!!! abstract "Track temporally the cells"
    _Most track options are in the Track tab of the Main interface_

EpiCure handles tracks by using the same label for the corresponding cell accross frames.
One cell has a unique number (its label), displayed with a specific color assigned by Napari, that corresponds to the track number as well.
The file containing the segmentation with the labelled cells is thus enough to reconstruct the tracks.

Cell divisions are organised in a graph and displayed with the `events` structure (see [Inspect](#Inspect.md#events)).
The graph is a NetworkX object and contains as keys the daugther cells and as values the parent cell.
This implementation is compatible with laptrack's output and Napari Track layer.

EpiCure opens a Tracks layer in Napari that displays the trajectories of each cell (label) centroid.
!!! warning "This layer is very slow to update, so it is NOT updated at each action." 
	A local version of the tracks is kept up-to-date with the modifications done, but not the displayed version. To update the display to the latest version, click on Update tracks.

With the EpiCure Track panel, you can choose a tracking algorithm and tune its parameter.
It's also possible to track the cells in an other software/plugins.

## Track with TrackAstra

`TrackAstra` is an additional tracking method in the Track tab. It does not
replace either Laptrack option. In this hybrid method, TrackAstra 0.5.3 assigns
adjacent-frame cell identities and division relationships using the fixed
`general_2d` model, while Laptrack is used only to reconnect compatible open
track ends across missing segmentations.

The initial supported platform is Apple Silicon macOS (ARM64). On the first run,
EpiCure provisions an isolated environment and downloads the model; this may take
several minutes. Later runs reuse the cached environment. TrackAstra uses MPS when
it is available and otherwise falls back to CPU. Provisioning or inference
failure leaves the current segmentation, graph, events, and corrections unchanged.

### Shared controls and preprocessing

- `Track only some frames` applies the inclusive tracking range to TrackAstra.
  Frames and valid relationships outside that range are preserved.
- `Remove border cells` supplies the shared border distance. The production
  default is 1 pixel, and whole border detections are excluded only inside the
  selected tracking range.
- `Gap-closing frames` has the same meaning for both tracker families. A value
  of 5 bridges up to four missing frames; 1 disables gap repair.
- Drift correction is automatically unchecked and disabled while TrackAstra is
  selected. It becomes available again after choosing Laptrack.

TrackAstra never creates or repairs segmentation masks. The segmentation visible
when Track is clicked is the authoritative detection set, so segmentation edits
are respected on every rerun. Unmatched detections remain as singleton cell
tracks rather than disappearing.

### Rerunning after manual corrections

Manual track joins, splits, swaps, and division changes are retained as protected
or forbidden decisions keyed to frame-local detections. A later TrackAstra run
recomputes automatic links but reapplies valid human decisions as hard constraints.
If a segmentation edit removes a correction endpoint, EpiCure keeps the evidence
and shows the missing endpoint in the Track tab instead of guessing another cell.
Correct the segmentation/relationship and rerun, or use `Dismiss first correction
conflict` to deliberately remove that retained correction.

### Inspect and saved results

All TrackAstra divisions use EpiCure's native graph and normal division display.
Inspect additionally queues divisions whose minimum association score is below
0.9 or whose parent-versus-combined-daughters area ratio exceeds 1.5. Gap repairs
are queued when their area ratio exceeds 2.0 or displacement exceeds 15 pixels per
frame. Review flags do not remove graph edges and rerunning replaces them only
inside the selected range. Existing human classifications and out-of-range events
remain intact.

A track appearance or disappearance is only an observation. TrackAstra does not
diagnose ingression, extrusion, or cell fusion; those classifications remain owned
by EpiCure's Inspect workflow and the user.

Saving writes the native labels, Tracks data, graph, method provenance, correction
ledger, conflicts, and Inspect events to the normal `epics` folder. It also writes
`<movie>_lineage.csv`, with columns `label`, `t1`, `t2`, and `parent`, from the
final committed EpiCure graph. Reopening restores the same identities and lineage.

## Import/Load tracking
To use tracking from an external software, the cells need to be labelled by their track number to be loaded in EpiCure. 
Cell divisions/merges will not be loaded from external tracks.

### Division detection
Cell divisions can be detected by going in the [Inspect](./Inspect.md) interface, and select `get_divisions` in the `Track options` panel.
This option looks for two tracks that appear at the same frame, are touching and have a potential parent track (a track ending in the previous frame without being in a division or extrusion event). 

Thus, if you load results from an external tracking software, as TrackMate, a division event should be detected without having to load the division information from that software (the format of the division implementation can vary between software so it can be convenient to not rely on it).

### Load TrackMate tracks
In particular, you can perform the cell segmentation and tracking in [TrackMate](https://imagej.net/plugins/trackmate/) and use the Action `Export label image`.
Then load this labelled image as the segmentation file in EpiCure and you will directly get the tracks.
However, the division and extrusion will have to be detected within EpiCure afterward.

## Track with Laptrack

Tracking within EpiCure can be performed with the [Laptrack](https://github.com/yfukai/laptrack) module.
Laptrack will optimize the linking of the cell from one frame to another, and can also include the possibility for cell division or cell merging.
As in our movies, we don't have cell merging biologically, we disabled this feature but it can easily be integrated.

### Laptrack centroids

With this option, Laptrack considers the distance between the centroid of the cells from one frame to another to optimize the linking.
Thus this method has good performance in general when the cell's center displacement are smaller than the size of the cell itself (it's less likely to confuse the cell with its neighbor).

### Laptrack overlap

With this option, Laptrack considers the overlap of the segmented cells from one frame to another to optimize the linking.
This method relies on more information than taking only the cell's centroid as it takes into account the full surface distances.
It necessitates the cell motion to be small enough for the cell to stay mainly within the previous cell surface.

### Add feature cost
With both options, it's also possible to take into account the size or the shape of the cell in the linking calculation.
This will improve the tracking when the cell is similar from one frame to another so it will increase the capacity of the algorithm to "recognize" the cell.
This can be done by checking the `add feature cost` in the interface.

### Gap-closing
A cell can briefly disappear from the segmentation for a few frames (a missed detection, or a cell moving out of focus) and then reappear. Without gap-closing this breaks the cell's track in two. The `Gap-closing frames` option lets Laptrack bridge such a gap, linking the cell across the missing frames so it keeps a single track.

The value sets how large a gap to bridge: a cell absent for up to (value − 1) frames keeps its track, so `1` disables gap-closing. A bridged track still has no label in the skipped frames, so it is still reported as a gap in the [Inspect](./Inspect.md) panel.

This option is available with the Laptrack centroids method.

### Drift correction
This option allows to take into account local drift in the tracking algorithm.
When there is a fast local movement of all cells in the same direction, the algorithm is more likely to fail as the distance between the cell centroids or their overlaps will be higher than the distance/overlap with another cell. 
This helps to correct it, by calculating the local overall drift and removing this drift from the distance calculation.

Local drift is estimated with optical flow.
This is however quite slow to calculate, so adding this option will significantly increase the computation time.


### Shortcuts
You can select the `Track` layer in the left part of the interface to change the display properties of this layer.
EpiCure proposes also a few shortcuts to change this display directly without having to select this layer, keeping the `Segmentation` layer selected.
General shortcuts are documented [here](index.md/#general-options).

???+ tip "Shortcut/options"

     _**EpiCure shortcuts are only active when `Segmentation` layer is selected**_

	=== "Track display :wrench:"
	
		|   |     |	
		| ------------ | ------------------------------------ |
		| <kbd>r</kbd> | Show/Hide the Track layer |
		| <kbd>l</kbd> | Color tracks by lineage (color of the first mother cell) |


---

