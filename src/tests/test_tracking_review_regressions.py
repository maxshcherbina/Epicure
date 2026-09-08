import pytest
from epicure.tracking_transaction import TrackingBoundaryError
import numpy as np
from test_tracking_action_transaction import _synthetic_epicure
from epicure.appose_trackastra import Detection, Association, Division, TrackAstraResult

def setup(epic, labels):
    epic.seg=labels
    epic.seglayer.data=labels
    epic.tracking.reset_tracks()
    epic.tracking.track_choice.setCurrentText('TrackAstra')
    epic.tracking.gap_frames_line.setText('1')

def response(labels, edges=(), divisions=()):
    detections=[]
    for frame,mask in enumerate(labels):
        for label in np.unique(mask[mask>0]):
            y,x=np.where(mask==label)
            detections.append(Detection(frame,int(label),float(y.mean()),float(x.mean())))
    return TrackAstraResult(1,'0.5.3','general_2d','cpu',tuple(detections),edges,divisions)

def test_protection_survives_real_commit_and_second_run(make_napari_viewer,tmp_path):
    epic=_synthetic_epicure(make_napari_viewer,tmp_path)
    labels=np.zeros((4,10,10),dtype=np.uint32)
    labels[0,3:5,3:5]=5
    labels[1:3,3:5,3:5]=10
    setup(epic,labels)
    tracking=epic.tracking
    tracking.set_association_correction((1,10),(2,10),'protected')
    tracking._trackastra_runner=lambda movie,masks,**kw: response(masks,(Association(0,5,1,10,0.9),))
    tracking.do_tracking()
    assert epic.seg[1,3,3]==epic.seg[2,3,3]
    tracking._trackastra_runner=lambda movie,masks,**kw: response(masks)
    tracking.do_tracking()
    assert epic.seg[1,3,3]==epic.seg[2,3,3], 'Protected join is lost on second real Track action'

def test_partial_division_has_valid_parent_lifetime(make_napari_viewer,tmp_path):
    epic=_synthetic_epicure(make_napari_viewer,tmp_path)
    labels=np.zeros((4,10,10),dtype=np.uint32)
    labels[:,3:5,3:5]=10
    labels[2,6:8,6:8]=30
    setup(epic,labels)
    tracking=epic.tracking
    tracking.frame_range.setChecked(True)
    tracking.start_frame.setValue(1)
    tracking.end_frame.setValue(2)
    tracking._trackastra_runner=lambda *a,**kw: TrackAstraResult(1,'0.5.3','general_2d','cpu',
        (Detection(1,10,3.5,3.5),Detection(2,10,3.5,3.5),Detection(2,30,6.5,6.5)),
        (Association(1,10,2,10,0.95),Association(1,10,2,30,0.95)),
        (Division(1,10,2,10,30,0.95,0.95),))
    before = epic.seg.copy()
    with pytest.raises(TrackingBoundaryError, match="Expand the tracking range"):
        tracking.do_tracking()
    np.testing.assert_array_equal(epic.seg, before)
    assert not tracking.conflict_status.isHidden()
    assert tracking.dismiss_conflict.isHidden()
    assert not tracking.graph


def test_join_does_not_leave_correction_to_temporary_label(make_napari_viewer,tmp_path):
    epic=_synthetic_epicure(make_napari_viewer,tmp_path)
    epic.forbid_gaps=False
    epic.editing.tracks_temporal_merging(10,np.array((1,2,2)),20,np.array((3,6,2)))
    for entry in epic.tracking.correction_ledger:
        for key in ('source','target'):
            frame,label=entry[key]
            assert np.any(epic.seg[frame]==label), f'Correction points to vanished temporary label: {entry}'

@pytest.mark.parametrize('missing_frame', [0, 2])
def test_missing_boundary_endpoint_is_a_conflict(missing_frame):
    from epicure.tracking_corrections import association_correction, reconcile_association_edges
    keys = [(frame, 10) for frame in range(3) if frame != missing_frame]
    _, _, conflicts = reconcile_association_edges(
        keys, (), [association_correction((0, 10), (2, 10), 'protected')],
        tracking_range=(0, 2),
    )
    assert len(conflicts) == 1
    assert conflicts[0].tracking_range == (0, 2)
    assert str((missing_frame, 10)) in conflicts[0].reason


