# Wayfinder map — Cellpose support in EpiCure

> Tracker fallback: no beads DB in this repo, so this markdown file **is** the map.
> Tickets live inline below (§ Tickets) with explicit `blocked-by` edges and a
> `status` line each, since markdown has no native blocking.

## Destination

A working **"Segment with cellpose"** button in EpiCure's start GUI, mirroring the
existing EpySeg feature exactly (isolated `appose` + `pixi` sub-environment). It runs
cellpose **slice-by-slice in 2D** on the loaded movie, writes an integer label-mask
TIF, and feeds it straight into EpiCure's normal load / edit / track path (which needs
no changes — it already ingests int label masks).

Target *now*: builds and runs on **Mac arm64 (M4)**. The pixi env is structured
cross-platform like EpySeg (a CUDA variant stubbed for later) but CUDA is **not**
tested in this effort. Eventually upstreamable to the real EpiCure, so **polish and a
docs page are in scope**.

## Notes

- **This map carries execution** (overrides wayfinder's plan-only default). The last
  tickets land a working button, not just a spec. Goal confirmed by user: "build the
  cellpose support into epicure", "lets do it all".
- **Template to clone (exact refs in `src/epicure/`):**
  - `start_epicuring.py` — EpySeg button `segment_with_epyseg` (~L262/L284), handler
    `launch_napari_epyseg` (~L212-246), signal wiring (~L340), visibility toggles
    (L107/133/138/186/246). The cellpose button is a sibling of these.
  - `appose_epyseg.py` (whole file, 78 lines) — the isolated-runner + shared-memory
    pattern to mirror as `appose_cellpose.py`. `go_epyseg(image, parameters, ...)`.
  - `resources/pixi.toml` — the env spec to extend/clone (python 3.10, per-platform
    deps, `[pypi-dependencies]`).
  - Loader `epicuring.py:356` `load_segmentation` — **no change needed**; cellpose
    emits `uint32`-castable int labels that plug straight in.
- **Reusable local code (sibling projects under `/Users/max/Documents/1python/`):**
  - `dapiVolumeCalc/worker_cellpose.py`, `scratch_cpsam_*.py`, `compare_cellpose_models.py`
    — existing working cellpose-SAM calls + params + frame loop.
  - `cellpose_napari/.venv` has **cellpose 4.0.8 + torch 2.7.1 installed** (cellpose 4.x
    = cellpose-SAM, the "most recent" model to default to).
- **Hard constraint — mobile hotspot, do NOT re-download torch/cellpose.** `~/.cache/uv`
  already holds torch / cellpose / torchvision wheels; pixi resolves `[pypi-dependencies]`
  via uv, so the isolated env should reuse that wheel cache. Avoid multi-GB pulls.
- **Detection is 2D slice-by-slice** across time, never `do_3D` (user's explicit choice).
- Python is `uv` (`uv run ...`); never bare pip.
- Skills to consult per ticket: `/research` (read sibling code), `/grill`+`/domain-modeling`
  (decisions), `verify` (end-to-end drive of the button in napari).

## Decisions so far

<!-- one line per closed ticket -->

- **R1 — cellpose-SAM call pinned** — `models.CellposeModel(gpu=True)` (v4 default =
  `cpsam`), then per-2D-frame `model.eval(frame_f32, diameter=None, normalize=True,
  flow_threshold=0.4, cellprob_threshold=0.0, min_size=30)` → `(masks, flows, styles)`;
  NO `channels` arg for SAM; masks→uint32. Validated against installed cellpose 4.0.8 on
  a synthetic 2-frame movie (found all cells, correct shape/dtype).
- **D2 — separate pixi workspace + cache-aligned pins** — `resources/pixi_cellpose.toml`
  (own workspace, not the TF/numpy<2 epyseg env). Deps as `[pypi-dependencies]` so
  pixi/uv reuse `~/.cache/uv`. Pinned cellpose==4.2.1.1, torch==2.11.0, torchvision==0.26.0
  (cp310, cache-aligned). **torch (200MB+) and cpsam weights (1.1GB) are already cached**
  — no big download.
- **T1 — pixi env builds on M4** — user approved a ~40MB one-time pull. Real
  `appose.pixi(...).build()` succeeded after pinning `setuptools>=65,<82` (torch 2.11 needs
  <82; the conda base was injecting 83 → unsatisfiable pypi solve). Env at
  `~/.local/share/appose/cellpose-env`.
- **T4 — end-to-end verified** — real appose+pixi subprocess ran cellpose **4.2.1.1**
  (cpsam_v2) on a synthetic 2-frame movie: `(2,128,128)` uint32 labels, cells found per
  frame. Two-buffer shared memory (uint8 in / uint32 out) works. Only the literal GUI
  button click is unexercised (thin wrapper over the verified `go_cellpose`).
- **Codex (gpt-5.6-sol) review #1** — confirmed appose two-buffer design, cellpose call, pixi
  manifest, magicgui wiring all sound. Found one **High** bug: `get_files.image_file`
  doesn't exist (pre-existing in the EpySeg handler too) → `AttributeError` on save.
  Fixed both to use `raw_movie_path`. Also removed an unused `extras` appose input and
  added progress-bar cleanup on failure.
- **GUI verified in real napari** — user ran the button in a live napari session; it
  segmented all 101 frames of `small_crop23-123_8bit.tif` and saved
  `<movie>_cellpose.tif`. Closes the "GUI click not driven" gap from T4.
- **Model dropdown (E1)** — added a `cellpose_model` ComboBox: **`cpsam` / `cpsam_v2`**.
  cellpose 4.x is SAM-only (`models.Cellpose` + cyto/nuclei removed); dispatch is
  `CellposeModel(pretrained_model=...)`. `cpdino`/`cpdino-vitb` are in `MODEL_NAMES` but
  need the DINOv3 package the env doesn't ship → removed (Codex review #2). "cellpose 3"
  (cyto3) needs a separate cellpose-3.x env → follow-up.
- **Membrane-snap refinement (E2)** — optional "Snap boundaries to membrane" checkbox.
  Host-side seeded watershed (`refine_to_membrane`, uses epicure's skimage) flowing on the
  membrane intensity, cellpose labels as seeds. It **grows** the cells to tile the frame
  (fills cellpose's background gaps) AND lands boundaries on the bright membrane, following
  its curvature — image-based, unlike flat geometric `expand_labels`. Preserves cell count.
  Off by default (raw cellpose labels otherwise).
- **Representation decision** — **filled labels are the right output for EpiCure**, not a
  thin junction mesh. EpiCure is label-based (it skeletonizes+fills any junction input via
  `junctions_to_label`), so cellpose labels feed it with zero conversion; a mesh would be a
  lossy round-trip. On-screen line thickness is napari's Labels `contour` setting, not data.
- **UI fix** — after segmenting, `hide_segment_options()` collapses the whole "generate a
  segmentation" block (both buttons + cellpose widgets + "OR" separators) so no dangling
  "OR" is left behind.
- **Codex reviews #2 & #3** — all findings triaged/fixed: cpdino removed, py3.9 classifier
  removed, refine guarded on empty/single-cell frames, CUDA doc claim corrected. Remaining
  low findings (uint16 save, dtype edge cases) judged safe for real cellpose per-frame data.

## Findings (research this session, not code)

- **Benchmark vs EpySeg** (101-frame movie): cellpose-SAM 223s (2.2s/frame, ~175 cells) vs
  EpySeg 256s (2.5s/frame, ~183). Tracking (EpiCure overlap): cellpose far cleaner — 1208
  vs 2690 tracks, mean length 14.6 vs 6.8 frames. Cellpose wins detection/counting/tracking.
- **Membrane accuracy** (membrane-marker data): cellpose puts boundaries ~15% below the
  membrane peak (cytosol edge); EpySeg sits on the membrane. The E2 watershed recovers most
  of it (boundary-on-membrane 83→108–121). For pure junction fidelity EpySeg is still the
  baseline; cellpose+E2 is competitive.
- **CAREamics denoise (N2V2)** — retrained on the movie, visually excellent. But: it does
  **not** change cellpose detection/counts, and (tested on frames 60–75) **does not** help
  cellpose capture a division. Its value is boundary/noise quality, **not** division capture
  or detection. → not worth wiring into the button for divisions.
- **Divisions** — cellpose is a whole-cell detector; it keeps a dividing cell as one label
  until cytokinesis fully closes the wall, so forming divisions aren't segmented as two
  daughters (denoise doesn't fix this). Divisions in EpiCure are semi-manual: split the cell
  in Edit, then the tracker links daughters. Splitting-cutoff semantics: cost is
  `dist²/max_distance²`, cutoff is `splitting_cost²`, so **0.2 → only ~6px → 0 divisions**;
  use **~0.4–0.5** (~12–15px) for real mitoses. Not a plugin gap.

## Not yet specified (fog, in scope, graduates later)

- **cellpose-3.x second env (cyto3 & the classic/denoising models)** — a separate
  `pixi_cellpose3.toml` + env, routed by model choice, since cellpose 4.x can't load them.
- **Real CUDA env** — the Linux/Windows feature is currently a stub resolving to CPU torch;
  configure a genuine CUDA PyTorch target + test on a GPU box.
- **Custom / user-trained model loading.**
- Multi-channel movie handling beyond the default channel mapping.

## Out of scope (ruled beyond the destination)

- **3D cellpose (`do_3D`)** — user chose 2D slice-by-slice.
- **Removing or replacing the EpySeg feature** — cellpose is purely additive.
- **Thin junction-mesh / skeleton output** — decided filled labels are the right EpiCure
  input; a mesh would be a lossy round-trip. Only relevant for analysis *outside* EpiCure.
- **CAREamics denoise integrated as a button pre-step** — tested negative for divisions and
  neutral for detection; a boundary-quality nicety only, not worth the added weight now.
- **Automated division detection** — cellpose can't catch the furrow moment; needs manual
  correction or a mitosis-specific detector, a separate tool from this button.

---

## Tickets

**All tickets closed — the map reached its destination (working, verified button),** plus
an in-session expansion (model dropdown E1, membrane-snap E2, UI fix, 3 Codex reviews) all
captured under "Decisions so far" / "Findings" above. Frontier at charting time was **R1**
only. Remaining fog (cyto3 env, real CUDA) is tracked under "Not yet specified".

### R1 — Extract & pin the cellpose-SAM 2D-per-frame call `[research]`
- **status:** CLOSED (see Decisions so far)
- **blocked-by:** —
- **blocks:** D2, T2, T3
- **Question:** From the local working code (`dapiVolumeCalc/worker_cellpose.py`,
  `scratch_cpsam_*.py`, `compare_cellpose_models.py`, `cellpose_napari` usage), extract
  the exact cellpose 4.x (SAM) API: model construction, `eval` params (diameter,
  flow/cellprob thresholds, channels, normalize, batch), how frames are looped for a
  2D+t movie, and the output shape/dtype. This ticket's answer **is** the pinned
  version + default param set the rest of the map builds on.

### D2 — pixi env design that reuses local caches (no re-download) `[decision]`
- **status:** CLOSED (see Decisions so far). Artifact: `resources/pixi_cellpose.toml`.
- **blocked-by:** R1
- **blocks:** T1
- **Question:** Design the cellpose pixi environment: python version (3.10, like EpySeg),
  cellpose + torch declared as `[pypi-dependencies]` so pixi/uv reuses `~/.cache/uv`,
  a Mac arm64 default feature now + a CUDA feature stub mirroring EpySeg's split.
  Decide whether to extend the existing `pixi.toml` or add a separate env. Confirm the
  resolution plan avoids fresh multi-GB downloads.

### T1 — Build the cellpose pixi env on M4 `[task]`
- **status:** CLOSED — built end-to-end (see Decisions: T1). ~40MB pulled (user-approved).
- **blocked-by:** D2
- **blocks:** T4
- **Finding:** torch 2.11.0 + torchvision 0.26.0 + cpsam weights are **cache-resident**
  (no big pull). But on py3.10 the small compiled deps (numpy, scipy, fastremap,
  fill-voids, imagecodecs) are cached only for cp311/cp313 in `~/.cache/uv`, so a clean
  `pixi install` would still pull **~40MB** (scipy ~25MB the largest). No single python
  version has everything cached (cache is a cross-project grab-bag). Options for the user:
  (a) accept the ~40MB one-time build now; (b) defer the pixi build to a networked
  machine / later and keep the toml as the shippable artifact, validating the cellpose
  logic locally against `cellpose_napari/.venv` (already done for the inner loop).

### T2 — Write `appose_cellpose.py` runner `[task]`
- **status:** DONE (pending Codex review + a real appose run in T4).
  Artifact: `src/epicure/appose_cellpose.py`. Inner cellpose loop validated against real
  cellpose 4.0.8. Key deviation from epyseg: a **separate uint32 output buffer** (input is
  uint8/uint16, labels need uint32) rather than reusing the input shared-memory buffer.
- **blocked-by:** R1, T1
- **blocks:** T3, T4

### T3 — Wire the "Segment with cellpose" UI button `[task]`
- **status:** DONE (pending GUI verify in T4). `start_epicuring.py`: `segment_with_cellpose`
  PushButton + `launch_cellpose()` handler + signal + 5 visibility toggles, mirroring
  EpySeg; writes `..._cellpose.tif` (uint16) into `segmentation_file`. Syntax-compiles.
- **blocked-by:** R1, T2
- **blocks:** T4, T5
- **Question:** In `start_epicuring.py`, add a `segment_with_cellpose` PushButton +
  `launch_cellpose()` handler + signal wiring + visibility toggles, mirroring the EpySeg
  button. Handler builds the `parameters` dict (decide the minimal exposed set here:
  diameter, channel, thresholds; model fixed for now), runs `go_cellpose`, writes
  `..._cellpose.tif`, and assigns it to `get_files.segmentation_file.value`.

### T4 — Verify end-to-end on a real 2D+t movie `[task]`
- **status:** CLOSED — verified two ways: (1) the real appose+pixi subprocess on a synthetic
  movie, and (2) **the user ran the button in a live napari session** on the 101-frame movie,
  which segmented all frames and saved the file. Fully exercised.
- **blocked-by:** T1, T2, T3
- **blocks:** —

### T5 — Docs page + README/installation mention `[task]`
- **status:** CLOSED — `docs/Segment-cellpose-option.md` + mkdocs nav entry, mirroring the
  EpySeg page. (README already lists cellpose as an external segmenter.)
- **blocked-by:** T3
- **blocks:** —

---

### Blocking graph
```
R1 ──> D2 ──> T1 ──┐
  │                ├─> T2 ──┐
  └────────────────┘        ├─> T3 ──> T5
                            │    │
                            └────┴─────> T4
```
