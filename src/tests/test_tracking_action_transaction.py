import csv

import numpy as np
import pytest

from epicure.appose_trackastra import (
    Association,
    Detection,
    Division,
    TrackAstraResult,
)
from epicure.epicuring import EpiCure
from epicure.hybrid_tracking import GapRepair
from epicure.tracking_transaction import TrackingProposal


def _synthetic_epicure(make_napari_viewer, tmp_path):
    viewer = make_napari_viewer()
    epic = EpiCure(viewer)
    movie_layer = viewer.add_image(
        np.zeros((4, 10, 10), dtype=np.uint8), name="Synthetic movie"
    )
    epic.movie_from_layer(movie_layer, str(tmp_path / "synthetic.tif"))
    epic.set_epithelia(False)

    labels = np.zeros((4, 10, 10), dtype=np.uint32)
    labels[0, 2:4, 2:4] = 10
    labels[1, 2:4, 2:4] = 10
    labels[1, 5:7, 5:7] = 30
    labels[2, 5:7, 5:7] = 31
    labels[2, 6:8, 2:4] = 20
    labels[3, 6:8, 2:4] = 20
    labels[0, 0:2, 8] = 80
    labels[3, 1:3, 8] = 81
    labels[1, 0:2, 8] = 90
    labels[2, 1:3, 8] = 91

    segmentation_layer = viewer.add_labels(labels, name="Synthetic segmentation")
    epic.go_epicure(
        str(tmp_path / "epics"),
        {"File": "synthetic", "Layer": segmentation_layer},
    )
    return epic


def test_track_action_commits_a_deterministic_proposal_atomically(
    make_napari_viewer, tmp_path
):
    epic = _synthetic_epicure(make_napari_viewer, tmp_path)
    tracking = epic.tracking
    before = epic.seg.copy()

    epic.inspecting.add_event((0, 2, 2), 10, "extrusion", force=True)
    extrusion_ids = tuple(epic.inspecting.get_events_from_type("extrusion"))

    def deterministic_adapter(start_frame, end_frame, source_labels):
        assert (start_frame, end_frame) == (1, 2)
        assert 90 not in source_labels
        assert 91 not in source_labels
        proposed = np.zeros_like(source_labels)
        proposed[0, source_labels[0] == 10] = 1
        proposed[0, source_labels[0] == 30] = 2
        proposed[1, source_labels[1] == 31] = 2
        proposed[1, source_labels[1] == 20] = 3
        return TrackingProposal(
            start_frame=start_frame,
            end_frame=end_frame,
            source_labels=source_labels,
            labels=proposed,
            graph={},
            method="deterministic-test",
        )

    tracking.register_tracking_method("Laptrack-Centroids", deterministic_adapter)
    tracking.frame_range.setChecked(True)
    tracking.start_frame.setValue(1)
    tracking.end_frame.setValue(2)
    epic.editing.border_size.setText("1")

    tracking.do_tracking()

    np.testing.assert_array_equal(epic.seg[0], before[0])
    np.testing.assert_array_equal(epic.seg[3], before[3])
    assert 90 not in epic.seg[1]
    assert 91 not in epic.seg[2]
    assert set(np.unique(epic.seg[1])) == {0, 10, 30}
    assert set(np.unique(epic.seg[2])) == {0, 20, 30}
    assert tuple(epic.inspecting.get_events_from_type("extrusion")) == extrusion_ids
    np.testing.assert_array_equal(tracking.track_data, tracking.tracklayer.data)


