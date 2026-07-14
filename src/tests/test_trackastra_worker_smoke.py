"""Opt-in real TrackAstra ARM64 smoke test.

Run explicitly with ``EPICURE_RUN_TRACKASTRA_SMOKE=1 pytest -q``.  The model and
isolated environment are intentionally not provisioned during the routine suite.
"""

import os

import numpy as np
import pytest

from epicure.appose_trackastra import (
    TRACKASTRA_MODEL,
    TRACKASTRA_VERSION,
    run_trackastra,
)


pytestmark = pytest.mark.skipif(
    os.environ.get("EPICURE_RUN_TRACKASTRA_SMOKE") != "1",
    reason="set EPICURE_RUN_TRACKASTRA_SMOKE=1 to provision the real ARM64 worker",
)


def test_real_arm64_worker_loads_model_and_returns_division_aware_tables():
    rng = np.random.default_rng(42)
    movie = rng.integers(0, 20, size=(4, 64, 64), dtype=np.uint8)
    segmentations = np.zeros(movie.shape, dtype=np.uint16)

    segmentations[0, 24:40, 24:40] = 1
    segmentations[1, 23:39, 24:40] = 2
    segmentations[2, 19:31, 18:30] = 3
    segmentations[2, 31:43, 34:46] = 4
    segmentations[3, 18:30, 17:29] = 5
    segmentations[3, 32:44, 35:47] = 6
    movie[segmentations > 0] = 180

    result = run_trackastra(movie, segmentations, start_frame=20)

    assert result.trackastra_version == TRACKASTRA_VERSION
    assert result.model == TRACKASTRA_MODEL
    assert result.device in {"mps", "cpu"}
    assert {(item.frame, item.label) for item in result.detections} == {
        (20, 1),
        (21, 2),
        (22, 3),
        (22, 4),
        (23, 5),
        (23, 6),
    }
    assert all(isinstance(item.score, float) for item in result.associations)
    assert isinstance(result.divisions, tuple)
