"""The registry says where each project's traces go (D33), and refuses incoherent answers."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from _registry import (  # noqa: E402
    TRACE_BACKENDS,
    RegistryError,
    load_registry,
)

BASE = {
    "platform": {
        "mlflow_uri": "http://localhost:5000",
        "mlflow_uri_compose": "http://mlflow:5000",
        "docker_network": "nmp-central",
    }
}


def write_registry(tmp_path: Path, projects: list[dict[str, object]]) -> Path:
    reg_dir = tmp_path / "registry"
    reg_dir.mkdir()
    p = reg_dir / "projects.yaml"
    p.write_text(yaml.safe_dump(BASE | {"projects": projects}))
    return p


def proj(pid: str, obs: dict[str, object] | None) -> dict[str, object]:
    out: dict[str, object] = {"id": pid, "name": pid.lower(), "path": "."}
    if obs is not None:
        out["observability"] = obs
    return out


def test_a_project_declaring_langfuse_is_listed_for_the_trace_check(tmp_path: Path) -> None:
    reg = load_registry(
        write_registry(
            tmp_path,
            [
                proj("P1", {"backend": "langfuse", "langfuse_project": "convfinqa"}),
                proj("P2", {"backend": "mlflow"}),
                proj("P3", None),
            ],
        )
    )
    assert [p.id for p in reg.traced] == ["P1", "P2"]
    assert [p.id for p in reg.on_langfuse] == ["P1"]
    p2 = reg.by_id("P2").observability
    assert p2 is not None and p2.uses_mlflow and not p2.uses_langfuse


def test_both_means_a_project_exports_to_each_backend_during_migration(tmp_path: Path) -> None:
    """`both` is the reversible middle step of the cutover, so it must satisfy both checks."""
    reg = load_registry(
        write_registry(tmp_path, [proj("P5", {"backend": "both", "langfuse_project": "data-qa"})])
    )
    obs = reg.by_id("P5").observability
    assert obs is not None
    assert obs.uses_langfuse and obs.uses_mlflow
    assert [p.id for p in reg.on_langfuse] == ["P5"]


@pytest.mark.parametrize(
    "obs, message",
    [
        ({"backend": "jaeger"}, "must be one of"),
        ({}, "must be one of"),
        ({"backend": "langfuse"}, "needs a langfuse_project"),
        ({"backend": "both"}, "needs a langfuse_project"),
        ({"backend": "mlflow", "langfuse_project": "stray"}, "but backend is 'mlflow'"),
    ],
)
def test_registry_refuses_an_incoherent_observability_block(
    tmp_path: Path, obs: dict[str, object], message: str
) -> None:
    with pytest.raises(RegistryError, match=message):
        load_registry(write_registry(tmp_path, [proj("P9", obs)]))


def test_registry_refuses_two_projects_claiming_the_same_langfuse_project(tmp_path: Path) -> None:
    """Langfuse project names are instance-global, like roles and databases (D15)."""
    with pytest.raises(RegistryError, match="declared by both P1 and P2"):
        load_registry(
            write_registry(
                tmp_path,
                [
                    proj("P1", {"backend": "langfuse", "langfuse_project": "shared"}),
                    proj("P2", {"backend": "both", "langfuse_project": "shared"}),
                ],
            )
        )


def test_the_backend_vocabulary_is_closed(tmp_path: Path) -> None:
    """Every accepted value must round-trip, so the set and the parser cannot drift apart."""
    for backend in sorted(TRACE_BACKENDS):
        obs: dict[str, object] = {"backend": backend}
        if backend != "mlflow":
            obs["langfuse_project"] = f"p-{backend}"
        sub = tmp_path / backend
        sub.mkdir()
        reg = load_registry(write_registry(sub, [proj("P9", obs)]))
        got = reg.by_id("P9").observability
        assert got is not None and got.backend == backend


# ---- the real registry -------------------------------------------------------------------------


def test_every_tracing_project_declares_where_its_traces_go() -> None:
    """A project that logs traces but names no backend is the gap D33 exists to close."""
    reg = load_registry()
    for p in reg.projects:
        if p.on_platform and p.client in {"python", "otlp"}:
            assert p.observability is not None, f"{p.id} traces but declares no observability block"


def test_langfuse_owns_a_database_on_the_cluster_and_is_not_an_mlflow_client() -> None:
    reg = load_registry()
    lf = reg.by_id("LANGFUSE")
    assert lf.database is not None
    assert lf.database.name == "langfuse" and lf.database.roles == ["langfuse"]
    # it consumes the platform, so check_projects must not try to verify runs for it
    assert not lf.on_platform


def test_the_registry_has_no_duplicate_keys() -> None:
    """Regression: a duplicated `ui:` key once loaded fine because YAML is last-key-wins."""
    path = Path(__file__).resolve().parents[1] / "registry" / "projects.yaml"

    class Strict(yaml.SafeLoader):
        pass

    def no_dupes(loader: yaml.SafeLoader, node: yaml.MappingNode) -> dict[object, object]:
        seen: set[object] = set()
        for key_node, _ in node.value:
            key = loader.construct_object(key_node)
            assert key not in seen, f"duplicate key {key!r} at line {key_node.start_mark.line + 1}"
            seen.add(key)
        return loader.construct_mapping(node)

    Strict.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, no_dupes)
    yaml.load(path.read_text(), Loader=Strict)