def test_track_action_rolls_back_when_the_tracking_adapter_fails(
    make_napari_viewer, tmp_path
):
    epic = _synthetic_epicure(make_napari_viewer, tmp_path)
    tracking = epic.tracking
    epic.inspecting.add_event((0, 2, 2), 10, "extrusion", force=True)
    tracking.graph = {20: [10]}
    tracking.tracking_conflicts = ["existing conflict"]
    tracking.correction_ledger = {"protected": [(0, 10)]}

    before_labels = epic.seg.copy()
    before_tracks = tracking.track_data.copy()
    before_graph = tracking.graph.copy()
    before_events = epic.inspecting.events.data.copy()
    before_event_types = {
        name: tuple(ids) for name, ids in epic.inspecting.event_types.items()
    }

    def failed_adapter(start_frame, end_frame, source_labels):
        raise RuntimeError("runner failed")

    tracking.register_tracking_method("Laptrack-Centroids", failed_adapter)

    with pytest.raises(RuntimeError, match="runner failed"):
        tracking.do_tracking()

    np.testing.assert_array_equal(epic.seg, before_labels)
    np.testing.assert_array_equal(tracking.track_data, before_tracks)
    assert tracking.graph == before_graph
    np.testing.assert_array_equal(epic.inspecting.events.data, before_events)
    assert {
        name: tuple(ids) for name, ids in epic.inspecting.event_types.items()
    } == before_event_types
    assert tracking.tracking_conflicts == ["existing conflict"]
    assert tracking.correction_ledger == {"protected": [(0, 10)]}


def test_track_action_rejects_a_malformed_proposal_without_changing_state(
    make_napari_viewer, tmp_path
):
    epic = _synthetic_epicure(make_napari_viewer, tmp_path)
    tracking = epic.tracking
    before_labels = epic.seg.copy()
    before_tracks = tracking.track_data.copy()

    def malformed_adapter(start_frame, end_frame, source_labels):
        return TrackingProposal(
            start_frame=start_frame,
            end_frame=end_frame,
            source_labels=source_labels,
            labels=np.zeros_like(source_labels),
            graph={},
            method="malformed-test",
        )

    tracking.register_tracking_method("Laptrack-Centroids", malformed_adapter)

    with pytest.raises(ValueError, match="retain every source detection"):
        tracking.do_tracking()

    np.testing.assert_array_equal(epic.seg, before_labels)
    np.testing.assert_array_equal(tracking.track_data, before_tracks)


def test_track_action_rejects_a_proposal_that_rewrites_authoritative_detections(
    make_napari_viewer, tmp_path
):
    epic = _synthetic_epicure(make_napari_viewer, tmp_path)
    tracking = epic.tracking
    before_labels = epic.seg.copy()

    def source_rewriting_adapter(start_frame, end_frame, source_labels):
        rewritten = source_labels.copy()
        rewritten[rewritten == 10] = 0
        return TrackingProposal(
            start_frame=start_frame,
            end_frame=end_frame,
            source_labels=rewritten,
            labels=rewritten.copy(),
            graph={},
            method="source-rewriting-test",
        )

    tracking.register_tracking_method("Laptrack-Centroids", source_rewriting_adapter)

    with pytest.raises(ValueError, match="authoritative source labels"):
        tracking.do_tracking()

    np.testing.assert_array_equal(epic.seg, before_labels)


def test_track_action_restores_all_state_when_commit_side_effects_fail(
    make_napari_viewer, tmp_path
):
    epic = _synthetic_epicure(make_napari_viewer, tmp_path)
    tracking = epic.tracking
    epic.inspecting.add_event((0, 2, 2), 10, "extrusion", force=True)
    tracking.graph = {20: [10]}
    tracking.tracking_conflicts = ["existing conflict"]
    tracking.correction_ledger = {"protected": [(0, 10)]}

    before_labels = epic.seg.copy()
    before_tracks = tracking.track_data.copy()
    before_graph = tracking.graph.copy()
    before_events = epic.inspecting.events.data.copy()
    before_event_types = {
        name: tuple(ids) for name, ids in epic.inspecting.event_types.items()
    }

    def valid_adapter(start_frame, end_frame, source_labels):
        return TrackingProposal(
            start_frame=start_frame,
            end_frame=end_frame,
            source_labels=source_labels,
            labels=source_labels.copy(),
            graph={},
            method="commit-failure-test",
        )

    def failed_inspect_update():
        epic.inspecting.reset_all_events()
        raise RuntimeError("inspect update failed")

    tracking.register_tracking_method("Laptrack-Centroids", valid_adapter)
    epic.updates_after_tracking = failed_inspect_update

    with pytest.raises(RuntimeError, match="inspect update failed"):
        tracking.do_tracking()

    np.testing.assert_array_equal(epic.seg, before_labels)
    np.testing.assert_array_equal(tracking.track_data, before_tracks)
    assert tracking.graph == before_graph
    np.testing.assert_array_equal(epic.inspecting.events.data, before_events)
    assert {
        name: tuple(ids) for name, ids in epic.inspecting.event_types.items()
    } == before_event_types
    assert tracking.tracking_conflicts == ["existing conflict"]
    assert tracking.correction_ledger == {"protected": [(0, 10)]}


