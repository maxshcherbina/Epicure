import appose
import numpy as np
import logging
from importlib import resources
import platform

def share_as_ndarray(img: np.ndarray) -> appose.NDArray:
    """Copies a NumPy array into a same-sized newly allocated block of shared memory."""
    shared = appose.NDArray(str(img.dtype), img.shape)
    shared.ndarray()[:] = img
    return shared

# Runs inside the isolated cellpose environment (see resources/pixi_cellpose.toml).
# 2D slice-by-slice: cellpose-SAM is run once per time frame; labels are per-frame
# (EpiCure does the cross-frame tracking). Results go into a SEPARATE uint32 shared
# buffer -- unlike epyseg we can't reuse the input buffer (input is uint8/uint16,
# labels need uint32).
cellpose_script = '''
import numpy as np
from cellpose import models

class ApposeLogHandler(__import__("logging").Handler):
    def emit(self, record):
        task.update(message=self.format(record))

data = image.ndarray()            # (T, Y, X), single channel
out = labels.ndarray()            # (T, Y, X), uint32 -- filled in place

use_gpu = parameters.get("gpu", True)
diameter = parameters.get("diameter", None)          # None = no diameter rescaling
flow_threshold = parameters.get("flow_threshold", 0.4)
cellprob_threshold = parameters.get("cellprob_threshold", 0.0)
min_size = parameters.get("min_size", 30)
model_name = parameters.get("model", "cpsam")

# cellpose 4.x is SAM-only: the classic models.Cellpose class + cyto/nuclei models were
# removed. Valid pretrained_model values are the SAM family (cpsam, cpsam_v2, cpdino,
# cpdino-vitb). Older cyto3-style models would need a separate cellpose 3.x environment.
model = models.CellposeModel(gpu=use_gpu, pretrained_model=model_name)

nframes = data.shape[0]
for i in range(nframes):
    frame = data[i].astype(np.float32)
    res = model.eval(
        frame,
        diameter=diameter,
        normalize=True,
        flow_threshold=flow_threshold,
        cellprob_threshold=cellprob_threshold,
        min_size=min_size,
    )   # SAM eval returns (masks, flows, styles); masks are res[0]
    out[i] = res[0].astype(np.uint32)
    task.update(message=f"Cellpose ({model_name}) segmented frame {i + 1}/{nframes}")
'''

def refine_to_membrane(image, labels, sigma=1.0):
    """Snap cellpose label boundaries onto the membrane ridge with a seeded watershed
    that flows on the membrane intensity (per 2D frame). Cellpose's boundaries sit on
    the cytosol edge and, once gaps are closed geometrically, look flat; feeding the
    cellpose labels as watershed seeds and letting the boundary settle on the bright
    membrane gives tiled, membrane-faithful junctions. Cell count is preserved (every
    input label stays a seed). Runs on the host (epicure env has scikit-image)."""
    from skimage.segmentation import watershed
    from skimage.filters import gaussian
    refined = np.zeros_like(labels)
    for i in range(labels.shape[0]):
        # Nothing to refine on empty or single-cell frames (watershed would just claim the
        # whole frame for that one label); leave them untouched. Note: on multi-cell frames
        # the watershed has no foreground mask, so cells tile the entire field -- intended
        # for epithelia that fill the frame, not for sparse cells on a large background.
        if len(np.unique(labels[i])) < 3:
            refined[i] = labels[i]
            continue
        land = gaussian(image[i].astype("float32"), sigma=sigma)
        refined[i] = watershed(land, markers=labels[i]).astype(labels.dtype)
    return refined

def go_cellpose(image, parameters, progress_bar=None, logger=None):
    """Install a python environment with cellpose if necessary (via appose+pixi) and
    run cellpose-SAM slice-by-slice on the (T, Y, X) image within that environment.
    Returns a (T, Y, X) uint32 label stack."""
    _logger = logger or logging.getLogger(__name__)
    try:
        pixi_file = resources.files("epicure.resources").joinpath("pixi_cellpose.toml")
        _logger.info("Build/Load cellpose environment")
        env = appose.pixi(pixi_file).log_debug()
        env = env.subscribe_output(lambda line: print("OUT:", line, end=""))
        env = env.subscribe_error(lambda line: print("DBG:", line, end=""))
        ## GPU environment for Linux/Windows (CUDA); macOS uses the default (MPS/CPU).
        is_gpu_platform = platform.system() in ("Linux", "Windows")
        env_name = "cuda" if is_gpu_platform else "default"
        env = env.environment(env_name).build()
        _logger.info(f"Environment built at: {env.base()}")
        python = env.python().init("import numpy as np; from cellpose import models")

        def log_listener(event):
            if event.message:
                _logger.info(f"[task] {event.message}")

        try:
            with share_as_ndarray(image) as shared_image, \
                 appose.NDArray("uint32", image.shape) as shared_labels:
                task = python.task(cellpose_script)
                task.listen(log_listener)
                task.inputs["image"] = shared_image
                task.inputs["labels"] = shared_labels
                task.inputs["parameters"] = parameters
                ## (no "extras" input: the script reports progress via task.update, and a
                ## napari progress object would not be JSON-serializable across appose.)
                _logger.info("Start cellpose segmentation in appose service task..")
                task.wait_for()
                labels = shared_labels.ndarray().copy()
            if parameters.get("refine_membrane", False):
                _logger.info("Snapping boundaries to the membrane (seeded watershed)..")
                labels = refine_to_membrane(image, labels, sigma=parameters.get("refine_sigma", 1.0))
            return labels
        except Exception as e:
            raise RuntimeError("Running cellpose in separated environment failed") from e
        finally:
            python.close()
    except Exception as e:
        raise RuntimeError("Cellpose in separated environment failed") from e
