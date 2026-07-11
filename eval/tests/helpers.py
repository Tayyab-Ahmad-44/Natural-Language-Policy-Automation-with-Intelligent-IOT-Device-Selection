"""Plain builder functions shared across the pytest suite -- not fixtures,
just terse constructors so test bodies read as data, not boilerplate."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import schemas


def node(
    id: str,
    device: str,
    capability: str,
    args: Optional[Dict[str, Any]] = None,
    deps: Optional[List[str]] = None,
    condition: Optional[Any] = None,
    on_failure: str = "ignore",
) -> schemas.ExecutionNode:
    return schemas.ExecutionNode(
        id=id,
        device=device,
        capability=capability,
        args=args or {},
        dependencies=deps or [],
        condition=condition,
        on_failure=on_failure,
    )


def dag(*nodes: schemas.ExecutionNode) -> schemas.ExecutionDAG:
    return schemas.ExecutionDAG(nodes=list(nodes))