def test_laptrack_overlap_runs_through_the_range_safe_transaction(
    make_napari_viewer, tmp_path
):
    epic = _synthetic_epicure(make_napari_viewer, tmp_path)
    tracking = epic.tracking
    before = epic.seg.copy()
    tracking.track_choice.setCurrentText("Laptrack-Overlaps")
    tracking.min_iou.setText("0.1")
    tracking.split_cost.setText("0")
    tracking.merg_cost.setText("0")
    tracking.frame_range.setChecked(True)
    tracking.start_frame.setValue(1)
    tracking.end_frame.setValue(2)
    epic.editing.border_size.setText("1")

    tracking.do_tracking()

    np.testing.assert_array_equal(epic.seg[0], before[0])
    np.testing.assert_array_equal(epic.seg[3], before[3])
    assert 90 not in epic.seg[1]
    assert 91 not in epic.seg[2]
    assert epic.seg[1, 5, 5] == epic.seg[2, 5, 5]
    assert epic.seg[1, 2, 2] == 10
    assert epic.seg[2, 6, 2] == 20


def test_laptrack_centroids_runs_through_the_range_safe_transaction(
    make_napari_viewer, tmp_path
):
    epic = _synthetic_epicure(make_napari_viewer, tmp_path)
    tracking = epic.tracking
    before = epic.seg.copy()
    tracking.track_choice.setCurrentText("Laptrack-Centroids")
    tracking.max_dist.setText("5")
    tracking.splitting_cost.setText("0")
    tracking.merging_cost.setText("0")
    tracking.gap_frames_line.setText("1")
    tracking.check_penalties.setChecked(False)
    tracking.frame_range.setChecked(True)
    tracking.start_frame.setValue(1)
    tracking.end_frame.setValue(2)
    epic.editing.border_size.setText("1")

    tracking.do_tracking()

    np.testing.assert_array_equal(epic.seg[0], before[0])
    np.testing.assert_array_equal(epic.seg[3], before[3])
    assert 90 not in epic.seg[1]
    assert 91 not in epic.seg[2]
    assert epic.seg[1, 5, 5] == epic.seg[2, 5, 5]
    assert epic.seg[1, 2, 2] == 10
    assert epic.seg[2, 6, 2] == 20
    assert [conflict.kind for conflict in tracking.tracking_conflicts] == [
        "range-boundary-identity"
    ]


def test_trackastra_selector_inhibits_drift_and_restores_laptrack_state(
    make_napari_viewer, tmp_path
):
    epic = _synthetic_epicure(make_napari_viewer, tmp_path)
    tracking = epic.tracking
    tracking.drift_correction.setChecked(True)
    tracking.drift_radius.setText("73")
    tracking.gap_frames_line.setText("4")

    assert tracking.track_choice.findText("TrackAstra") >= 0
    tracking.track_choice.setCurrentText("TrackAstra")

    assert not tracking.drift_correction.isChecked()
    assert not tracking.drift_correction.isEnabled()
    assert not tracking.drift_radius.isEnabled()
    assert not tracking.gTrackAstra.isHidden()
    assert not tracking.gap_frames_line.isHidden()
    assert tracking.get_current_settings()["Gap-closing frames"] == "4"

    tracking.track_choice.setCurrentText("Laptrack-Centroids")

    assert tracking.drift_correction.isEnabled()
    assert tracking.drift_radius.isEnabled()
    assert tracking.drift_correction.isChecked()
    assert tracking.drift_radius.text() == "73"
    assert tracking.gap_frames_line.text() == "4"


