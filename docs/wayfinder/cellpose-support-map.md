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
  — no big download. Caveat feeding T1 below.

## Not yet specified (fog, in scope, graduates later)

- **Model-selection dropdown** in the button UI (choose among cellpose models). Default
  to newest (cpsam) for now; graduates once T3 works with a single fixed model.
- **CUDA / Windows / Linux env variant + testing.** Structure it now, test later when
  a CUDA machine is available.
- **Custom / user-trained model loading.**
- Multi-channel movie handling beyond the default channel mapping.

## Out of scope (ruled beyond the destination)

- **3D cellpose (`do_3D`)** — user chose 2D slice-by-slice.
- **Removing or replacing the EpySeg feature** — cellpose is purely additive.

---

## Tickets

Frontier at charting time (open + unblocked): **R1** only.

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
- **status:** BLOCKED ON USER (bandwidth decision) — awaiting steer.
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
- **status:** blocked
- **blocked-by:** T1, T2, T3
- **blocks:** —
- **Question:** Drive the button in napari on a real movie (or the test fixture): cellpose
  → mask → loads/edits/tracks in EpiCure with no loader changes. Use the `verify` skill.

### T5 — Docs page + README/installation mention `[task]`
- **status:** blocked
- **blocked-by:** T3
- **blocks:** —
- **Question:** Add a cellpose docs page paralleling `docs/Segment-option.md`, and mention
  it in README / Installation, matching how EpySeg is documented. In scope because this
  is meant to be upstreamed.

---

### Blocking graph
```
R1 ──> D2 ──> T1 ──┐
  │                ├─> T2 ──┐
  └────────────────┘        ├─> T3 ──> T5
                            │    │
                            └────┴─────> T4
```
