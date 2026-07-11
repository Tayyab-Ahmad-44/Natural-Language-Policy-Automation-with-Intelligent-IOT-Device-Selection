"""
YAML -> real backend types.

Device catalogs load into plain dicts matching application.py::_serialize_devices()
exactly (the shape fed to llm.parse_policy_with_llm as `devices_data`).
Scenario expected_dag blocks load into schemas.ExecutionDAG itself -- reusing
the real pydantic model means a malformed scenario YAML fails loudly at load
time (pydantic validation error) instead of silently scoring against a
drifted shadow schema.
"""

from __future__ import annotations

import pathlib
from dataclasses import dataclass, field
from typing import Any, Dict, List

import yaml

import eval as _eval_bootstrap  # noqa: F401  (side effect: backend/ on sys.path)
import schemas

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
CATALOG_DIR = REPO_ROOT / "eval" / "catalogs"
DAG_SCENARIO_DIR = REPO_ROOT / "eval" / "scenarios" / "dag"
CONFLICT_SCENARIO_DIR = REPO_ROOT / "eval" / "scenarios" / "conflicts"


def load_catalog(name: str) -> List[Dict[str, Any]]:
    """Load a device catalog by name (e.g. "home") into devices_data shape."""
    path = CATALOG_DIR / f"{name}.yaml"
    with path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    return data["devices"]


@dataclass
class DagScenario:
    id: str
    nl: str
    tags: List[str]
    catalog_name: str
    devices_data: List[Dict[str, Any]]
    expected_dag: schemas.ExecutionDAG
    source_path: pathlib.Path = field(repr=False)


def load_dag_scenario(path: pathlib.Path) -> DagScenario:
    with path.open(encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    devices_data = load_catalog(raw["catalog"])
    expected_dag = schemas.ExecutionDAG(**raw["expected_dag"])
    return DagScenario(
        id=raw["id"],
        nl=raw["nl"],
        tags=list(raw.get("tags", [])),
        catalog_name=raw["catalog"],
        devices_data=devices_data,
        expected_dag=expected_dag,
        source_path=path,
    )


def load_all_dag_scenarios() -> List[DagScenario]:
    return [load_dag_scenario(p) for p in sorted(DAG_SCENARIO_DIR.glob("*.yaml"))]


def validate_conflict_scenario(raw: Dict[str, Any], source: str = "<scenario>") -> Dict[str, Any]:
    """Conflict scenarios are kept as plain dicts (not a dataclass/pydantic
    model): they're fed straight into conflicts.detect_conflicts(), which
    itself expects plain dicts, so there's no real type to validate against
    the way schemas.ExecutionDAG validates DAG scenarios. The one invariant
    this harness relies on -- candidate names unique within a scenario, used
    to match detect_conflicts()'s output back to the labelled candidate
    that produced it -- is checked explicitly here instead. Split out from
    load_conflict_scenario() so it's testable on plain dicts, with no file
    I/O required.
    """
    names = [c["name"] for c in raw["candidates"]]
    duplicates = {n for n in names if names.count(n) > 1}
    if duplicates:
        raise ValueError(f"{source}: duplicate candidate name(s) {duplicates} -- names must be unique within a scenario")
    return raw


def load_conflict_scenario(path: pathlib.Path) -> Dict[str, Any]:
    with path.open(encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    return validate_conflict_scenario(raw, source=str(path))


def load_all_conflict_scenarios() -> List[Dict[str, Any]]:
    return [load_conflict_scenario(p) for p in sorted(CONFLICT_SCENARIO_DIR.glob("*.yaml"))]