def test_trackastra_runs_through_normal_action_with_divisions_and_singletons(
    make_napari_viewer, tmp_path
):
    epic = _synthetic_epicure(make_napari_viewer, tmp_path)
    tracking = epic.tracking
    before = epic.seg.copy()
    captured = {}

    def fake_runner(movie, segmentations, *, start_frame, **_kwargs):
        captured["movie"] = movie.copy()
        captured["segmentations"] = segmentations.copy()
        captured["start_frame"] = start_frame
        return TrackAstraResult(
            schema_version=1,
            trackastra_version="0.5.3",
            model="general_2d",
            device="cpu",
            detections=(
                Detection(1, 10, 2.5, 2.5),
                Detection(1, 30, 5.5, 5.5),
                Detection(2, 20, 6.5, 2.5),
                Detection(2, 31, 5.5, 5.5),
            ),
            associations=(
                Association(1, 30, 2, 20, 0.91),
                Association(1, 30, 2, 31, 0.97),
            ),
            divisions=(Division(1, 30, 2, 20, 31, 0.91, 0.97),),
        )

    tracking._trackastra_runner = fake_runner
    tracking.track_choice.setCurrentText("TrackAstra")
    tracking.frame_range.setChecked(True)
    tracking.start_frame.setValue(1)
    tracking.end_frame.setValue(2)
    epic.editing.border_size.setText("1")

    tracking.do_tracking()

    assert captured["start_frame"] == 1
    np.testing.assert_array_equal(captured["movie"], epic.img[1:3])
    assert 90 not in captured["segmentations"]
    assert 91 not in captured["segmentations"]
    np.testing.assert_array_equal(epic.seg[0], before[0])
    np.testing.assert_array_equal(epic.seg[3], before[3])
    assert epic.seg[1, 2, 2] == 10  # unmatched detection restored as singleton
    assert set(tracking.graph) == {20, 31}
    assert tracking.graph[20] == [30]
    assert tracking.graph[31] == [30]
    assert tracking.tracking_method_metadata["method"] == "TrackAstra"
    assert tracking.tracking_method_metadata["range"] == (1, 2)
    assert tracking.tracking_method_metadata["trackastra_version"] == "0.5.3"
    assert tracking.tracking_method_metadata["trackastra_device"] == "cpu"
    assert len(tracking.tracking_method_metadata["trackastra_associations"]) == 2
    assert len(tracking.tracking_method_metadata["trackastra_divisions"]) == 1
    assert tracking.tracking_method_metadata["gap_repairs"] == ()
    np.testing.assert_array_equal(tracking.track_data, tracking.tracklayer.data)


def test_trackastra_gap_repair_joins_tracklets_and_keeps_review_provenance(
    make_napari_viewer, tmp_path
):
    epic = _synthetic_epicure(make_napari_viewer, tmp_path)
    labels = np.zeros((4, 10, 10), dtype=np.uint32)
    labels[0, 2:4, 2:4] = 1
    labels[3, 3:5, 2:4] = 2
    result = TrackAstraResult(
        schema_version=1,
        trackastra_version="0.5.3",
        model="general_2d",
        device="cpu",
        detections=(Detection(0, 1, 2.5, 2.5), Detection(3, 2, 3.5, 2.5)),
        associations=(),
        divisions=(),
    )
    repair = GapRepair(
        source=(0, 1),
        target=(3, 2),
        missing_frames=2,
        distance=1.0,
        distance_per_frame=1.0 / 3.0,
        area_ratio=1.0,
        source_y=2.5,
        source_x=2.5,
        target_y=3.5,
        target_x=2.5,
    )

    proposal = epic.tracking.proposal_from_trackastra_result(
        0, 3, labels, result, gap_repairs=(repair,)
    )

    assert proposal.labels[0, 2, 2] == proposal.labels[3, 3, 2]
    assert proposal.metadata["gap_repairs"][0]["provenance"] == "LapTrack-gap"
    assert proposal.metadata["gap_repairs"][0]["missing_frames"] == 2


def test_trackastra_gap_pass_uses_shared_laptrack_gap_setting(
    make_napari_viewer, tmp_path
):
    epic = _synthetic_epicure(make_napari_viewer, tmp_path)
    labels = np.zeros((4, 10, 10), dtype=np.uint32)
    labels[0, 2:4, 2:4] = 1
    labels[3, 3:5, 2:4] = 2
    result = TrackAstraResult(
        schema_version=1,
        trackastra_version="0.5.3",
        model="general_2d",
        device="cpu",
        detections=(Detection(0, 1, 2.5, 2.5), Detection(3, 2, 3.5, 2.5)),
        associations=(),
        divisions=(),
    )
    epic.tracking.max_dist.setText("15")
    epic.tracking.gap_frames_line.setText("5")

    repairs = epic.tracking.trackastra_gap_repairs(0, labels, result)

    assert len(repairs) == 1
    assert repairs[0].source == (0, 1)
    assert repairs[0].target == (3, 2)
    epic.tracking.gap_frames_line.setText("1")
    assert epic.tracking.trackastra_gap_repairs(0, labels, result) == ()


