"""Isolated TrackAstra worker contract.

The public boundary deliberately identifies detections by the segmentation facts
``(frame, label)``.  TrackAstra's integer NetworkX node IDs are an implementation
detail and are not stable enough to persist in an EpiCure project.
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib import resources
import platform
from typing import Any, Callable, Mapping, Protocol, Sequence

import appose
import numpy as np


TRACKASTRA_SCHEMA_VERSION = 1
TRACKASTRA_VERSION = "0.5.3"
TRACKASTRA_MODEL = "general_2d"
TRACKASTRA_MODE = "greedy"

ProgressCallback = Callable[[str, int | None, int | None], None]
CancelCallback = Callable[[], bool]


class TrackAstraWorkerError(RuntimeError):
    """Raised when TrackAstra cannot run or violates the worker contract."""


class TrackAstraCancelled(TrackAstraWorkerError):
    """Raised when the caller cancels an isolated TrackAstra task."""


@dataclass(frozen=True, eq=False)
class TrackAstraRequest:
    """The selected movie and authoritative segmentations sent to the worker."""

    movie: np.ndarray
    segmentations: np.ndarray
    start_frame: int = 0
    model: str = TRACKASTRA_MODEL
    mode: str = TRACKASTRA_MODE

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, TrackAstraRequest):
            return NotImplemented
        return (
            self.start_frame == other.start_frame
            and self.model == other.model
            and self.mode == other.mode
            and np.array_equal(self.movie, other.movie)
            and np.array_equal(self.segmentations, other.segmentations)
        )


@dataclass(frozen=True)
class Detection:
    frame: int
    label: int
    y: float
    x: float


@dataclass(frozen=True)
class Association:
    source_frame: int
    source_label: int
    target_frame: int
    target_label: int
    score: float


@dataclass(frozen=True)
class Division:
    parent_frame: int
    parent_label: int
    child_frame: int
    child_a_label: int
    child_b_label: int
    child_a_score: float
    child_b_score: float


@dataclass(frozen=True)
class TrackAstraResult:
    schema_version: int
    trackastra_version: str
    model: str
    device: str
    detections: tuple[Detection, ...]
    associations: tuple[Association, ...]
    divisions: tuple[Division, ...]


class TrackAstraWorker(Protocol):
    def __call__(
        self,
        request: TrackAstraRequest,
        *,
        progress: ProgressCallback | None = None,
        cancel_requested: CancelCallback | None = None,
    ) -> Mapping[str, Any]: ...


def run_trackastra(
    movie: np.ndarray,
    segmentations: np.ndarray,
    *,
    start_frame: int = 0,
    worker: TrackAstraWorker | None = None,
    progress: ProgressCallback | None = None,
    cancel_requested: CancelCallback | None = None,
) -> TrackAstraResult:
    """Run TrackAstra without allowing worker failures to mutate host arrays."""

    movie_array, segmentation_array = _validate_inputs(
        movie, segmentations, start_frame
    )
    request = TrackAstraRequest(
        movie=movie_array.copy(),
        segmentations=segmentation_array.copy(),
        start_frame=int(start_frame),
    )
    execute = worker or _run_appose_trackastra
    try:
        response = execute(
            request,
            progress=progress,
            cancel_requested=cancel_requested,
        )
        return _validate_response(response, request)
    except TrackAstraWorkerError:
        raise
    except Exception as exc:
        raise TrackAstraWorkerError(
            "TrackAstra failed in its isolated environment; the current EpiCure "
            "segmentations and tracks were not changed."
        ) from exc


def _validate_inputs(
    movie: np.ndarray, segmentations: np.ndarray, start_frame: int
) -> tuple[np.ndarray, np.ndarray]:
    movie_array = np.asarray(movie)
    segmentation_array = np.asarray(segmentations)
    if movie_array.ndim != 3 or segmentation_array.ndim != 3:
        raise TrackAstraWorkerError(
            "TrackAstra requires matching (time, y, x) movie and segmentation stacks."
        )
    if movie_array.shape != segmentation_array.shape or movie_array.shape[0] < 2:
        raise TrackAstraWorkerError(
            "TrackAstra requires matching movie and segmentation stacks with at least two frames."
        )
    if not np.issubdtype(movie_array.dtype, np.number):
        raise TrackAstraWorkerError("TrackAstra movie data must be numeric.")
    if not np.isfinite(movie_array).all():
        raise TrackAstraWorkerError("TrackAstra movie data cannot contain NaN or infinity.")
    if not np.issubdtype(segmentation_array.dtype, np.integer):
        raise TrackAstraWorkerError("TrackAstra segmentations must contain integer labels.")
    if np.any(segmentation_array < 0):
        raise TrackAstraWorkerError("TrackAstra segmentation labels cannot be negative.")
    if not np.any(segmentation_array > 0):
        raise TrackAstraWorkerError(
            "TrackAstra requires at least one segmented cell in the selected range."
        )
    if int(start_frame) != start_frame or start_frame < 0:
        raise TrackAstraWorkerError("TrackAstra start_frame must be a non-negative integer.")
    return np.ascontiguousarray(movie_array), np.ascontiguousarray(segmentation_array)


def _validate_response(
    response: Mapping[str, Any], request: TrackAstraRequest
) -> TrackAstraResult:
    if not isinstance(response, Mapping):
        raise TrackAstraWorkerError("TrackAstra returned a malformed worker response.")
    if response.get("schema_version") != TRACKASTRA_SCHEMA_VERSION:
        raise TrackAstraWorkerError(
            "TrackAstra worker schema is incompatible with this EpiCure version."
        )
    if response.get("model") != request.model:
        raise TrackAstraWorkerError("TrackAstra returned results from an unexpected model.")
    device = response.get("device")
    if device not in {"mps", "cpu"}:
        raise TrackAstraWorkerError("TrackAstra returned an unsupported compute device.")
    version = response.get("trackastra_version")
    if version != TRACKASTRA_VERSION:
        raise TrackAstraWorkerError(
            f"TrackAstra worker must use pinned version {TRACKASTRA_VERSION}; got {version!r}."
        )

    detections = tuple(
        _parse_row(Detection, row, 4, "detection")
        for row in _rows(response, "detections")
    )
    associations = tuple(
        _parse_row(Association, row, 5, "association")
        for row in _rows(response, "associations")
    )
    divisions = tuple(
        _parse_row(Division, row, 7, "division")
        for row in _rows(response, "divisions")
    )

    expected = _segmentation_detection_keys(request)
    actual = {(item.frame, item.label) for item in detections}
    if len(actual) != len(detections) or actual != expected:
        raise TrackAstraWorkerError(
            "TrackAstra worker detection set does not match the selected segmentations."
        )

    detection_by_key = {(item.frame, item.label): item for item in detections}
    for item in detections:
        if item.label <= 0 or not np.isfinite((item.y, item.x)).all():
            raise TrackAstraWorkerError("TrackAstra returned an invalid detection row.")
        local_frame = item.frame - request.start_frame
        height, width = request.segmentations.shape[1:]
        if not (0 <= item.y < height and 0 <= item.x < width):
            raise TrackAstraWorkerError("TrackAstra returned an out-of-bounds detection.")
        ys, xs = np.where(request.segmentations[local_frame] == item.label)
        expected_centroid = (float(ys.mean()), float(xs.mean()))
        if not np.allclose((item.y, item.x), expected_centroid, atol=1e-4, rtol=0):
            raise TrackAstraWorkerError(
                "TrackAstra detection centroid does not match its segmentation label."
            )

    association_scores: dict[tuple[int, int, int, int], float] = {}
    outgoing: dict[tuple[int, int], set[tuple[int, int]]] = {}
    incoming: dict[tuple[int, int], set[tuple[int, int]]] = {}
    for item in associations:
        source = (item.source_frame, item.source_label)
        target = (item.target_frame, item.target_label)
        key = (*source, *target)
        if source not in detection_by_key or target not in detection_by_key:
            raise TrackAstraWorkerError(
                "TrackAstra association references a detection outside the selected range."
            )
        if item.target_frame != item.source_frame + 1:
            raise TrackAstraWorkerError(
                "TrackAstra returned a non-adjacent association for adjacent-frame tracking."
            )
        if not np.isfinite(item.score) or not 0.0 <= item.score <= 1.0:
            raise TrackAstraWorkerError("TrackAstra returned an invalid association score.")
        if key in association_scores:
            raise TrackAstraWorkerError("TrackAstra returned a duplicate association.")
        association_scores[key] = item.score
        outgoing.setdefault(source, set()).add(target)
        incoming.setdefault(target, set()).add(source)

    if any(len(targets) > 2 for targets in outgoing.values()):
        raise TrackAstraWorkerError(
            "TrackAstra returned more than two children for one detection."
        )
    if any(len(sources) > 1 for sources in incoming.values()):
        raise TrackAstraWorkerError(
            "TrackAstra returned more than one parent for one detection."
        )

    actual_divisions: set[tuple[int, int, int, frozenset[int]]] = set()
    for item in divisions:
        if item.child_a_label == item.child_b_label:
            raise TrackAstraWorkerError("TrackAstra returned duplicate division children.")
        child_edges = {
            (
                item.parent_frame,
                item.parent_label,
                item.child_frame,
                item.child_a_label,
            ),
            (
                item.parent_frame,
                item.parent_label,
                item.child_frame,
                item.child_b_label,
            ),
        }
        if (
            item.child_frame != item.parent_frame + 1
            or not child_edges <= association_scores.keys()
        ):
            raise TrackAstraWorkerError(
                "TrackAstra division evidence does not match its scored associations."
            )
        evidence_scores = (item.child_a_score, item.child_b_score)
        if not np.isfinite(evidence_scores).all() or not all(
            0.0 <= score <= 1.0 for score in evidence_scores
        ):
            raise TrackAstraWorkerError("TrackAstra returned an invalid division score.")
        expected_scores = (
            association_scores[
                (
                    item.parent_frame,
                    item.parent_label,
                    item.child_frame,
                    item.child_a_label,
                )
            ],
            association_scores[
                (
                    item.parent_frame,
                    item.parent_label,
                    item.child_frame,
                    item.child_b_label,
                )
            ],
        )
        if not np.allclose(evidence_scores, expected_scores, rtol=1e-6, atol=1e-7):
            raise TrackAstraWorkerError(
                "TrackAstra division scores do not match its association evidence."
            )
        division_key = (
            item.parent_frame,
            item.parent_label,
            item.child_frame,
            frozenset((item.child_a_label, item.child_b_label)),
        )
        if division_key in actual_divisions:
            raise TrackAstraWorkerError("TrackAstra returned duplicate division evidence.")
        actual_divisions.add(division_key)

    expected_divisions = {
        (source[0], source[1], next(iter(targets))[0], frozenset(t[1] for t in targets))
        for source, targets in outgoing.items()
        if len(targets) == 2
    }
    if actual_divisions != expected_divisions:
        raise TrackAstraWorkerError(
            "TrackAstra division table does not cover every two-child association."
        )

    return TrackAstraResult(
        schema_version=TRACKASTRA_SCHEMA_VERSION,
        trackastra_version=version,
        model=request.model,
        device=device,
        detections=detections,
        associations=associations,
        divisions=divisions,
    )


def _rows(response: Mapping[str, Any], name: str) -> Sequence[Sequence[Any]]:
    rows = response.get(name)
    if not isinstance(rows, (list, tuple)):
        raise TrackAstraWorkerError(f"TrackAstra response is missing the {name} table.")
    return rows


def _parse_row(record_type, row: Sequence[Any], width: int, name: str):
    if not isinstance(row, (list, tuple)) or len(row) != width:
        raise TrackAstraWorkerError(f"TrackAstra returned an invalid {name} row.")
    try:
        return record_type(*row)
    except (TypeError, ValueError) as exc:
        raise TrackAstraWorkerError(
            f"TrackAstra returned an invalid {name} row."
        ) from exc


def _segmentation_detection_keys(request: TrackAstraRequest) -> set[tuple[int, int]]:
    return {
        (request.start_frame + local_frame, int(label))
        for local_frame, frame in enumerate(request.segmentations)
        for label in np.unique(frame)
        if label != 0
    }


def _run_appose_trackastra(
    request: TrackAstraRequest,
    *,
    progress: ProgressCallback | None = None,
    cancel_requested: CancelCallback | None = None,
) -> Mapping[str, Any]:
    return ApposeTrackAstraWorker()(
        request,
        progress=progress,
        cancel_requested=cancel_requested,
    )


TRACKASTRA_SCRIPT = r'''
import importlib.metadata
import logging
import numpy as np
import torch
from trackastra.model import Trackastra

class ApposeLogHandler(logging.Handler):
    def emit(self, record):
        task.update(message=self.format(record))

trackastra_logger = logging.getLogger("trackastra")
trackastra_logger.setLevel(logging.INFO)
trackastra_logger.addHandler(ApposeLogHandler())

images = movie.ndarray()
masks = segmentations.ndarray()
start = int(start_frame)
device = "mps" if torch.backends.mps.is_available() else "cpu"
task.update(message=f"TrackAstra: loading {model_name} on {device}")

model = Trackastra.from_pretrained(model_name, device=device)
graph, _ = model.track(images, masks, mode=tracking_mode, delta_t=1)

# The authoritative detections are the edited input segmentations, including
# detections the greedy solver leaves unmatched and omits from its result graph.
detections = []
for local_frame, frame in enumerate(masks):
    labels = np.unique(frame)
    labels = labels[labels != 0]
    for label in labels:
        ys, xs = np.where(frame == label)
        detections.append([
            start + local_frame,
            int(label),
            float(ys.mean()),
            float(xs.mean()),
        ])

def node_key(node):
    attrs = graph.nodes[node]
    return (start + int(attrs["time"]), int(attrs["label"]))

associations = []
for source, target, attrs in graph.edges(data=True):
    source_frame, source_label = node_key(source)
    target_frame, target_label = node_key(target)
    score = float(attrs["weight"])
    associations.append([
        source_frame,
        source_label,
        target_frame,
        target_label,
        score,
    ])

divisions = []
for parent in graph.nodes:
    children = list(graph.successors(parent))
    if len(children) > 2:
        raise RuntimeError(
            f"TrackAstra returned {len(children)} children for one detection; expected at most 2"
        )
    if len(children) == 2:
        parent_frame, parent_label = node_key(parent)
        child_evidence = sorted(
            (*node_key(child), float(graph.edges[parent, child]["weight"]))
            for child in children
        )
        child_frame = child_evidence[0][0]
        if child_evidence[1][0] != child_frame:
            raise RuntimeError("TrackAstra division children occur in different frames")
        divisions.append([
            parent_frame,
            parent_label,
            child_frame,
            child_evidence[0][1],
            child_evidence[1][1],
            child_evidence[0][2],
            child_evidence[1][2],
        ])

task.outputs["schema_version"] = schema_version
task.outputs["trackastra_version"] = importlib.metadata.version("trackastra")
task.outputs["model"] = model_name
task.outputs["device"] = device
task.outputs["detections"] = detections
task.outputs["associations"] = associations
task.outputs["divisions"] = divisions
'''


class ApposeTrackAstraWorker:
    """Provision and execute the reusable Apple ARM64 TrackAstra environment."""

    def __init__(
        self,
        *,
        appose_module=appose,
        system: Callable[[], str] = platform.system,
        machine: Callable[[], str] = platform.machine,
        manifest=None,
    ):
        self._appose = appose_module
        self._system = system
        self._machine = machine
        self._manifest = manifest

    def __call__(
        self,
        request: TrackAstraRequest,
        *,
        progress: ProgressCallback | None = None,
        cancel_requested: CancelCallback | None = None,
    ) -> Mapping[str, Any]:
        self._require_apple_arm64()
        manifest = self._manifest or resources.files("epicure.resources").joinpath(
            "pixi_trackastra.toml"
        )
        service = None
        try:
            _emit_progress(progress, "Preparing the TrackAstra environment", 0, 1)
            builder = self._appose.pixi(manifest)
            builder = builder.name("epicure-trackastra-arm64")
            builder = builder.subscribe_progress(
                lambda title, current, maximum: _emit_progress(
                    progress, title, current, maximum
                )
            )
            builder = builder.subscribe_output(
                lambda line: _emit_progress(progress, line.strip(), None, None)
            )
            builder = builder.subscribe_error(
                lambda line: _emit_progress(progress, line.strip(), None, None)
            )
            environment = builder.environment("default").build()
            _emit_progress(progress, "TrackAstra environment ready", 1, 1)

            service = environment.python().init(
                "import numpy as np; import torch; from trackastra.model import Trackastra"
            )
            with _share_as_ndarray(self._appose, request.movie) as shared_movie, \
                 _share_as_ndarray(
                     self._appose, request.segmentations
                 ) as shared_segmentations:
                task = service.task(TRACKASTRA_SCRIPT)
                task.listen(
                    lambda event: _emit_progress(
                        progress, event.message, event.current, event.maximum
                    )
                    if event.message
                    else None
                )
                task.inputs.update(
                    {
                        "movie": shared_movie,
                        "segmentations": shared_segmentations,
                        "start_frame": request.start_frame,
                        "model_name": request.model,
                        "tracking_mode": request.mode,
                        "schema_version": TRACKASTRA_SCHEMA_VERSION,
                    }
                )
                _emit_progress(progress, "Running TrackAstra", 0, 1)
                _wait_for_task(task, cancel_requested)
                response = dict(task.outputs)
                _emit_progress(progress, "TrackAstra complete", 1, 1)
                return response
        except TrackAstraCancelled:
            raise
        except TrackAstraWorkerError:
            raise
        except Exception as exc:
            raise TrackAstraWorkerError(
                "TrackAstra could not be provisioned or run on this Apple Silicon Mac. "
                "Check the network connection on first use and available disk space, "
                "then try again. Existing EpiCure data was not changed."
            ) from exc
        finally:
            if service is not None:
                service.close()

    def _require_apple_arm64(self) -> None:
        system = self._system()
        machine = self._machine().lower()
        if system != "Darwin" or machine not in {"arm64", "aarch64"}:
            raise TrackAstraWorkerError(
                "This TrackAstra worker currently supports Apple Silicon (ARM64) Macs only."
            )


def _share_as_ndarray(appose_module, array: np.ndarray):
    shared = appose_module.NDArray(str(array.dtype), list(array.shape))
    shared.ndarray()[:] = array
    return shared


def _wait_for_task(task, cancel_requested: CancelCallback | None) -> None:
    if cancel_requested is None:
        task.wait_for()
        return

    task.start()
    while not task.status.is_finished():
        if cancel_requested():
            task.cancel()
            raise TrackAstraCancelled(
                "TrackAstra tracking was canceled; existing EpiCure data was not changed."
            )
        with task.cv:
            task.cv.wait(timeout=0.1)
    task.wait_for()


def _emit_progress(
    callback: ProgressCallback | None,
    message: str | None,
    current: int | None,
    maximum: int | None,
) -> None:
    if callback is not None and message:
        callback(message, current, maximum)
