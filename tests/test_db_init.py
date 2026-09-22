"""db_init renders the psql script the cluster is made from; the registry refuses bad names."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from _registry import SUPERUSER, RegistryError, load_registry  # noqa: E402
from db_init import render_env, render_sql, url_for  # noqa: E402

BASE = {
    "platform": {
        "mlflow_uri": "http://localhost:5000",
        "mlflow_uri_compose": "http://mlflow:5000",
        "docker_network": "nmp-central",
        "postgres_uri": "postgresql://localhost:5432",
        "postgres_superuser": "nmp",
        "postgres_db": "nmp",
    }
}


def write_registry(tmp_path: Path, projects: list[dict[str, object]]) -> Path:
    # load_registry resolves project paths relative to the registry's grandparent
    reg_dir = tmp_path / "registry"
    reg_dir.mkdir()
    p = reg_dir / "projects.yaml"
    p.write_text(yaml.safe_dump(BASE | {"projects": projects}))
    return p


def proj(pid: str, name: str, db: dict[str, object]) -> dict[str, object]:
    return {"id": pid, "name": name, "path": ".", "mlflow": {"client": "external"}, "database": db}


def test_render_sql_creates_roles_databases_and_extensions_idempotently(tmp_path: Path) -> None:
    reg = load_registry(
        write_registry(
            tmp_path,
            [
                proj(
                    "P9",
                    "demo",
                    {
                        "name": "demo",
                        "roles": ["demo_app"],
                        "extensions": ["vector"],
                        "env": {"DATABASE_URL": "demo_app", "ADMIN_URL": SUPERUSER},
                    },
                )
            ],
        )
    )
    sql = render_sql(reg, reg.databases)
    assert "IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'demo_app')" in sql
    assert "CREATE ROLE demo_app LOGIN PASSWORD 'demo_app' NOSUPERUSER" in sql
    assert "ALTER ROLE demo_app WITH LOGIN PASSWORD 'demo_app';" in sql
    assert "SELECT 'CREATE DATABASE demo OWNER nmp'" in sql and "\\gexec" in sql
    assert "\\connect demo\nCREATE EXTENSION IF NOT EXISTS vector;\n\\connect nmp" in sql


def test_role_password_env_override_reaches_sql_and_urls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DEMO_APP_PASSWORD", "s3cret'quote")
    reg = load_registry(
        write_registry(
            tmp_path,
            [
                proj(
                    "P9",
                    "demo",
                    {"name": "demo", "roles": ["demo_app"], "env": {"DATABASE_URL": "demo_app"}},
                )
            ],
        )
    )
    sql = render_sql(reg, reg.databases)
    assert "PASSWORD 's3cret''quote'" in sql  # quoted for SQL
    db = reg.databases[0].database
    assert db is not None
    assert url_for(reg, db, "demo_app", "postgresql", reg.postgres_uri) == (
        "postgresql://demo_app:s3cret'quote@localhost:5432/demo"
    )


def test_env_block_uses_scheme_and_superuser(tmp_path: Path) -> None:
    reg = load_registry(
        write_registry(
            tmp_path,
            [
                proj(
                    "P9",
                    "demo",
                    {
                        "name": "demo",
                        "roles": ["demo_app"],
                        "env": {
                            "DATABASE_URL": {"role": "demo_app", "scheme": "postgresql+asyncpg"},
                            "ADMIN_DATABASE_URL": SUPERUSER,
                        },
                    },
                )
            ],
        )
    )
    env = render_env(reg, reg.databases, "postgresql://localhost:15432")
    assert "DATABASE_URL=postgresql+asyncpg://demo_app:demo_app@localhost:15432/demo" in env
    assert "ADMIN_DATABASE_URL=postgresql://nmp:nmp@localhost:15432/demo" in env


def test_aws_target_skips_projects_marked_aws_false(tmp_path: Path) -> None:
    reg = load_registry(
        write_registry(
            tmp_path,
            [
                proj("PLATFORM", "central", {"name": "mlflow", "roles": ["mlflow"], "aws": True}),
                proj("P9", "demo", {"name": "demo", "roles": ["demo_app"], "aws": False}),
            ],
        )
    )
    sql = render_sql(reg, reg.databases, target="aws")
    assert "CREATE DATABASE mlflow" in sql
    assert "CREATE DATABASE demo" not in sql and "aws=false, skipped" in sql


@pytest.mark.parametrize(
    "second, message",
    [
        ({"name": "demo", "roles": ["other_role"]}, "database 'demo' declared by both"),
        ({"name": "other", "roles": ["demo_app"]}, "role 'demo_app' declared by both"),
        ({"name": "other", "roles": ["nmp"]}, "is the cluster superuser"),
        (
            {"name": "other", "roles": ["x"], "env": {"URL": "ghost"}},
            "names role 'ghost' not in roles",
        ),
    ],
)
def test_registry_refuses_cluster_global_collisions(
    tmp_path: Path, second: dict[str, object], message: str
) -> None:
    path = write_registry(
        tmp_path,
        [
            proj("P8", "first", {"name": "demo", "roles": ["demo_app"]}),
            proj("P9", "second", second),
        ],
    )
    with pytest.raises(RegistryError, match=message):
        load_registry(path)


def test_the_real_registry_declares_a_database_for_the_platform() -> None:
    reg = load_registry()
    ids = {p.id: p for p in reg.databases}
    assert "PLATFORM" in ids and ids["PLATFORM"].database is not None
    assert ids["PLATFORM"].database.name == "mlflow"
    for p in reg.databases:
        assert p.database is not None
        assert p.database.status in {"pending", "migrated"}, p.id


def test_a_role_may_carry_a_grandfathered_local_password(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("LEGACY_PASSWORD", raising=False)
    reg = load_registry(
        write_registry(
            tmp_path,
            [
                proj(
                    "P9",
                    "demo",
                    {
                        "name": "demo",
                        "roles": [{"name": "legacy", "password": "legacy_pw"}, "demo_app"],
                        "env": {"URL": "legacy"},
                    },
                )
            ],
        )
    )
    sql = render_sql(reg, reg.databases)
    assert "CREATE ROLE legacy LOGIN PASSWORD 'legacy_pw'" in sql
    assert "CREATE ROLE demo_app LOGIN PASSWORD 'demo_app'" in sql
    assert "URL=postgresql://legacy:legacy_pw@localhost:5432/demo" in render_env(
        reg, reg.databases, reg.postgres_uri
    )
    monkeypatch.setenv("LEGACY_PASSWORD", "from-env")
    assert "PASSWORD 'from-env'" in render_sql(reg, reg.databases)


def test_role_options_are_rendered_and_validated(tmp_path: Path) -> None:
    reg = load_registry(
        write_registry(
            tmp_path,
            [
                proj(
                    "P9",
                    "demo",
                    {"name": "demo", "roles": [{"name": "ro", "options": ["bypassrls"]}]},
                )
            ],
        )
    )
    sql = render_sql(reg, reg.databases)
    assert "CREATE ROLE ro LOGIN PASSWORD 'ro' NOSUPERUSER BYPASSRLS;" in sql
    assert "ALTER ROLE ro WITH LOGIN PASSWORD 'ro' BYPASSRLS;" in sql
    (tmp_path / "bad").mkdir()
    with pytest.raises(RegistryError, match="unsupported options"):
        load_registry(
            write_registry(
                tmp_path / "bad",
                [
                    proj(
                        "P9",
                        "demo",
                        {"name": "demo", "roles": [{"name": "ro", "options": ["SUPERUSER"]}]},
                    )
                ],
            )
        )


def test_role_settings_become_alter_role_set(tmp_path: Path) -> None:
    reg = load_registry(
        write_registry(
            tmp_path,
            [
                proj(
                    "P9",
                    "demo",
                    {
                        "name": "demo",
                        "roles": [{"name": "ro", "settings": {"statement_timeout": "15s"}}],
                    },
                )
            ],
        )
    )
    assert "ALTER ROLE ro SET statement_timeout = '15s';" in render_sql(reg, reg.databases)