def test_hybrid_tracking_save_reopen_and_lineage_csv_use_committed_state(
    make_napari_viewer, tmp_path
):
    epic = _synthetic_epicure(make_napari_viewer, tmp_path)
    tracking = epic.tracking
    tracking.graph = {20: [30], 31: [30]}
    tracking.tracklayer.graph = tracking.graph
    tracking.tracking_method_metadata = {
        "method": "TrackAstra",
        "range": (1, 2),
        "trackastra_version": "0.5.3",
        "trackastra_device": "cpu",
        "gap_repairs": (
            {
                "source": (0, 10),
                "target": (3, 20),
                "missing_frames": 2,
                "provenance": "LapTrack-gap",
            },
        ),
    }
    tracking.correction_ledger = [
        {
            "kind": "association",
            "decision": "protected",
            "source": (0, 10),
            "target": (1, 10),
        }
    ]
    tracking.tracking_conflicts = [{"kind": "boundary", "track": 10}]

    expected_labels = epic.seg.copy()
    expected_tracks = tracking.track_data.copy()
    expected_graph = tracking.graph.copy()
    epic.save_epicures()

    lineage_path = tmp_path / "epics" / "synthetic_lineage.csv"
    with lineage_path.open(newline="") as infile:
        rows = {int(row["label"]): row for row in csv.DictReader(infile)}
    assert set(rows) == set(int(label) for label in expected_tracks[:, 0])
    assert rows[30] == {"label": "30", "t1": "1", "t2": "1", "parent": "0"}
    assert rows[20] == {"label": "20", "t1": "2", "t2": "3", "parent": "30"}
    assert rows[31] == {"label": "31", "t1": "2", "t2": "2", "parent": "30"}

    reopened_viewer = make_napari_viewer()
    reopened = EpiCure(reopened_viewer)
    reopened_movie = reopened_viewer.add_image(
        np.zeros((4, 10, 10), dtype=np.uint8), name="Synthetic movie"
    )
    reopened.movie_from_layer(reopened_movie, str(tmp_path / "synthetic.tif"))
    reopened.set_epithelia(False)
    reopened.go_epicure(
        str(tmp_path / "epics"),
        str(tmp_path / "epics" / "synthetic_labels.tif"),
    )

    np.testing.assert_array_equal(reopened.seg, expected_labels)
    np.testing.assert_array_equal(reopened.tracking.track_data, expected_tracks)
    np.testing.assert_array_equal(
        reopened.tracking.tracklayer.data, expected_tracks
    )
    assert reopened.tracking.graph == expected_graph
    assert reopened.tracking.tracklayer.graph == expected_graph
    assert reopened.tracking.tracking_method_metadata == tracking.tracking_method_metadata
    assert reopened.tracking.correction_ledger == tracking.correction_ledger
    assert reopened.tracking.tracking_conflicts == tracking.tracking_conflicts


def test_legacy_project_without_tracking_state_keeps_empty_defaults(
    make_napari_viewer, tmp_path
):
    epic = _synthetic_epicure(make_napari_viewer, tmp_path)

    epic.read_epidata({"Graph": {20: [30]}})

    assert epic.tracking.tracking_method_metadata == {}
    assert epic.tracking.correction_ledger == []
    assert epic.tracking.tracking_conflicts == []


