"""Opt-in full reference-movie qualification for the ARM64 hybrid workflow."""

import json
import os
from pathlib import Path
import time

import napari
import numpy as np
import pytest
import tifffile

from epicure.epicuring import EpiCure
from epicure.tracking_transaction import exclude_border_cells


pytestmark = pytest.mark.skipif(
    os.environ.get("EPICURE_RUN_TRACKASTRA_FULL") != "1",
    reason="set EPICURE_RUN_TRACKASTRA_FULL=1 for the 101-frame ARM64 run",
)


RAW = Path("/Volumes/Lab SSD/Workshop/small_crop23-123_8bit.tif")
MASKS = Path("/Volumes/Lab SSD/Workshop/small_crop23-123_8bit.tif_cellpose.tif")


def _epicure_from_arrays(viewer, movie, masks, outdir):
    epic = EpiCure(viewer)
    movie_layer = viewer.add_image(movie, name="Reference movie")
    epic.movie_from_layer(movie_layer, str(RAW))
    epic.set_epithelia(False)
    segmentation_layer = viewer.add_labels(masks, name="Reference segmentation")
    epic.go_epicure(
        str(outdir),
        {"File": str(MASKS), "Layer": segmentation_layer},
    )
    return epic


def test_full_reference_movie_hybrid_trackastra_save_reopen(tmp_path):
    if not RAW.exists() or not MASKS.exists():
        pytest.skip("reference movie is not mounted")
    movie = tifffile.imread(RAW)
    masks = tifffile.imread(MASKS)
    retained = exclude_border_cells(masks, 1)
    retained_detections = sum(
        len(np.unique(frame[frame > 0])) for frame in retained
    )

    viewer = napari.Viewer(show=False)
    epic = _epicure_from_arrays(viewer, movie, masks, tmp_path / "epics")
    tracking = epic.tracking
    tracking.track_choice.setCurrentText("TrackAstra")
    tracking.gap_frames_line.setText("5")
    epic.editing.border_size.setText("1")

    started = time.perf_counter()
    tracking.do_tracking()
    runtime_seconds = time.perf_counter() - started

    metadata = tracking.tracking_method_metadata
    divisions = len(
        {
            tuple(parents)
            for parents in (tracking.graph or {}).values()
            if len(parents) == 1
        }
    )
    metrics = {
        "retained_detections": retained_detections,
        "track_rows": int(tracking.track_data.shape[0]),
        "trackastra_associations": len(metadata["trackastra_associations"]),
        "trackastra_divisions": len(metadata["trackastra_divisions"]),
        "gap_repairs": len(metadata["gap_repairs"]),
        "native_division_parents": divisions,
        "runtime_seconds": runtime_seconds,
        "device": metadata["trackastra_device"],
    }
    print("TRACKASTRA_QUALIFICATION=" + json.dumps(metrics, sort_keys=True))

    assert retained_detections == 12134
    assert tracking.track_data.shape[0] == retained_detections
    assert np.count_nonzero(epic.seg) == np.count_nonzero(retained)
    assert not tracking.drift_correction.isEnabled()
    assert metadata["trackastra_device"] in {"mps", "cpu"}
    assert len(metadata["trackastra_divisions"]) > 0
    assert divisions == len(metadata["trackastra_divisions"])

    labels_before = epic.seg.copy()
    tracks_before = tracking.track_data.copy()
    graph_before = tracking.graph.copy()
    epic.save_epicures()
    viewer.close()

    reopened_viewer = napari.Viewer(show=False)
    reopened = EpiCure(reopened_viewer)
    reopened_movie = reopened_viewer.add_image(movie, name="Reference movie")
    reopened.movie_from_layer(reopened_movie, str(RAW))
    reopened.set_epithelia(False)
    reopened.go_epicure(
        str(tmp_path / "epics"),
        str(tmp_path / "epics" / "small_crop23-123_8bit_labels.tif"),
    )
    np.testing.assert_array_equal(reopened.seg, labels_before)
    np.testing.assert_array_equal(reopened.tracking.track_data, tracks_before)
    assert reopened.tracking.graph == graph_before
    assert reopened.tracking.tracking_method_metadata == metadata
    reopened_viewer.close()
