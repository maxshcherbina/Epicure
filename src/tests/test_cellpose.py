from importlib import resources
import logging
import os
from pathlib import Path

import numpy as np
import pytest
import tifffile

from epicure.appose_cellpose import (
    CELLPOSE_DEFAULT_MODEL,
    CELLPOSE_MODELS,
    go_cellpose,
)
from epicure.start_epicuring import gui_files


def test_cellpose_model_dropdown_includes_dino_vitb(
    make_napari_viewer,
    tmp_path,
):
    viewer = make_napari_viewer()
    movie_layer = viewer.add_image(
        np.zeros((2, 32, 32), dtype=np.uint8),
        name="Raw movie",
    )

    widget, _ = gui_files(movie_layer, tmp_path / "movie.tif", None)

    assert tuple(widget.cellpose_model.choices) == CELLPOSE_MODELS
    assert "cpdino-vitb" in widget.cellpose_model.choices
    assert widget.cellpose_model.value == CELLPOSE_DEFAULT_MODEL


def test_cellpose_worker_pins_pilot_proven_dinov3_revision():
    pixi_file = resources.files("epicure.resources").joinpath(
        "pixi_cellpose.toml"
    )
    config = pixi_file.read_text()

    assert 'python = "==3.11"' in config
    assert (
        'dinov3 = { git = "https://github.com/facebookresearch/dinov3.git", '
        'rev = "346f38fee679c56a6888f91c51670fae61d364e0" }'
        in config
    )


def test_cellpose_rejects_unsupported_model_before_provisioning():
    with pytest.raises(ValueError, match="Unsupported Cellpose model"):
        go_cellpose(
            np.zeros((1, 8, 8), dtype=np.uint8),
            {"model": "not-a-real-model"},
        )


@pytest.mark.skipif(
    os.environ.get("EPICURE_RUN_CELLPOSE_DINO_SMOKE") != "1",
    reason="set EPICURE_RUN_CELLPOSE_DINO_SMOKE=1 for the real ARM64/MPS run",
)
def test_cellpose_dino_vitb_real_worker_on_mps(caplog):
    movie_path = (
        Path(__file__).parents[2]
        / "test_images"
        / "small_crop23-123_8bit.tif"
    )
    movie = tifffile.imread(movie_path)[0:1]

    with caplog.at_level(logging.INFO, logger="epicure.appose_cellpose"):
        labels = go_cellpose(
            movie,
            {
                "gpu": True,
                "model": "cpdino-vitb",
                "refine_membrane": False,
                "diameter": None,
                "flow_threshold": 0.4,
                "cellprob_threshold": 0.0,
                "min_size": 30,
            },
        )

    assert labels.shape == movie.shape
    assert labels.dtype == np.uint32
    assert labels.max() > 0
    assert any(
        "Cellpose (cpdino-vitb) initialized on mps" in record.message
        for record in caplog.records
    )
