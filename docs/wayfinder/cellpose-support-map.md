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

<!-- one line per closed ticket; empty at charting time -->

_(none yet — charting session)_

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
- **status:** open (frontier)
- **blocked-by:** —
- **blocks:** D2, T2, T3
- **Question:** From the local working code (`dapiVolumeCalc/worker_cellpose.py`,
  `scratch_cpsam_*.py`, `compare_cellpose_models.py`, `cellpose_napari` usage), extract
  the exact cellpose 4.x (SAM) API: model construction, `eval` params (diameter,
  flow/cellprob thresholds, channels, normalize, batch), how frames are looped for a
  2D+t movie, and the output shape/dtype. This ticket's answer **is** the pinned
  version + default param set the rest of the map builds on.

### D2 — pixi env design that reuses local caches (no re-download) `[decision]`
- **status:** blocked
- **blocked-by:** R1
- **blocks:** T1
- **Question:** Design the cellpose pixi environment: python version (3.10, like EpySeg),
  cellpose + torch declared as `[pypi-dependencies]` so pixi/uv reuses `~/.cache/uv`,
  a Mac arm64 default feature now + a CUDA feature stub mirroring EpySeg's split.
  Decide whether to extend the existing `pixi.toml` or add a separate env. Confirm the
  resolution plan avoids fresh multi-GB downloads.

### T1 — Build the cellpose pixi env on M4 `[task]`
- **status:** blocked
- **blocked-by:** D2
- **blocks:** T2, T4
- **Question:** Add the cellpose env to `src/epicure/resources/pixi.toml` (or a sibling
  spec) and confirm `appose.pixi(...).environment(...).build()` actually builds on Mac
  arm64 reusing caches, with no large download. This is the slow/risky ticket.

### T2 — Write `appose_cellpose.py` runner `[task]`
- **status:** blocked
- **blocked-by:** R1, T1
- **blocks:** T3, T4
- **Question:** Mirror `appose_epyseg.py`: pass the movie via shared memory, run cellpose
  slice-by-slice in the isolated subprocess, return an int label stack. Expose a
  `go_cellpose(image, parameters, ...)` matching the EpySeg signature.

### T3 — Wire the "Segment with cellpose" UI button `[task]`
- **status:** blocked
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
