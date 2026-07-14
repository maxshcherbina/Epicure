"""Range-safe preparation of tracking results before they reach live EpiCure state."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

import numpy as np


Graph = Mapping[int, int | Sequence[int]]


@dataclass(frozen=True)
class TrackingConflict:
    """A relationship that could not be reconciled without guessing."""

    kind: str
    endpoints: tuple[int, ...]
    message: str
    correction_kind: str | None = None
    decision: str | None = None
    detection_endpoints: tuple[tuple[int, int], ...] = ()
    tracking_range: tuple[int, int] | None = None
    reason: str = ""


@dataclass(frozen=True)
class TrackingProposal:
    """Method-neutral tracker output for one inclusive frame range."""

    start_frame: int
    end_frame: int
    source_labels: np.ndarray
    labels: np.ndarray
    graph: Graph
    method: str
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TrackingResult:
    """A fully validated movie state that can be committed atomically."""

    labels: np.ndarray
    graph: dict[int, list[int]]
    conflicts: tuple[TrackingConflict, ...]
    method: str
    tracking_range: tuple[int, int]
    metadata: Mapping[str, Any] = field(default_factory=dict)


def _positive_ids(labels: np.ndarray) -> set[int]:
    return {int(value) for value in np.unique(labels) if value != 0}


def exclude_border_cells(labels: np.ndarray, border_size: int = 1) -> np.ndarray:
    """Return labels with cells at the configured border distance removed."""

    movie = np.asarray(labels)
    if movie.ndim != 3:
        raise ValueError("Border exclusion expects a 3D label movie")
    if border_size < 0:
        raise ValueError("Border size cannot be negative")
    inset = border_size + 1
    excluded = movie.copy()
    for index, frame in enumerate(movie):
        border_labels = np.unique(
            np.concatenate(
                (
                    frame[:inset, :].ravel(),
                    frame[-inset:, :].ravel(),
                    frame[:, :inset].ravel(),
                    frame[:, -inset:].ravel(),
                )
            )
        )
        border_labels = border_labels[border_labels != 0]
        excluded[index][np.isin(frame, border_labels)] = 0
    return excluded


def _parents(value: int | Sequence[int]) -> list[int]:
    if isinstance(value, (int, np.integer)):
        return [int(value)]
    return [int(parent) for parent in value]


def _boundary_anchors(
    current: np.ndarray, proposal: TrackingProposal
) -> dict[int, list[tuple[int, int]]]:
    anchors: dict[int, list[tuple[int, int]]] = {}
    boundaries = (
        (proposal.start_frame, 0, proposal.start_frame - 1, 0),
        (proposal.end_frame, -1, proposal.end_frame + 1, 1),
    )
    for frame, proposal_index, outside_frame, priority in boundaries:
        if outside_frame < 0 or outside_frame >= current.shape[0]:
            continue
        source_frame = proposal.source_labels[proposal_index]
        proposed_frame = proposal.labels[proposal_index]
        crossing_ids = _positive_ids(source_frame) & _positive_ids(
            current[outside_frame]
        )
        for source_id in sorted(crossing_ids):
            local_ids = _positive_ids(proposed_frame[source_frame == source_id])
            if len(local_ids) == 1:
                local_id = next(iter(local_ids))
                anchors.setdefault(local_id, []).append((priority, source_id))
    return anchors


def _preferred_source_id(proposal: TrackingProposal, local_id: int) -> int:
    for source_frame, proposed_frame in zip(
        proposal.source_labels, proposal.labels, strict=True
    ):
        source_ids = _positive_ids(source_frame[proposed_frame == local_id])
        if source_ids:
            return min(source_ids)
    raise ValueError(f"Proposed track {local_id} contains no detections")


def _assign_track_ids(
    current: np.ndarray, proposal: TrackingProposal
) -> tuple[
    dict[int, int],
    tuple[tuple[int, int], ...],
    tuple[TrackingConflict, ...],
]:
    before = current[: proposal.start_frame]
    after = current[proposal.end_frame + 1 :]
    outside_ids = _positive_ids(before) | _positive_ids(after)
    local_ids = sorted(_positive_ids(proposal.labels))
    anchors = _boundary_anchors(current, proposal)
    assigned: dict[int, int] = {}
    claimed: set[int] = set()
    boundary_overrides: list[tuple[int, int]] = []
    conflicts: list[TrackingConflict] = []

    next_id = max(_positive_ids(current) | set(local_ids) | {0}) + 1

    def allocate() -> int:
        nonlocal next_id
        while next_id in outside_ids or next_id in claimed:
            next_id += 1
        value = next_id
        next_id += 1
        return value

    for local_id in local_ids:
        candidates = sorted(set(anchors.get(local_id, ())))
        anchor_ids = [source_id for _, source_id in candidates]
        if len(set(anchor_ids)) > 1:
            conflicts.append(
                TrackingConflict(
                    kind="range-boundary-identity",
                    endpoints=tuple(dict.fromkeys(anchor_ids)),
                    message=(
                        "One proposed track connects different preserved identities at "
                        "the tracking-range boundaries"
                    ),
                )
            )
            boundary_overrides.extend(candidates)
        available = [source_id for source_id in anchor_ids if source_id not in claimed]
        if available:
            final_id = available[0]
        else:
            preferred = _preferred_source_id(proposal, local_id)
            if preferred not in outside_ids and preferred not in claimed:
                final_id = preferred
            else:
                final_id = allocate()
        assigned[local_id] = final_id
        claimed.add(final_id)

    return assigned, tuple(boundary_overrides), tuple(conflicts)


def _validate_proposal(current: np.ndarray, proposal: TrackingProposal) -> None:
    if current.ndim != 3:
        raise ValueError("Tracking labels must be a 3D frame, row, column movie")
    if not 0 <= proposal.start_frame <= proposal.end_frame < current.shape[0]:
        raise ValueError("Tracking proposal range is outside the label movie")
    expected_shape = (
        proposal.end_frame - proposal.start_frame + 1,
        *current.shape[1:],
    )
    if proposal.source_labels.shape != expected_shape:
        raise ValueError("Tracking proposal source labels do not match its range")
    if proposal.labels.shape != expected_shape:
        raise ValueError("Tracking proposal labels do not match its range")
    if not np.array_equal(proposal.source_labels > 0, proposal.labels > 0):
        raise ValueError("Tracking proposal must retain every source detection mask")
    for source_frame, proposed_frame in zip(
        proposal.source_labels, proposal.labels, strict=True
    ):
        for source_id in _positive_ids(source_frame):
            assigned_ids = _positive_ids(proposed_frame[source_frame == source_id])
            if len(assigned_ids) != 1:
                raise ValueError(
                    "Tracking proposal must assign each segmentation detection "
                    "to exactly one track"
                )

    proposed_ids = _positive_ids(proposal.labels)
    for child, raw_parents in proposal.graph.items():
        relationship_ids = {int(child), *_parents(raw_parents)}
        if not relationship_ids <= proposed_ids:
            raise ValueError("Tracking proposal graph refers to an unknown track")


def _merge_graph(
    current_labels: np.ndarray,
    result_labels: np.ndarray,
    current_graph: Graph | None,
    proposal: TrackingProposal,
    id_mapping: Mapping[int, int],
) -> tuple[dict[int, list[int]], tuple[TrackingConflict, ...]]:
    before = current_labels[: proposal.start_frame]
    after = current_labels[proposal.end_frame + 1 :]
    outside_ids = _positive_ids(before) | _positive_ids(after)
    final_ids = _positive_ids(result_labels)
    merged: dict[int, list[int]] = {}
    conflicts: list[TrackingConflict] = []

    for raw_child, raw_parents in (current_graph or {}).items():
        child = int(raw_child)
        parents = _parents(raw_parents)
        if child not in outside_ids and not any(parent in outside_ids for parent in parents):
            continue
        missing = [endpoint for endpoint in (child, *parents) if endpoint not in final_ids]
        if missing:
            conflicts.append(
                TrackingConflict(
                    kind="range-boundary-relationship",
                    endpoints=(child, *parents),
                    message=(
                        "A relationship crossing the tracking range has an endpoint "
                        "that no longer exists"
                    ),
                )
            )
            continue
        merged[child] = parents

    for raw_child, raw_parents in proposal.graph.items():
        child = id_mapping[int(raw_child)]
        parents = [id_mapping[parent] for parent in _parents(raw_parents)]
        if child in merged and merged[child] != parents:
            conflicts.append(
                TrackingConflict(
                    kind="range-boundary-relationship",
                    endpoints=(child, *parents),
                    message="A proposed relationship conflicts with a preserved boundary relationship",
                )
            )
            continue
        merged[child] = parents

    return merged, tuple(conflicts)


def prepare_tracking_result(
    current_labels: np.ndarray, graph: Graph | None, proposal: TrackingProposal
) -> TrackingResult:
    """Validate and merge a proposal without mutating the current movie."""

    current = np.asarray(current_labels)
    _validate_proposal(current, proposal)
    id_mapping, boundary_overrides, id_conflicts = _assign_track_ids(
        current, proposal
    )

    result = current.copy()
    relabeled = np.zeros_like(proposal.labels, dtype=result.dtype)
    for local_id, final_id in id_mapping.items():
        relabeled[proposal.labels == local_id] = final_id
    for boundary, source_id in boundary_overrides:
        proposal_index = 0 if boundary == 0 else -1
        source_mask = proposal.source_labels[proposal_index] == source_id
        relabeled[proposal_index][source_mask] = source_id
    result[proposal.start_frame : proposal.end_frame + 1] = relabeled

    merged_graph, graph_conflicts = _merge_graph(
        current, result, graph, proposal, id_mapping
    )

    return TrackingResult(
        labels=result,
        graph=merged_graph,
        conflicts=(
            *id_conflicts,
            *graph_conflicts,
            *tuple(proposal.metadata.get("correction_conflicts", ())),
        ),
        method=proposal.method,
        tracking_range=(proposal.start_frame, proposal.end_frame),
        metadata=dict(proposal.metadata),
    )
