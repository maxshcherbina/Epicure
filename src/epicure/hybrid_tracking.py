"""Constraint layer for TrackAstra association plus LapTrack gap repair."""

from __future__ import annotations

from dataclasses import dataclass
from math import hypot
from typing import Iterable

import numpy as np
import pandas as pd

from epicure.appose_trackastra import TrackAstraResult


DetectionKey = tuple[int, int]
AssociationKey = tuple[DetectionKey, DetectionKey]


@dataclass(frozen=True)
class GapRepair:
    """One accepted non-adjacent association with review provenance."""

    source: DetectionKey
    target: DetectionKey
    missing_frames: int
    distance: float
    distance_per_frame: float
    area_ratio: float
    source_y: float
    source_x: float
    target_y: float
    target_x: float
    provenance: str = "LapTrack-gap"


def find_constrained_gap_repairs(
    trackastra: TrackAstraResult,
    source_labels: np.ndarray,
    laptrack_tracks: pd.DataFrame,
    *,
    gap_frames: int,
    start_frame: int = 0,
    forbidden_edges: Iterable[AssociationKey] = (),
    protected_edges: Iterable[AssociationKey] = (),
) -> tuple[GapRepair, ...]:
    """Accept only LapTrack gap pairs that do not overwrite existing decisions.

    ``gap_frames`` follows LapTrack's UI semantics: ``1`` disables gap repair,
    while ``5`` permits targets separated by at most five frames (four missing
    segmentation frames).
    """

    if int(gap_frames) != gap_frames or gap_frames < 1:
        raise ValueError("Gap-closing frames must be a positive integer")
    if gap_frames == 1:
        return ()

    labels = np.asarray(source_labels)
    if labels.ndim != 3:
        raise ValueError("Gap repair expects a 3D segmentation range")

    required_columns = {"track_id", "frame", "label"}
    if not required_columns <= set(laptrack_tracks.columns):
        raise ValueError("LapTrack gap candidates are missing required columns")

    detection_by_key = {
        (item.frame, item.label): item for item in trackastra.detections
    }
    outgoing = {
        (item.source_frame, item.source_label)
        for item in trackastra.associations
    }
    incoming = {
        (item.target_frame, item.target_label)
        for item in trackastra.associations
    }
    forbidden = set(forbidden_edges)
    protected = set(protected_edges)
    protected_sources = {source for source, _target in protected}
    protected_targets = {target for _source, target in protected}

    candidates: list[GapRepair] = []
    for _track_id, track in laptrack_tracks.groupby("track_id", sort=True):
        rows = track.sort_values(["frame", "label"]).to_dict("records")
        for source_row, target_row in zip(rows, rows[1:], strict=False):
            source = (int(source_row["frame"]), int(source_row["label"]))
            target = (int(target_row["frame"]), int(target_row["label"]))
            frame_delta = target[0] - source[0]
            edge = (source, target)
            if frame_delta < 2 or frame_delta > gap_frames:
                continue
            if source not in detection_by_key or target not in detection_by_key:
                continue
            if source in outgoing or target in incoming or edge in forbidden:
                continue
            if source in protected_sources and edge not in protected:
                continue
            if target in protected_targets and edge not in protected:
                continue

            source_detection = detection_by_key[source]
            target_detection = detection_by_key[target]
            distance = hypot(
                target_detection.y - source_detection.y,
                target_detection.x - source_detection.x,
            )
            source_area = _detection_area(labels, start_frame, source)
            target_area = _detection_area(labels, start_frame, target)
            area_ratio = max(source_area, target_area) / min(source_area, target_area)
            candidates.append(
                GapRepair(
                    source=source,
                    target=target,
                    missing_frames=frame_delta - 1,
                    distance=distance,
                    distance_per_frame=distance / frame_delta,
                    area_ratio=area_ratio,
                    source_y=source_detection.y,
                    source_x=source_detection.x,
                    target_y=target_detection.y,
                    target_x=target_detection.x,
                )
            )

    # LapTrack normally already produces one-to-one tracks. Keep this defensive
    # arbitration so malformed or merged candidate tables cannot violate the
    # hybrid topology.
    accepted: list[GapRepair] = []
    claimed_sources: set[DetectionKey] = set()
    claimed_targets: set[DetectionKey] = set()
    for candidate in sorted(
        candidates,
        key=lambda item: (item.distance, item.source, item.target),
    ):
        if candidate.source in claimed_sources or candidate.target in claimed_targets:
            continue
        accepted.append(candidate)
        claimed_sources.add(candidate.source)
        claimed_targets.add(candidate.target)
    return tuple(sorted(accepted, key=lambda item: (item.source, item.target)))


def _detection_area(
    labels: np.ndarray, start_frame: int, detection: DetectionKey
) -> int:
    frame, label = detection
    offset = frame - start_frame
    if offset < 0 or offset >= len(labels):
        raise ValueError("Gap repair detection is outside the selected range")
    area = int(np.count_nonzero(labels[offset] == label))
    if area == 0:
        raise ValueError("Gap repair detection is missing from the segmentations")
    return area
