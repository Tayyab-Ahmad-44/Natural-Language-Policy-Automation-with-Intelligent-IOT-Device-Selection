"""Shared precision/recall/F1-from-counts helper, used by both the DAG
scorer and the conflict scorer so the same zero-denominator convention
applies everywhere in the harness."""

from __future__ import annotations

from typing import Tuple


def prf_from_counts(tp: int, fp: int, fn: int) -> Tuple[float, float, float]:
    """Precision/recall/F1 from TP/FP/FN counts.

    Convention: if nothing was predicted AND nothing was expected (tp=fp=fn=0),
    that's a vacuous perfect match (1.0/1.0/1.0), not an undefined 0/0 -- e.g.
    a scenario with zero expected edges where the generated DAG also has zero
    edges is a correct prediction, not a non-answer. If something was
    expected but nothing was predicted, that's a real miss and scores 0,
    matching the standard convention (e.g. sklearn's zero_division=0).
    """
    if tp + fp == 0 and tp + fn == 0:
        return 1.0, 1.0, 1.0
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 0.0 if (precision + recall) == 0 else 2 * precision * recall / (precision + recall)
    return precision, recall, f1
