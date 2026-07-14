import numpy as np

from epicure.tracking_transaction import (
    TrackingProposal,
    exclude_border_cells,
    prepare_tracking_result,
)


def test_tracking_proposal_preserves_frames_and_identities_outside_its_range():
    labels = np.zeros((4, 8, 8), dtype=np.uint32)

    # An unrelated outside track already owns the proposal-local ID 1.
    labels[0, 6, 6] = 1

    # Two tracks cross opposite sides of the selected range.
    labels[0, 1:3, 1:3] = 10
    labels[1, 1:3, 1:3] = 10
    labels[2, 4:6, 4:6] = 20
    labels[3, 4:6, 4:6] = 20

    source = labels[1:3].copy()
    proposed = np.zeros_like(source)
    proposed[0, source[0] == 10] = 1
    proposed[1, source[1] == 20] = 2

    result = prepare_tracking_result(
        labels,
        graph={},
        proposal=TrackingProposal(
            start_frame=1,
            end_frame=2,
            source_labels=source,
            labels=proposed,
            graph={},
            method="deterministic-test",
            metadata={"gap_repairs": ({"provenance": "LapTrack-gap"},)},
        ),
    )

    np.testing.assert_array_equal(result.labels[0], labels[0])
    np.testing.assert_array_equal(result.labels[3], labels[3])
    assert set(np.unique(result.labels[1])) == {0, 10}
    assert set(np.unique(result.labels[2])) == {0, 20}
    assert result.conflicts == ()
    assert result.metadata == {
        "gap_repairs": ({"provenance": "LapTrack-gap"},)
    }


def test_tracking_proposal_reconciles_relationships_crossing_the_range_boundary():
    labels = np.zeros((4, 8, 8), dtype=np.uint32)
    labels[0, 1, 1] = 7
    labels[0, 6, 1] = 8
    labels[1, 1, 2] = 10
    labels[1, 6, 2] = 30
    labels[3, 1, 6] = 40
    labels[3, 2, 6] = 50

    # Border exclusion removed detection 30 before the tracker saw this range.
    source = labels[1:3].copy()
    source[source == 30] = 0
    proposed = np.zeros_like(source)
    proposed[source == 10] = 1

    result = prepare_tracking_result(
        labels,
        graph={10: [7], 30: [8], 50: [40]},
        proposal=TrackingProposal(
            start_frame=1,
            end_frame=2,
            source_labels=source,
            labels=proposed,
            graph={},
            method="deterministic-test",
        ),
    )

    assert result.graph == {10: [7], 50: [40]}
    assert len(result.conflicts) == 1
    assert result.conflicts[0].kind == "range-boundary-relationship"
    assert result.conflicts[0].endpoints == (30, 8)


def test_border_exclusion_uses_one_shared_pixel_distance_rule():
    labels = np.zeros((1, 9, 9), dtype=np.uint32)
    labels[0, 0:2, 4] = 1
    labels[0, 1:3, 6] = 2
    labels[0, 3:5, 3:5] = 3

    excluded = exclude_border_cells(labels, border_size=1)

    assert set(np.unique(excluded)) == {0, 3}
    np.testing.assert_array_equal(labels[0, 3:5, 3:5], excluded[0, 3:5, 3:5])


def test_tracking_proposal_converts_divisions_to_final_epicure_ids():
    labels = np.zeros((2, 8, 8), dtype=np.uint32)
    labels[0, 2:6, 2:6] = 100
    labels[1, 2:4, 2:5] = 200
    labels[1, 4:6, 3:6] = 300
    proposed = np.zeros_like(labels)
    proposed[0, labels[0] == 100] = 1
    proposed[1, labels[1] == 200] = 2
    proposed[1, labels[1] == 300] = 3

    result = prepare_tracking_result(
        labels,
        graph={},
        proposal=TrackingProposal(
            start_frame=0,
            end_frame=1,
            source_labels=labels,
            labels=proposed,
            graph={2: [1], 3: [1]},
            method="division-test",
        ),
    )

    assert result.graph == {200: [100], 300: [100]}
