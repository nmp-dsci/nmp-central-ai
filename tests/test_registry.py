import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from _registry import load_registry  # noqa: E402


def test_registry_loads_and_ids_unique() -> None:
    reg = load_registry()
    ids = [p.id for p in reg.projects]
    assert len(ids) == len(set(ids))
    assert reg.mlflow_uri.startswith("http")


def test_platform_projects_declare_experiments() -> None:
    reg = load_registry()
    for p in reg.projects:
        if p.on_platform:
            assert p.experiments, p.id
            assert p.verify in {"runs", "traces", "both"}, p.id


def test_env_ids_reference_declared_experiments() -> None:
    reg = load_registry()
    for p in reg.projects:
        for var, exp in p.env_ids.items():
            assert exp in p.experiments, (p.id, var)
