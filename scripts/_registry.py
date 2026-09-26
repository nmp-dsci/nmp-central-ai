"""Shared helpers for the platform scripts: load the registry, talk to MLflow."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT / "registry" / "projects.yaml"
IDS_ENV_PATH = ROOT / ".mlflow-ids.env"
DB_URLS_ENV_PATH = ROOT / ".db-urls.env"
DBGATE_ENV_PATH = ROOT / ".dbgate.env"  # the DB UI's connection list (D20), env_file in compose


SUPERUSER = "superuser"  # the `env:` value that means "the cluster superuser" (D16)
ROLE_OPTIONS = {"BYPASSRLS", "NOBYPASSRLS", "CREATEDB", "NOCREATEDB", "INHERIT", "NOINHERIT"}


@dataclass(frozen=True)
class DbEnv:
    """One URL the project reads: which role it connects as, and the URL scheme."""

    var: str
    role: str  # a declared role name, or SUPERUSER
    scheme: str = "postgresql"


@dataclass
class Database:
    """A project's database on the central cluster (registry `database:` block, M3)."""

    name: str
    roles: list[str] = field(default_factory=list)
    passwords: dict[str, str] = field(default_factory=dict)  # local dev defaults per role
    options: dict[str, list[str]] = field(default_factory=dict)  # role attributes, e.g. BYPASSRLS
    settings: dict[str, dict[str, str]] = field(default_factory=dict)  # ALTER ROLE … SET k = v
    extensions: list[str] = field(default_factory=list)
    env: list[DbEnv] = field(default_factory=list)
    migrate: str = ""
    smoke: str = ""
    status: str = "pending"
    aws: bool = False
    # DB UI hint: load schemas lazily (DbGate USE_SEPARATE_SCHEMAS) — set for DAB's 2 813 tables
    ui_separate_schemas: bool = False


@dataclass
class Project:
    id: str
    name: str
    path: Path
    status: str
    client: str
    experiments: list[str] = field(default_factory=list)
    env_ids: dict[str, str] = field(default_factory=dict)
    verify: str = "runs"
    smoke: str = ""
    notes: str = ""
    database: Database | None = None

    @property
    def on_platform(self) -> bool:
        return self.client in {"python", "otlp"} and self.status not in {"excluded", "external"}


@dataclass
class Registry:
    mlflow_uri: str
    mlflow_uri_compose: str
    docker_network: str
    projects: list[Project]
    postgres_uri: str = "postgresql://localhost:5432"
    postgres_uri_compose: str = "postgresql://postgres:5432"
    postgres_superuser: str = "nmp"
    postgres_db: str = "nmp"  # the maintenance database psql connects to first

    def by_id(self, pid: str) -> Project:
        for p in self.projects:
            if p.id == pid:
                return p
        raise KeyError(pid)

    @property
    def databases(self) -> list[Project]:
        return [p for p in self.projects if p.database is not None]


class RegistryError(ValueError):
    """The registry declares something the cluster cannot honour (duplicate names, bad refs)."""


def _parse_database(raw: dict[str, Any]) -> Database:
    env: list[DbEnv] = []
    for var, spec in (raw.get("env") or {}).items():
        if isinstance(spec, str):
            env.append(DbEnv(var=var, role=spec))
        else:
            env.append(DbEnv(var=var, role=spec["role"], scheme=spec.get("scheme", "postgresql")))
    roles: list[str] = []
    passwords: dict[str, str] = {}
    options: dict[str, list[str]] = {}
    settings: dict[str, dict[str, str]] = {}
    for item in raw.get("roles") or []:
        if isinstance(item, str):
            roles.append(item)
            continue
        # {name, password, options}: password is a grandfathered local default (D15), e.g.
        # data-qa's app_pw; options are cluster-level role attributes a database dump cannot
        # carry (data-qa's admin_ro is BYPASSRLS); settings are per-role GUCs set the same way
        # (data-qa's statement_timeout), also cluster-level.
        roles.append(item["name"])
        if item.get("password"):
            passwords[item["name"]] = str(item["password"])
        opts = [str(o).upper() for o in (item.get("options") or [])]
        bad = [o for o in opts if o not in ROLE_OPTIONS]
        if bad:
            raise RegistryError(f"role {item['name']!r}: unsupported options {bad}")
        if opts:
            options[item["name"]] = opts
        if item.get("settings"):
            settings[item["name"]] = {str(k): str(v) for k, v in item["settings"].items()}
    return Database(
        name=raw["name"],
        roles=roles,
        passwords=passwords,
        options=options,
        settings=settings,
        extensions=list(raw.get("extensions") or []),
        env=env,
        migrate=(raw.get("migrate") or "").strip(),
        smoke=(raw.get("smoke") or "").strip(),
        status=raw.get("status", "pending"),
        aws=bool(raw.get("aws", False)),
        ui_separate_schemas=bool(raw.get("ui_separate_schemas", False)),
    )


def validate_databases(reg: Registry) -> None:
    """Role and database names are cluster-global (D15): refuse a registry that reuses one."""
    seen_db: dict[str, str] = {}
    seen_role: dict[str, str] = {}
    for p in reg.databases:
        db = p.database
        assert db is not None
        if db.name in seen_db:
            raise RegistryError(
                f"database {db.name!r} declared by both {seen_db[db.name]} and {p.id}"
            )
        seen_db[db.name] = p.id
        for r in db.roles:
            if r == reg.postgres_superuser:
                raise RegistryError(
                    f"{p.id}: role {r!r} is the cluster superuser; do not declare it"
                )
            if r in seen_role:
                raise RegistryError(f"role {r!r} declared by both {seen_role[r]} and {p.id}")
            seen_role[r] = p.id
        for e in db.env:
            if e.role != SUPERUSER and e.role not in db.roles:
                raise RegistryError(f"{p.id}: env {e.var} names role {e.role!r} not in roles")


def load_registry(path: Path = REGISTRY_PATH) -> Registry:
    raw: dict[str, Any] = yaml.safe_load(path.read_text())
    plat = raw["platform"]
    projects: list[Project] = []
    for item in raw["projects"]:
        ml = item.get("mlflow") or {}
        db_raw = item.get("database")
        projects.append(
            Project(
                id=item["id"],
                name=item["name"],
                path=(path.parent.parent / item["path"]).resolve(),
                status=item.get("status", "pending"),
                client=ml.get("client", "external"),
                experiments=list(ml.get("experiments") or []),
                env_ids=dict(ml.get("env_ids") or {}),
                verify=ml.get("verify", "runs"),
                smoke=(ml.get("smoke") or "").strip(),
                notes=(item.get("notes") or "").strip(),
                database=_parse_database(db_raw) if db_raw else None,
            )
        )
    reg = Registry(
        mlflow_uri=plat["mlflow_uri"],
        mlflow_uri_compose=plat["mlflow_uri_compose"],
        docker_network=plat["docker_network"],
        projects=projects,
        postgres_uri=plat.get("postgres_uri", "postgresql://localhost:5432"),
        postgres_uri_compose=plat.get("postgres_uri_compose", "postgresql://postgres:5432"),
        postgres_superuser=plat.get("postgres_superuser", "nmp"),
        postgres_db=plat.get("postgres_db", "nmp"),
    )
    validate_databases(reg)
    return reg


def resolve_uri(explicit: str | None, reg: Registry) -> str:
    return explicit or os.environ.get("MLFLOW_TRACKING_URI") or reg.mlflow_uri
