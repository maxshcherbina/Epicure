# TrackAstra division-curation baseline

Saved from EpiCure on 2026-07-13 after running the hybrid TrackAstra method on
`small_crop23-123_8bit.tif` and applying manual review corrections.

This snapshot is a useful starting point for reviewing and curating division
relationships. It is **not** segmentation ground truth: the segmentation still
contains substantial merge and shape errors that can create false division
proposals.

Files:

- `small_crop23-123_8bit_labels.tif` — committed EpiCure labels;
- `small_crop23-123_8bit_epidata.pkl` — graph, tracking metadata, Inspect state,
  human correction ledger, and conflicts;
- `small_crop23-123_8bit_lineage.csv` — lineage derived from the committed graph.

Snapshot summary:

- 12,214 tracked detections across 416 cell tracks;
- 62 TrackAstra division proposals;
- 81 constrained LapTrack gap repairs;
- 9 retained human corrections;
- 0 unresolved correction conflicts;
- 416 lineage CSV rows.

Known example: the frame 27→28 division involving label 4002 is a false
merge-then-split proposal caused by an oversized merged mask. Follow-up is
tracked in Beads issue `cellpose-support-jbi`. The correction-conflict UI work is
tracked in `cellpose-support-dms`.
