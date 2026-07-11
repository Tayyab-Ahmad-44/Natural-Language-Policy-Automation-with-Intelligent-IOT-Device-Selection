"""Loader sanity: every catalog and scenario YAML actually in the repo loads
and validates against the real backend schemas -- this is what makes a
malformed scenario fail loudly at load time instead of silently scoring
against a drifted shape."""

from __future__ import annotations

import pytest

import schemas
from eval.loaders import (
    CATALOG_DIR,
    load_all_conflict_scenarios,
    load_all_dag_scenarios,
    load_catalog,
    validate_conflict_scenario,
)
from eval.scoring.conflict_score import CONFLICT_TYPES

KNOWN_TAGS = {"single_node", "multi_node", "conditional", "parallel", "scheduled"}


def test_every_catalog_loads_with_required_shape():
    catalog_names = [p.stem for p in CATALOG_DIR.glob("*.yaml")]
    assert catalog_names, "expected at least one catalog file"

    for name in catalog_names:
        devices = load_catalog(name)
        assert devices, f"{name} catalog has no devices"
        for device in devices:
            assert {"name", "type", "capabilities"} <= device.keys()
            assert device["capabilities"], f"{device['name']} in {name} has no capabilities"
            for cap in device["capabilities"]:
                assert {"name", "url", "method", "input_schema"} <= cap.keys()


def test_every_dag_scenario_loads_and_validates_against_schema():
    scenarios = load_all_dag_scenarios()
    assert scenarios, "expected at least one DAG scenario"

    seen_ids = set()
    for sc in scenarios:
        assert sc.id not in seen_ids, f"duplicate scenario id: {sc.id}"
        seen_ids.add(sc.id)

        assert isinstance(sc.expected_dag, schemas.ExecutionDAG)
        assert sc.expected_dag.nodes, f"{sc.id} has an empty expected_dag"
        assert set(sc.tags) <= KNOWN_TAGS, f"{sc.id} uses unknown tag(s): {set(sc.tags) - KNOWN_TAGS}"

        node_ids = {n.id for n in sc.expected_dag.nodes}
        assert len(node_ids) == len(sc.expected_dag.nodes), f"{sc.id} has duplicate node ids"
        for n in sc.expected_dag.nodes:
            for dep in n.dependencies:
                assert dep in node_ids, f"{sc.id}: node {n.id} depends on unknown id {dep}"

        device_names = {d["name"] for d in sc.devices_data}
        for n in sc.expected_dag.nodes:
            assert n.device in device_names, f"{sc.id}: node {n.id} references unknown device {n.device!r}"


def test_every_conflict_scenario_loads_with_valid_labels():
    scenarios = load_all_conflict_scenarios()
    assert scenarios, "expected at least one conflict scenario"

    seen_ids = set()
    for sc in scenarios:
        assert sc["id"] not in seen_ids, f"duplicate scenario id: {sc['id']}"
        seen_ids.add(sc["id"])

        assert "actions" in sc["new_policy"]
        assert sc["candidates"], f"{sc['id']} has no candidates"
        for cand in sc["candidates"]:
            assert cand["expected_type"] in CONFLICT_TYPES, (
                f"{sc['id']}: candidate {cand['name']!r} has invalid expected_type {cand['expected_type']!r}"
            )


def test_conflict_validator_rejects_duplicate_candidate_names():
    raw = {
        "id": "bad_scenario",
        "new_policy": {
            "name": "New", "text": "", "window": {"from_time": "18:00", "to_time": "19:00"},
            "actions": [{"device": "X", "capability": "Y", "args": {}}],
        },
        "candidates": [
            {
                "name": "Dup", "text": "", "window": {"from_time": "18:00", "to_time": "19:00"},
                "actions": [{"device": "X", "capability": "Y", "args": {}}], "expected_type": "none",
            },
            {
                "name": "Dup", "text": "", "window": {"from_time": "18:00", "to_time": "19:00"},
                "actions": [{"device": "X", "capability": "Z", "args": {}}], "expected_type": "overlap",
            },
        ],
    }

    with pytest.raises(ValueError, match="duplicate candidate name"):
        validate_conflict_scenario(raw)
