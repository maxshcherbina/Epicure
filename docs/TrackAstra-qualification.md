# TrackAstra ARM64 qualification

Qualification date: 2026-07-13

## Production reference run

The complete hybrid TrackAstra workflow was exercised through EpiCure's normal
Track action and save/reopen lifecycle on Apple Silicon:

- movie: `small_crop23-123_8bit.tif`, 101 frames, 332 × 528 pixels;
- authoritative Cellpose masks: `small_crop23-123_8bit.tif_cellpose.tif`;
- shared border exclusion: symmetric EpiCure border size 1;
- TrackAstra: 0.5.3, `general_2d`, greedy division-aware mode;
- compute device: MPS;
- shared gap-closing value: 5, allowing one through four missing frames.

| Metric | Earlier standalone benchmark | Integrated hybrid qualification |
|---|---:|---:|
| Retained detections represented | 12,058 / 12,110 | 12,134 / 12,134 |
| TrackAstra associations | 11,760 edges | 11,788 edges |
| TrackAstra divisions | 84 | 79 |
| Constrained gap repairs | 0 | 73 |
| Native EpiCure cell tracks | 466 | 431 |
| Single-frame tracks | 15 | 27 |
| Median cell-track span | 19 frames | 23 frames |
| Tracks containing repaired gaps | 0 | 51 |
| Track action wall time | 7.8 s, worker only on CPU | 30.1 s, complete EpiCure action on MPS |

The integrated result conserves every retained segmentation detection, including
TrackAstra-unmatched detections, and converts every accepted division to two native
daughter relationships. Saving and reopening reproduced identical labels, Tracks
data, graph, provenance, events, and a 431-row committed-graph lineage CSV.

The earlier 12,110 comparison set contained a preprocessing asymmetry: it removed
33 cells exactly two pixels from only the bottom or right edge. Current EpiCure
uses symmetric whole-label border-band semantics. If any component of a frame-local
label touches that band, all components of that cell are removed; this matters in
ten frames of the reference masks. The input difference and the integrated
constrained gap pass explain why the counts do not exactly match the standalone
table.

## Other qualification evidence

- The cached real ARM64 worker smoke passed and returned scored association and
  division tables. The worker selects MPS when available and permits CPU fallback.
- Synthetic normal-action tests cover a selected tracking range, collision-safe
  boundary identity preservation, 1-pixel exclusion limited to that range, drift
  inhibition, singleton restoration, native divisions, and Inspect review flags.
- Save/reopen tests cover exact labels, Tracks data, graph, gap provenance, method
  provenance, correction ledger, conflicts, legacy project defaults, and lineage CSV.
- Rerun tests cover authoritative segmentation edits; protected/forbidden joins,
  splits, swaps, and divisions; repeated reruns; invalid endpoints; explicit conflict
  dismissal; and persistence of unresolved evidence.
- Worker and transaction tests force provisioning/inference failure, cancellation,
  malformed output, validation failure, and commit-side-effect failure. Live labels,
  tracks, graph, events, correction ledger, conflicts, and metadata roll back.
- The routine suite exercises Laptrack-Centroids, Laptrack-Overlaps, preferences,
  Inspect, TrackMate/GEFF interoperability, and legacy project loading.

Current release limits are Apple Silicon macOS, 2D movies, the fixed `general_2d`
model, and greedy division-aware linking. TrackAstra does not correct segmentation,
bridge missing masks itself, classify ingression/extrusion, or represent a two-parent
cell merge. EpiCure and its constrained Laptrack/Inspect passes retain those duties.
