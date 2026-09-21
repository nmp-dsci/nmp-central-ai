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

    @property
    def on_platform(self) -> bool:
        return self.client in {"python", "otlp"} and self.status not in {"excluded", "external"}


@dataclass
class Registry:
    mlflow_uri: str
    mlflow_uri_compose: str
    docker_network: str
    projects: list[Project]

    def by_id(self, pid: str) -> Project:
        for p in self.projects:
            if p.id == pid:
                return p
        raise KeyError(pid)


def load_registry(path: Path = REGISTRY_PATH) -> Registry:
    raw: dict[str, Any] = yaml.safe_load(path.read_text())
    plat = raw["platform"]
    projects: list[Project] = []
    for item in raw["projects"]:
        ml = item.get("mlflow") or {}
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
            )
        )
    return Registry(
        mlflow_uri=plat["mlflow_uri"],
        mlflow_uri_compose=plat["mlflow_uri_compose"],
        docker_network=plat["docker_network"],
        projects=projects,
    )


def resolve_uri(explicit: str | None, reg: Registry) -> str:
    return explicit or os.environ.get("MLFLOW_TRACKING_URI") or reg.mlflow_uri
