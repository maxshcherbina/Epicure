"""Persistence and lineage export for EpiCure's committed tracking state."""

from collections.abc import Mapping, Sequence
from copy import deepcopy
import csv

import numpy as np


TRACKING_STATE_VERSION = 1


def serialize_tracking_state(tracking):
    """Return the versioned state that cannot be reconstructed from labels alone."""
    return {
        "Version": TRACKING_STATE_VERSION,
        "TrackData": (
            None if tracking.track_data is None else np.copy(tracking.track_data)
        ),
        "MethodMetadata": deepcopy(tracking.tracking_method_metadata),
        "CorrectionLedger": deepcopy(tracking.correction_ledger),
        "Conflicts": deepcopy(tracking.tracking_conflicts),
    }


def restore_tracking_state(tracking, state):
    """Restore a saved tracking block, defaulting absent legacy fields safely."""
    if not isinstance(state, Mapping):
        return

    track_data = state.get("TrackData")
    if track_data is not None:
        track_data = np.asarray(track_data)
        if track_data.ndim != 2 or track_data.shape[1] != 4:
            raise ValueError("Saved Tracks data must have four columns")
        tracking.track_data = np.copy(track_data)
        if tracking.tracklayer is not None:
            tracking.tracklayer.data = tracking.track_data

    tracking.tracking_method_metadata = deepcopy(state.get("MethodMetadata", {}))
    tracking.correction_ledger = deepcopy(state.get("CorrectionLedger", []))
    tracking.tracking_conflicts = deepcopy(state.get("Conflicts", []))
    tracking.update_conflict_status()
    if tracking.tracklayer is not None:
        tracking.tracklayer.graph = tracking.graph or {}
        tracking.tracklayer.refresh()


def lineage_rows(track_data, graph):
    """Build CTC-style lineage rows from final native track IDs and graph."""
    if track_data is None:
        return []
    track_data = np.asarray(track_data)
    if track_data.ndim != 2 or track_data.shape[1] != 4:
        raise ValueError("Tracks data must have four columns")

    graph = graph or {}
    rows = []
    for raw_label in sorted(np.unique(track_data[:, 0])):
        label = int(raw_label)
        frames = track_data[track_data[:, 0] == raw_label, 1]
        raw_parent = graph.get(label, 0)
        if isinstance(raw_parent, Sequence) and not isinstance(raw_parent, (str, bytes)):
            parent = int(raw_parent[0]) if len(raw_parent) else 0
        else:
            parent = int(raw_parent) if raw_parent else 0
        rows.append(
            {
                "label": label,
                "t1": int(np.min(frames)),
                "t2": int(np.max(frames)),
                "parent": parent,
            }
        )
    return rows


def write_lineage_csv(path, track_data, graph):
    """Write the lineage table derived from the same state saved in the project."""
    with open(path, "w", newline="") as outfile:
        writer = csv.DictWriter(outfile, fieldnames=("label", "t1", "t2", "parent"))
        writer.writeheader()
        writer.writerows(lineage_rows(track_data, graph))
