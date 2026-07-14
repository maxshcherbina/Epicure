import numpy as np
import pytest

from epicure.appose_trackastra import (
    Association,
    Detection,
    Division,
    TrackAstraResult,
)
from epicure.epicuring import EpiCure
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

    assert tracking.track_choice.findText("TrackAstra") >= 0
    tracking.track_choice.setCurrentText("TrackAstra")

    assert not tracking.drift_correction.isChecked()
    assert not tracking.drift_correction.isEnabled()
    assert not tracking.drift_radius.isEnabled()
    assert not tracking.gTrackAstra.isHidden()

    tracking.track_choice.setCurrentText("Laptrack-Centroids")

    assert tracking.drift_correction.isEnabled()
    assert tracking.drift_radius.isEnabled()
    assert tracking.drift_correction.isChecked()
    assert tracking.drift_radius.text() == "73"


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
    assert tracking.tracking_method_metadata == {
        "method": "TrackAstra",
        "range": (1, 2),
    }
    np.testing.assert_array_equal(tracking.track_data, tracking.tracklayer.data)
