import numpy as np
import pytest

from epicure.appose_trackastra import (
    ApposeTrackAstraWorker,
    Association,
    Detection,
    Division,
    TrackAstraRequest,
    TrackAstraWorkerError,
    run_trackastra,
)


def _movie_and_segmentations():
    movie = np.zeros((2, 5, 5), dtype=np.uint8)
    segmentations = np.zeros((2, 5, 5), dtype=np.uint16)
    segmentations[0, 1:3, 1:3] = 7
    segmentations[1, 1:2, 1:3] = 8
    segmentations[1, 2:3, 1:3] = 9
    return movie, segmentations


def test_fake_worker_contract_returns_global_detection_and_division_evidence():
    movie, segmentations = _movie_and_segmentations()
    captured = {}

    def fake_worker(request, **_kwargs):
        captured["request"] = request
        return {
            "schema_version": 1,
            "trackastra_version": "0.5.3",
            "model": "general_2d",
            "device": "mps",
            "detections": [
                [12, 7, 1.5, 1.5],
                [13, 8, 1.0, 1.5],
                [13, 9, 2.0, 1.5],
            ],
            "associations": [
                [12, 7, 13, 8, 0.95],
                [12, 7, 13, 9, 0.85],
            ],
            "divisions": [[12, 7, 13, 8, 9, 0.95, 0.85]],
        }

    result = run_trackastra(
        movie,
        segmentations,
        start_frame=12,
        worker=fake_worker,
    )

    assert captured["request"] == TrackAstraRequest(
        movie=movie,
        segmentations=segmentations,
        start_frame=12,
    )
    assert result.device == "mps"
    assert result.detections == (
        Detection(frame=12, label=7, y=1.5, x=1.5),
        Detection(frame=13, label=8, y=1.0, x=1.5),
        Detection(frame=13, label=9, y=2.0, x=1.5),
    )
    assert result.associations == (
        Association(12, 7, 13, 8, 0.95),
        Association(12, 7, 13, 9, 0.85),
    )
    assert result.divisions == (Division(12, 7, 13, 8, 9, 0.95, 0.85),)


def test_invalid_worker_response_is_rejected_without_mutating_inputs():
    movie, segmentations = _movie_and_segmentations()
    movie_before = movie.copy()
    segmentations_before = segmentations.copy()

    def fake_worker(_request, **_kwargs):
        _request.movie[:] = 255
        _request.segmentations[:] = 0
        return {
            "schema_version": 1,
            "trackastra_version": "0.5.3",
            "model": "general_2d",
            "device": "cpu",
            "detections": [[12, 7, 1.5, 1.5]],
            "associations": [[12, 7, 13, 404, 0.5]],
            "divisions": [],
        }

    with pytest.raises(TrackAstraWorkerError, match="detection set"):
        run_trackastra(movie, segmentations, start_frame=12, worker=fake_worker)

    np.testing.assert_array_equal(movie, movie_before)
    np.testing.assert_array_equal(segmentations, segmentations_before)


def test_worker_must_report_division_for_every_two_child_association():
    movie, segmentations = _movie_and_segmentations()

    def fake_worker(_request, **_kwargs):
        response = _valid_response()
        response["divisions"] = []
        return response

    with pytest.raises(TrackAstraWorkerError, match="cover every two-child"):
        run_trackastra(movie, segmentations, start_frame=12, worker=fake_worker)


class _FakeStatus:
    def __init__(self):
        self.finished = False

    def is_finished(self):
        return self.finished


class _FakeTask:
    def __init__(self, response, failure=None):
        self.inputs = {}
        self.outputs = response
        self.failure = failure
        self.listener = None
        self.status = _FakeStatus()
        self.cv = _FakeCondition()
        self.canceled = False

    def listen(self, listener):
        self.listener = listener

    def wait_for(self):
        if self.failure:
            raise self.failure
        self.status.finished = True
        return self

    def start(self):
        return self

    def cancel(self):
        self.canceled = True


class _FakeCondition:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def wait(self, timeout=None):
        return None


class _FakeService:
    def __init__(self, task):
        self._task = task
        self.closed = False
        self.init_script = None

    def init(self, script):
        self.init_script = script
        return self

    def task(self, _script):
        return self._task

    def close(self):
        self.closed = True


class _FakeEnvironment:
    def __init__(self, service):
        self._service = service

    def python(self):
        return self._service


class _FakeBuilder:
    def __init__(self, environment):
        self._environment = environment
        self.environment_name = None
        self.name_value = None

    def name(self, value):
        self.name_value = value
        return self

    def subscribe_progress(self, _callback):
        return self

    def subscribe_output(self, _callback):
        return self

    def subscribe_error(self, _callback):
        return self

    def environment(self, value):
        self.environment_name = value
        return self

    def build(self):
        return self._environment


class _FakeNDArray:
    def __init__(self, dtype, shape):
        self.array = np.zeros(shape, dtype=dtype)
        self.disposed = False

    def ndarray(self):
        return self.array

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.disposed = True


