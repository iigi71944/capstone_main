"""Batch 35-4: version and provenance of saved 81-metric snapshots.

No migration and no imputation: a missing counter is unknown, not an observed
zero. Current complete snapshots may drive transformations; malformed or
unsupported snapshots fail closed. Legacy *unversioned* snapshots retain prior
planning behavior for backward compatibility and are explicitly identified.
"""
from __future__ import annotations

import ast
from functools import lru_cache
from typing import Any

from app.services.metric_service import calculate_metrics

METRICS_SCHEMA_VERSION = 1


@lru_cache(maxsize=1)
def metric_names() -> frozenset[str]:
    # Derive the key contract from the actual production extractor, preventing
    # a separately maintained list from drifting when the extractor changes.
    return frozenset(calculate_metrics(ast.parse("")).keys())


def normalize_style_metric_snapshot(style: dict | None) -> tuple[dict[str, int], dict]:
    """Return observed, valid counters and JSON-safe provenance.

    Missing/invalid counters are omitted rather than rewritten to zero. No
    source object is mutated and no unknown metric becomes a transform gate.
    An unversioned *valid partial* snapshot remains backward-compatible; a
    declared current version must be complete and valid before auto-apply.
    """
    raw_style = style if isinstance(style, dict) else {}
    raw = raw_style.get("metrics", {})
    version = raw_style.get("metrics_version")
    expected = metric_names()
    malformed_container = not isinstance(raw, dict)
    source = raw if isinstance(raw, dict) else {}
    valid: dict[str, int] = {}
    invalid: list[str] = []
    extra: list[str] = []
    for key, value in source.items():
        if not isinstance(key, str):
            invalid.append(str(key))
        elif key not in expected:
            extra.append(key)
        elif type(value) is not int or value < 0:
            invalid.append(key)
        else:
            valid[key] = value

    missing = sorted(expected.difference(valid))
    invalid.sort()
    extra.sort()
    is_legacy = version is None
    supported = type(version) is int and version == METRICS_SCHEMA_VERSION
    if not is_legacy and not supported:
        status = "unsupported_version"
        allowed = False
    elif malformed_container or invalid:
        status = "invalid_snapshot"
        allowed = False
    elif supported and missing:
        status = "incomplete_versioned"
        allowed = False
    elif supported:
        status = "current_complete"
        allowed = True
    elif missing:
        status = "legacy_partial"
        # Existing saved styles are not retrospectively versioned. Keep their
        # established transformation behavior, but expose missing evidence.
        allowed = True
    else:
        status = "legacy_complete"
        allowed = True

    info: dict[str, Any] = {
        "schema_version": METRICS_SCHEMA_VERSION,
        "stored_version": version if type(version) is int else None,
        "status": status,
        "complete": not missing and not invalid and not malformed_container,
        "automatic_transforms_allowed": allowed,
        "expected_count": len(expected),
        "observed_count": len(valid),
        "missing_keys": missing,
        "invalid_keys": invalid,
        "unknown_keys": extra,
    }
    return valid, info
