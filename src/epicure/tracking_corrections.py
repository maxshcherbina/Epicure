"""Stable human association decisions and deterministic replay."""

from collections.abc import Mapping


def _detection_key(value):
    frame, label = value
    return int(frame), int(label)


def association_correction(source, target, decision):
    """Create one persisted association decision using frame-local detections."""
    if decision not in {"protected", "forbidden"}:
        raise ValueError("Association decision must be protected or forbidden")
    source = _detection_key(source)
    target = _detection_key(target)
    if source[0] >= target[0]:
        raise ValueError("Association corrections must point forward in time")
    return {
        "kind": "association",
        "decision": decision,
        "source": source,
        "target": target,
    }


def _entries(ledger):
    if isinstance(ledger, list):
        return list(ledger)
    if isinstance(ledger, tuple):
        return list(ledger)
    if isinstance(ledger, Mapping) and ledger.get("kind"):
        return [dict(ledger)]
    return []


def set_association_correction(ledger, source, target, decision):
    """Replace an exact decision and enforce exclusive protected continuations."""
    entry = association_correction(source, target, decision)
    source = entry["source"]
    target = entry["target"]
    retained = []
    for existing in _entries(ledger):
        if not isinstance(existing, Mapping) or existing.get("kind") != "association":
            retained.append(existing)
            continue
        existing_source = _detection_key(existing["source"])
        existing_target = _detection_key(existing["target"])
        if existing_source == source and existing_target == target:
            continue
        if (
            decision == "protected"
            and existing.get("decision") == "protected"
            and (existing_source == source or existing_target == target)
        ):
            continue
        retained.append(existing)
    retained.append(entry)
    return retained


def remove_association_correction(ledger, source, target):
    """Remove the explicit decision for one detection pair."""
    source = _detection_key(source)
    target = _detection_key(target)
    return [
        entry
        for entry in _entries(ledger)
        if not (
            isinstance(entry, Mapping)
            and entry.get("kind") == "association"
            and _detection_key(entry["source"]) == source
            and _detection_key(entry["target"]) == target
        )
    ]


def reconcile_association_edges(detection_keys, automatic_edges, ledger):
    """Replay valid decisions as hard winners over automatic associations."""
    detections = {_detection_key(key) for key in detection_keys}
    edges = {
        (_detection_key(source), _detection_key(target))
        for source, target in automatic_edges
    }
    applied = []
    for raw_entry in _entries(ledger):
        if not isinstance(raw_entry, Mapping) or raw_entry.get("kind") != "association":
            continue
        decision = raw_entry.get("decision")
        if decision not in {"protected", "forbidden"}:
            continue
        source = _detection_key(raw_entry["source"])
        target = _detection_key(raw_entry["target"])
        if source not in detections or target not in detections:
            continue
        if decision == "forbidden":
            edges.discard((source, target))
        else:
            edges = {
                edge
                for edge in edges
                if edge[0] != source and edge[1] != target
            }
            edges.add((source, target))
        applied.append(association_correction(source, target, decision))
    return tuple(sorted(edges)), tuple(applied)