class _FakeAppose:
    def __init__(self, task):
        self.service = _FakeService(task)
        self.builder = _FakeBuilder(_FakeEnvironment(self.service))
        self.shared_arrays = []

    def pixi(self, _manifest):
        return self.builder

    def NDArray(self, dtype, shape):
        shared = _FakeNDArray(dtype, shape)
        self.shared_arrays.append(shared)
        return shared


def _valid_response(device="cpu"):
    return {
        "schema_version": 1,
        "trackastra_version": "0.5.3",
        "model": "general_2d",
        "device": device,
        "detections": [
            [12, 7, 1.5, 1.5],
            [13, 8, 1.0, 1.5],
            [13, 9, 2.0, 1.5],
        ],
        "associations": [
            [12, 7, 13, 8, 0.95],
            [12, 7, 13, 9, 0.85],
        ],
        "divisions": [[12, 7, 13, 8, 9, 0.95, 0.85]],
    }


def _appose_worker(fake_appose):
    return ApposeTrackAstraWorker(
        appose_module=fake_appose,
        system=lambda: "Darwin",
        machine=lambda: "arm64",
        manifest="fake-pixi-trackastra.toml",
    )


def test_appose_adapter_releases_service_and_shared_memory_on_success():
    movie, segmentations = _movie_and_segmentations()
    fake_appose = _FakeAppose(_FakeTask(_valid_response()))
    messages = []

    result = run_trackastra(
        movie,
        segmentations,
        start_frame=12,
        worker=_appose_worker(fake_appose),
        progress=lambda message, current, maximum: messages.append(
            (message, current, maximum)
        ),
    )

    assert result.device == "cpu"
    assert fake_appose.builder.name_value == "epicure-trackastra-arm64"
    assert fake_appose.builder.environment_name == "default"
    assert fake_appose.service.closed
    assert len(fake_appose.shared_arrays) == 2
    assert all(shared.disposed for shared in fake_appose.shared_arrays)
    assert ("Preparing the TrackAstra environment", 0, 1) in messages
    assert ("TrackAstra complete", 1, 1) in messages


def test_appose_adapter_releases_resources_when_worker_fails():
    movie, segmentations = _movie_and_segmentations()
    fake_appose = _FakeAppose(
        _FakeTask(_valid_response(), failure=RuntimeError("model exploded"))
    )

    with pytest.raises(TrackAstraWorkerError, match="could not be provisioned or run"):
        run_trackastra(
            movie,
            segmentations,
            start_frame=12,
            worker=_appose_worker(fake_appose),
        )

    assert fake_appose.service.closed
    assert all(shared.disposed for shared in fake_appose.shared_arrays)


def test_appose_adapter_cancels_task_and_releases_resources():
    movie, segmentations = _movie_and_segmentations()
    task = _FakeTask(_valid_response())
    fake_appose = _FakeAppose(task)

    with pytest.raises(TrackAstraWorkerError, match="was canceled"):
        run_trackastra(
            movie,
            segmentations,
            start_frame=12,
            worker=_appose_worker(fake_appose),
            cancel_requested=lambda: True,
        )

    assert task.canceled
    assert fake_appose.service.closed
    assert all(shared.disposed for shared in fake_appose.shared_arrays)


def test_appose_adapter_rejects_non_arm64_hosts_before_provisioning():
    movie, segmentations = _movie_and_segmentations()
    fake_appose = _FakeAppose(_FakeTask(_valid_response()))
    worker = ApposeTrackAstraWorker(
        appose_module=fake_appose,
        system=lambda: "Linux",
        machine=lambda: "x86_64",
        manifest="fake-pixi-trackastra.toml",
    )

    with pytest.raises(TrackAstraWorkerError, match="Apple Silicon"):
        run_trackastra(movie, segmentations, start_frame=12, worker=worker)

    assert not fake_appose.service.closed
    assert fake_appose.shared_arrays == []


def test_cleanup_failure_does_not_mask_allocation_failure(monkeypatch):
    fake = _FakeAppose(_FakeTask(_valid_response()))
    def allocation_failure(*args):
        raise MemoryError('shared memory exhausted')
    def close_unstarted():
        raise RuntimeError('Service has not been started')
    monkeypatch.setattr(fake, 'NDArray', allocation_failure)
    monkeypatch.setattr(fake.service, 'close', close_unstarted)
    movie, masks = _movie_and_segmentations()
    with pytest.raises(TrackAstraWorkerError) as error:
        run_trackastra(movie, masks, start_frame=12, worker=_appose_worker(fake))
    assert isinstance(error.value.__cause__, MemoryError)
    assert 'shared memory exhausted' in str(error.value.__cause__)


def test_successful_worker_reports_cleanup_error_inside_callers_except(monkeypatch):
    fake = _FakeAppose(_FakeTask(_valid_response()))
    def close_failure():
        raise RuntimeError('close failed')
    monkeypatch.setattr(fake.service, 'close', close_failure)
    movie, masks = _movie_and_segmentations()
    try:
        raise ValueError('unrelated caller exception')
    except ValueError:
        with pytest.raises(TrackAstraWorkerError, match='could not be closed'):
            run_trackastra(movie, masks, start_frame=12, worker=_appose_worker(fake))