def test_manual_join_split_and_swap_record_detection_key_corrections(
    make_napari_viewer, tmp_path
):
    epic = _synthetic_epicure(make_napari_viewer, tmp_path)
    tracking = epic.tracking

    epic.editing.tracks_temporal_merging(
        80, np.array((0, 0, 8)), 90, np.array((1, 0, 8))
    )
    assert {
        "kind": "association",
        "decision": "protected",
        "source": (0, 80),
        "target": (1, 80),
    } in tracking.correction_ledger

    split_label = epic.split_track(10, 1)
    assert {
        "kind": "association",
        "decision": "forbidden",
        "source": (0, 10),
        "target": (1, split_label),
    } in tracking.correction_ledger

    for frame in range(3):
        epic.seg[frame, 4:6, 0:2] = 40
        epic.seg[frame, 7:9, 4:6] = 50
    epic.seglayer.data = epic.seg
    tracking.reset_tracks()
    epic.swap_tracks(40, 50, 1)
    assert {
        "kind": "association",
        "decision": "protected",
        "source": (0, 40),
        "target": (1, 40),
    } in tracking.correction_ledger
    assert {
        "kind": "association",
        "decision": "protected",
        "source": (0, 50),
        "target": (1, 50),
    } in tracking.correction_ledger


def test_association_corrections_replace_remove_and_override_fresh_edges(
    make_napari_viewer, tmp_path
):
    epic = _synthetic_epicure(make_napari_viewer, tmp_path)
    tracking = epic.tracking
    labels = np.zeros((2, 10, 10), dtype=np.uint32)
    labels[0, 2:4, 2:4] = 1
    labels[0, 6:8, 2:4] = 2
    labels[1, 2:4, 3:5] = 3
    labels[1, 6:8, 3:5] = 4
    result = TrackAstraResult(
        schema_version=1,
        trackastra_version="0.5.3",
        model="general_2d",
        device="cpu",
        detections=(
            Detection(1, 1, 2.5, 2.5),
            Detection(1, 2, 6.5, 2.5),
            Detection(2, 3, 2.5, 3.5),
            Detection(2, 4, 6.5, 3.5),
        ),
        associations=(
            Association(1, 1, 2, 3, 0.9),
            Association(1, 2, 2, 4, 0.9),
        ),
        divisions=(),
    )

    tracking.set_association_correction((1, 1), (2, 4), "protected")
    proposal = tracking.proposal_from_trackastra_result(1, 2, labels, result)

    assert proposal.labels[0, 2, 2] == proposal.labels[1, 6, 3]
    assert proposal.labels[0, 2, 2] != proposal.labels[1, 2, 3]
    assert proposal.labels[0, 6, 2] != proposal.labels[1, 6, 3]
    assert proposal.metadata["replayed_association_corrections"] == (
        {
            "kind": "association",
            "decision": "protected",
            "source": (1, 1),
            "target": (2, 4),
        },
    )

    tracking.set_association_correction((1, 1), (2, 4), "forbidden")
    assert len(tracking.correction_ledger) == 1
    forbidden = tracking.proposal_from_trackastra_result(1, 2, labels, result)
    assert forbidden.labels[0, 2, 2] != forbidden.labels[1, 6, 3]
    tracking.remove_association_correction((1, 1), (2, 4))
    assert tracking.correction_ledger == []


def test_forbidden_association_removes_a_proposed_gap_repair(
    make_napari_viewer, tmp_path
):
    epic = _synthetic_epicure(make_napari_viewer, tmp_path)
    tracking = epic.tracking
    labels = np.zeros((3, 10, 10), dtype=np.uint32)
    labels[0, 2:4, 2:4] = 1
    labels[2, 3:5, 2:4] = 2
    result = TrackAstraResult(
        schema_version=1,
        trackastra_version="0.5.3",
        model="general_2d",
        device="cpu",
        detections=(Detection(0, 1, 2.5, 2.5), Detection(2, 2, 3.5, 2.5)),
        associations=(),
        divisions=(),
    )
    repair = GapRepair(
        source=(0, 1),
        target=(2, 2),
        missing_frames=1,
        distance=1.0,
        distance_per_frame=0.5,
        area_ratio=1.0,
        source_y=2.5,
        source_x=2.5,
        target_y=3.5,
        target_x=2.5,
    )
    tracking.set_association_correction((0, 1), (2, 2), "forbidden")

    proposal = tracking.proposal_from_trackastra_result(
        0, 2, labels, result, gap_repairs=(repair,)
    )

    assert proposal.labels[0, 2, 2] != proposal.labels[2, 3, 2]
    assert proposal.metadata["gap_repairs"] == ()