def test_concave_cell_keeps_gap_review_on_its_own_identity(make_napari_viewer, tmp_path):
    epic = _synthetic_epicure(make_napari_viewer, tmp_path)
    masks = np.zeros((4, 10, 10), dtype=np.uint32)
    masks[0, 2:8, 2:8] = 10
    masks[0, 3:7, 3:7] = 0
    masks[3] = masks[0]
    masks[3, 4:6, 4:6] = 20  # The centroid is inside another cell.
    setup(epic, masks)
    epic.inspecting.review_tracking_decisions({
        'method': 'TrackAstra', 'range': (0, 3),
        'gap_repairs': ({'target': (3, 10), 'target_y': 4.5, 'target_x': 4.5,
                         'area_ratio': 3, 'distance_per_frame': 1},),
    })
    ids = epic.inspecting.get_events_from_type('laptrack-gap-review')
    assert len(ids) == 1
    index = epic.inspecting.index_from_id(ids[0])
    assert epic.inspecting.events.properties['label'][index] == 10


def test_border_exclusion_removes_annotations_and_rollback_restores_them(make_napari_viewer, tmp_path, monkeypatch):
    from epicure.tracking_transaction import TrackingProposal
    epic = _synthetic_epicure(make_napari_viewer, tmp_path)
    tracking = epic.tracking
    epic.groups = {'border': [90], 'kept': [10]}
    epic.inspecting.add_event((1, 0, 8), 90, 'human-classified', force=True)
    tracking.register_tracking_method('Laptrack-Centroids', lambda start, end, masks:
        TrackingProposal(start, end, masks, masks.copy(), {}, 'test'))
    original = epic.finish_update
    def fail(*args, **kwargs):
        raise RuntimeError('commit failed after annotation update')
    monkeypatch.setattr(epic, 'finish_update', fail)
    with pytest.raises(RuntimeError, match='commit failed'):
        tracking.do_tracking()
    assert epic.groups == {'border': [90], 'kept': [10]}
    assert epic.inspecting.nb_type('human-classified') == 1
    monkeypatch.setattr(epic, 'finish_update', original)
    tracking.do_tracking()
    assert epic.groups == {'kept': [10]}
    assert epic.inspecting.nb_type('human-classified') == 0


def test_missing_endpoint_does_not_rebind_to_reused_label(make_napari_viewer, tmp_path):
    epic = _synthetic_epicure(make_napari_viewer, tmp_path)
    labels = np.zeros((4, 10, 10), dtype=np.uint32)
    labels[0, 3:5, 3:5] = 5
    labels[1:3, 3:5, 3:5] = 10
    setup(epic, labels)
    tracking = epic.tracking
    tracking.set_association_correction((1, 5), (2, 10), 'protected')
    tracking._trackastra_runner = lambda movie, masks, **kw: response(masks, (Association(0, 5, 1, 10, 0.9),))
    tracking.do_tracking()
    tracking._trackastra_runner = lambda movie, masks, **kw: response(masks)
    tracking.do_tracking()
    assert epic.seg[1, 3, 3] != epic.seg[2, 3, 3]
    assert len(tracking.tracking_conflicts) == 1


def test_division_correction_survives_relabel_and_save_reopen(make_napari_viewer, tmp_path):
    from epicure.epicuring import EpiCure
    epic = _synthetic_epicure(make_napari_viewer, tmp_path)
    masks = np.zeros((4, 10, 10), dtype=np.uint32)
    masks[0, 3:5, 3:5] = 5
    masks[1, 3:5, 3:5] = 10
    masks[2:, 2:4, 2:4] = 20
    masks[2:, 6:8, 6:8] = 30
    setup(epic, masks)
    tracking = epic.tracking
    tracking.set_division_correction((1, 10), ((2, 20), (2, 30)), 'protected')
    tracking._trackastra_runner = lambda movie, labels, **kw: response(labels, (Association(0, 5, 1, 10, 0.9),))
    tracking.do_tracking()
    assert tracking.correction_ledger[0]['parent'] == (1, 5)
    epic.save_epicures()
    reopened = EpiCure(make_napari_viewer())
    movie_layer = reopened.viewer.add_image(np.zeros(masks.shape, dtype=np.uint8))
    reopened.movie_from_layer(movie_layer, str(tmp_path / 'synthetic.tif'))
    reopened.set_epithelia(False)
    reopened.go_epicure(str(tmp_path / 'epics'), str(tmp_path / 'epics' / 'synthetic_labels.tif'))
    reopened.tracking.track_choice.setCurrentText('TrackAstra')
    reopened.tracking.gap_frames_line.setText('1')
    reopened.tracking._trackastra_runner = lambda movie, labels, **kw: response(labels)
    reopened.tracking.do_tracking()
    assert len(reopened.tracking.graph) == 2
    assert reopened.tracking.tracking_conflicts == []
    assert len(reopened.tracking.tracking_method_metadata['replayed_division_corrections']) == 1


