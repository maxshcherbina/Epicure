## Segment with Cellpose

When starting EpiCure, once you have selected the movie to process and the junction (or membrane/nuclei) channel, you have to load the file containing the segmentation of the movie. If you haven't done it yet, you can use the `Segment now with Cellpose` button that appears in the `Start EpiCure` interface, next to the `Segment now with EpySeg` button.

This option runs [Cellpose](https://github.com/MouseLand/cellpose) 4.2 directly on the movie, **frame by frame in 2D**. The default model is DINOv3 ViT-B (`cpdino-vitb`); `cpsam` and `cpsam_v2` remain selectable from the **Cellpose model** menu. It runs with sensible default parameters (automatic diameter, `flow_threshold=0.4`, `cellprob_threshold=0.0`, `min_size=30`). If you want finer control over the parameters, run Cellpose directly (its own GUI or API) and load the resulting label mask through the normal `Segmentation file` field instead.

Note that this option depends on Cellpose and PyTorch, which are **not** installed with EpiCure. As for EpySeg, and for the same reason (heavy, version-sensitive dependencies that could conflict with EpiCure's own), the call to Cellpose is isolated to an independent virtual environment, handled entirely automatically by EpiCure through the [appose](https://github.com/apposed/appose) library.

When clicking the first time on the `Segment now with Cellpose` button, `appose` will install a new virtual environment (Python 3.11, Cellpose, PyTorch, and a pinned version of Meta's DINOv3 architecture package). This first build takes a while and needs a network connection; the next time the button is clicked, `appose` reuses the same environment. Selecting `cpdino-vitb` for the first time also downloads its approximately 328 MB Cellpose checkpoint into Cellpose's normal model cache. On Apple Silicon, Cellpose uses MPS when it is available and otherwise falls back to CPU. DINOv3 is distributed under [Meta's DINOv3 License](https://github.com/facebookresearch/dinov3/blob/main/LICENSE.md).

Then `appose` puts the raw movie in memory shared between the two python processes (the main EpiCure one and the Cellpose one), and runs the segmentation there. Each time frame is segmented independently in 2D; the resulting per-frame label mask is written back to EpiCure through the same shared memory. Cross-frame cell identity is then established by EpiCure's tracking, exactly as for any other segmentation source.

On macOS the model runs on the MPS backend (Apple GPU) if available, otherwise on CPU. macOS arm64 is the tested target. A Linux/Windows GPU environment is stubbed in the pixi spec but is not yet configured with a CUDA-specific PyTorch build, so it currently resolves to the same CPU packages; wiring a real CUDA target is future work.

Thanks to that set-up, you only have to click the button and wait. EpiCure saves the result automatically in the segmentation file default location (`<movie>_cellpose.tif`) so it is ready to use.
