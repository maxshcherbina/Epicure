import numpy as np
import pandas as pd
import pytest

from epicure.appose_trackastra import Association, Detection, Division, TrackAstraResult
from epicure.hybrid_tracking import find_constrained_gap_repairs


def _result(detections, associations=(), divisions=()):
    return TrackAstraResult(
        schema_version=1,
        trackastra_version="0.5.3",
        model="general_2d",
        device="cpu",
        detections=tuple(detections),
        associations=tuple(associations),
        divisions=tuple(divisions),
    )


def _labels_for(detections, frames=7):
    labels = np.zeros((frames, 24, 24), dtype=np.uint16)
    for detection in detections:
        y = int(detection.y)
        x = int(detection.x)
        labels[detection.frame, y : y + 2, x : x + 2] = detection.label
    return labels


def _laptrack_table(*rows):
    return pd.DataFrame(
        rows,
        columns=["track_id", "frame", "label", "centroid-0", "centroid-1"],
    )


@pytest.mark.parametrize("missing_frames", [1, 2, 3, 4])
def test_gap_repair_accepts_each_supported_missing_frame_count(missing_frames):
    target_frame = missing_frames + 1
    detections = (
        Detection(0, 1, 4.5, 4.5),
        Detection(target_frame, 2, 5.5, 4.5),
    )
    laptrack = _laptrack_table(
        (0, 0, 1, 4.5, 4.5),
        (0, target_frame, 2, 5.5, 4.5),
    )

    repairs = find_constrained_gap_repairs(
        _result(detections),
        _labels_for(detections),
        laptrack,
        gap_frames=5,
    )

    assert len(repairs) == 1
    assert repairs[0].source == (0, 1)
    assert repairs[0].target == (target_frame, 2)
    assert repairs[0].missing_frames == missing_frames
    assert repairs[0].provenance == "LapTrack-gap"


def test_gap_repair_value_one_disables_repairs():
    detections = (Detection(0, 1, 4.5, 4.5), Detection(2, 2, 5.5, 4.5))
    laptrack = _laptrack_table(
        (0, 0, 1, 4.5, 4.5),
        (0, 2, 2, 5.5, 4.5),
    )

    repairs = find_constrained_gap_repairs(
        _result(detections), _labels_for(detections), laptrack, gap_frames=1
    )

    assert repairs == ()


def test_gap_repair_never_replaces_adjacent_trackastra_or_division_edges():
    detections = (
        Detection(0, 1, 4.5, 4.5),
        Detection(1, 2, 5.5, 4.5),
        Detection(1, 3, 4.5, 5.5),
        Detection(3, 4, 6.5, 4.5),
    )
    associations = (
        Association(0, 1, 1, 2, 0.95),
        Association(0, 1, 1, 3, 0.90),
    )
    divisions = (Division(0, 1, 1, 2, 3, 0.95, 0.90),)
    laptrack = _laptrack_table(
        (0, 0, 1, 4.5, 4.5),
        (0, 3, 4, 6.5, 4.5),
    )

    repairs = find_constrained_gap_repairs(
        _result(detections, associations, divisions),
        _labels_for(detections),
        laptrack,
        gap_frames=5,
    )

    assert repairs == ()


def test_gap_repair_keeps_one_to_one_topology_for_competing_candidates():
    detections = (
        Detection(0, 1, 4.5, 4.5),
        Detection(0, 2, 10.5, 10.5),
        Detection(2, 3, 5.5, 4.5),
    )
    # A defensive malformed LapTrack table nominates the same target twice.
    # The shorter candidate wins deterministically.
    laptrack = _laptrack_table(
        (0, 0, 1, 4.5, 4.5),
        (0, 2, 3, 5.5, 4.5),
        (1, 0, 2, 10.5, 10.5),
        (1, 2, 3, 5.5, 4.5),
    )

    repairs = find_constrained_gap_repairs(
        _result(detections),
        _labels_for(detections),
        laptrack,
        gap_frames=5,
    )

    assert len(repairs) == 1
    assert repairs[0].source == (0, 1)
    assert repairs[0].target == (2, 3)


def test_gap_repair_respects_forbidden_and_protected_association_decisions():
    detections = (
        Detection(0, 1, 4.5, 4.5),
        Detection(2, 2, 5.5, 4.5),
        Detection(2, 3, 10.5, 10.5),
    )
    edge = ((0, 1), (2, 2))
    laptrack = _laptrack_table(
        (0, 0, 1, 4.5, 4.5),
        (0, 2, 2, 5.5, 4.5),
    )
    result = _result(detections)
    labels = _labels_for(detections)

    assert find_constrained_gap_repairs(
        result,
        labels,
        laptrack,
        gap_frames=5,
        forbidden_edges=(edge,),
    ) == ()
    assert find_constrained_gap_repairs(
        result,
        labels,
        laptrack,
        gap_frames=5,
        protected_edges=(((0, 1), (2, 3)),),
    ) == ()
    assert len(
        find_constrained_gap_repairs(
            result,
            labels,
            laptrack,
            gap_frames=5,
            protected_edges=(edge,),
        )
    ) == 1