def test_manual_relabel_keeps_existing_corrections_attached(make_napari_viewer, tmp_path):
    epic = _synthetic_epicure(make_napari_viewer, tmp_path)
    epic.tracking.set_association_correction((0, 10), (1, 10), 'protected')
    epic.replace_label(10, 42, 1)
    assert epic.tracking.correction_ledger[0]['target'] == (1, 42)
    assert epic.tracking.correction_ledger[0]['source'] == (0, 10)


def test_spatial_merge_keeps_split_correction_endpoints(make_napari_viewer, tmp_path):
    epic = _synthetic_epicure(make_napari_viewer, tmp_path)
    masks = np.zeros((4, 10, 10), dtype=np.uint32)
    masks[:, 2:6, 2:4] = 10
    masks[:2, 2:6, 4:6] = 20
    setup(epic, masks)
    epic.editing.tracks_spatial_merging(10, np.array((1, 3, 3)), 20)
    for entry in epic.tracking.correction_ledger:
        for name in ('source', 'target'):
            frame, label = entry[name]
            assert np.any(epic.seg[frame] == label), entry


def test_manual_relabel_maps_all_frames_not_pixel_coordinates(make_napari_viewer, tmp_path):
    epic = _synthetic_epicure(make_napari_viewer, tmp_path)
    masks = np.zeros((4, 10, 10), dtype=np.uint32)
    masks[:, 2:4, 2:4] = 10
    setup(epic, masks)
    epic.tracking.set_association_correction((2, 10), (3, 10), 'protected')
    epic.replace_label(10, 42, 0)
    assert epic.tracking.correction_ledger[0]['source'] == (2, 42)
    assert epic.tracking.correction_ledger[0]['target'] == (3, 42)


def test_drift_samples_centroids_beyond_pixel_255(make_napari_viewer, tmp_path, monkeypatch):
    epic = _synthetic_epicure(make_napari_viewer, tmp_path)
    epic.img = np.zeros((2, 400, 10), dtype=np.uint8)
    labels = np.zeros(epic.img.shape, dtype=np.uint32)
    labels[:, 300:302, 3:5] = 10
    tracking = epic.tracking
    tracking.region_properties = ['label', 'centroid']
    tracking.drift_correction.setChecked(True)
    rows = np.broadcast_to(np.arange(400)[:, None] / 100, (400, 10))
    monkeypatch.setattr(tracking, 'optical_flow', lambda *args: (rows, np.zeros_like(rows)))
    table = tracking.labels_to_centroids_flow(0, 1, labels)
    assert table.loc[table['frame'] == 1, 'centroid-0'].iloc[0] == pytest.approx(297.5)


def test_deletion_marks_original_endpoint_missing(make_napari_viewer, tmp_path):
    epic = _synthetic_epicure(make_napari_viewer, tmp_path)
    epic.tracking.set_association_correction((0, 10), (1, 10), 'protected')
    epic.replace_label(10, 0, 1)
    entry = epic.tracking.correction_ledger[0]
    assert entry['target'] == (1, 10)
    assert entry['missing_endpoints'] == ((1, 10),)
    assert epic.tracking._association_constraints() == ((), ())


def test_repeated_boundary_failures_show_one_conflict(make_napari_viewer, tmp_path):
    epic = _synthetic_epicure(make_napari_viewer, tmp_path)
    tracking = epic.tracking
    from epicure.tracking_transaction import TrackingConflict
    error = TrackingBoundaryError((TrackingConflict('range-boundary-identity', (10, 20), 'Expand range'),))
    def fail(*args):
        raise error
    tracking.register_tracking_method('Laptrack-Centroids', fail)
    for _ in range(2):
        with pytest.raises(TrackingBoundaryError):
            tracking.do_tracking()
    assert len(tracking.tracking_conflicts) == 1


def test_empty_relabel_is_a_noop(make_napari_viewer, tmp_path, monkeypatch):
    epic = _synthetic_epicure(make_napari_viewer, tmp_path)
    before = epic.seg.copy()
    monkeypatch.setattr(epic, 'get_label_indexes', lambda *args: [])
    epic.replace_label(123456, 42, 0)
    np.testing.assert_array_equal(epic.seg, before)
