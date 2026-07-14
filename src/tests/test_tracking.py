import numpy as np
import os
import pandas as pd
import epicure.epicuring as epi
from epicure.laptrack_centroids import LaptrackCentroids

def test_track_methods(make_napari_viewer):
    """ Tracking with EpiCure with Laptrack, different parameters """
    test_img = os.path.join(".", "test_data", "003_crop.tif")
    test_seg = os.path.join(".", "test_data", "003_crop_epyseg.tif")

    ## load and initialize
    viewer = make_napari_viewer()
    epic = epi.EpiCure(viewer)
    epic.load_movie(test_img)
    epic.go_epicure("test_epics", test_seg)

    ## no tracked yet 
    assert epic.tracked == 0
    alllabels = epic.nlabels()
    assert alllabels == 1294

    # default tracking
    track = epic.tracking
    ## Chosse method overlap for tracking
    track.track_choice.setCurrentText("Laptrack-Overlaps")
    track.min_iou.setText("0.1")
    track.split_cost.setText("0.5")
    track.merg_cost.setText("0")
    track.do_tracking()
    ## after tracking should have much less labels now
    ntracks = epic.nlabels()
    assert ntracks < alllabels 
    assert ntracks == track.nb_tracks()
    assert track.graph is not None
    ## This crop's former division candidates are all removed by the shared
    ## border-cell exclusion that now precedes every tracking method.
    assert track.graph == {}
    assert not track.check_gap()

    ## check reset function: reread the tracks from the labels (so should be the same)
    track.reset_tracks()
    assert epic.nlabels() == ntracks 
    assert epic.nlabels() == track.nb_tracks()

    ## check one surviving track's validity after border exclusion
    track_id = track.get_track_list()[20]
    assert track_id > 0
    assert track.get_first_frame( track_id ) == 0
    feats = track.measure_track_features( track_id )
    assert feats["TrackDuration"] == 11
    assert feats["NbGaps"] == 0 
    assert feats["Label"] == track_id 

    # Operations to get last frame, remove it
    last = track.get_last_frame(track_id)
    track.remove_one_frame( track_id, last )
    newlast = track.get_last_frame(track_id)
    assert last == newlast+1

    ## create a gap in the middle of the track, then fix it (split the track)
    midle = track.get_first_frame(track_id) + 2
    track.remove_one_frame( track_id, midle )
    gaped = track.check_gap()
    ## gaps are allowed now
    assert len(gaped) > 0
    epic.handle_gaps( None )
    assert track.nb_tracks() == ntracks + 1

def _gap_regionprops_df():
    """ Synthetic regionprops table for the centroid tracker: cell A near
    (10,10) vanishes for frames 2-3 then returns ~1px away; cell B near (50,50)
    is present every frame as a stable reference. Columns match
    LaptrackCentroids.region_properties (area/solidity unused, penalties=0). """
    rows = [
        ## (frame, centroid-0, centroid-1)
        (0, 10, 10), (0, 50, 50),
        (1, 11, 10), (1, 50, 50),
        (2, 50, 50),               ## A missing
        (3, 50, 50),               ## A missing
        (4, 12, 10), (4, 50, 50),  ## A returns
        (5, 12, 10), (5, 50, 50),
    ]
    recs = [ {"label": lab, "frame": frame, "centroid-0": c0, "centroid-1": c1,
              "area": 100, "solidity": 0.9}
             for lab, (frame, c0, c1) in enumerate(rows, start=1) ]
    return pd.DataFrame(recs)

def _track(gap_frames, df):
    """ Run the centroid tracker at a given gap_frames; return the track table.
    track/epic are unused on the tracking path so None is fine. """
    lc = LaptrackCentroids(None, None)
    lc.gap_frames = gap_frames
    track_df, _, _ = lc.perform_track(df.copy())
    return track_df

def test_laptrack_centroids_gap_closing():
    """ Gap-closing: a cell absent for 2 frames keeps a single track when
    gap_frames spans the gap, and breaks into two when gap_frames=1 (off). """
    df = _gap_regionprops_df()

    ## the gappy cell A lives in column centroid-1 == 10
    closed = _track(5, df)
    a_closed = closed[closed["centroid-1"] == 10]
    assert closed["track_id"].nunique() == 2     ## A bridged + B
    assert a_closed["track_id"].nunique() == 1   ## A is one track across the gap

    opened = _track(1, df)
    a_opened = opened[opened["centroid-1"] == 10]
    assert opened["track_id"].nunique() == 3     ## A split in two + B
    assert a_opened["track_id"].nunique() == 2   ## A broken into pre/post gap

if __name__ == "__main__":
    test_track_methods()
    print("********* Test tracking cure completed ***********")
