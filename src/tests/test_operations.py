import numpy as np
import os
import epicure.epicuring as epi
import epicure.Utils as ut
import napari

def test_get_free_label( make_napari_viewer ):
    ## test from a skeletonized movie
    test_mov = os.path.join(".", "test_data", "003_crop.tif")
    test_seg = os.path.join(".", "test_data", "003_crop_epyseg.tif")
    viewer = make_napari_viewer()
    epic = epi.EpiCure(viewer)
    epic.load_movie(test_mov)
    #epic.viewer = napari.Viewer(show=False)
    epic.go_epicure("epics", test_seg)
    assert len(epic.get_free_labels(5)) == 5
    assert len(epic.get_free_labels(15)) == 15
    epic = None

#def test_remove_layer():
#    """ Test remove layer utility """
#    test_mov = os.path.join(".", "test_data", "003_crop.tif")
#    test_seg = os.path.join(".", "test_data", "003_crop_epyseg.tif")
#    epic = epi.EpiCure()
#    epic.load_movie(test_mov)
#    epic.go_epicure("epics", test_seg)
#    assert "Events" in epic.viewer.layers 
#    ut.remove_layer(epic.viewer, "Events")
#    assert "Events" not in epic.viewer.layers 
#    epic.inspecting.first_event((0,10,20), 10, "suspect")
#    assert "Events" in epic.viewer.layers 
    
def utils_value(make_napari_viewer):
    """ Labels operations in Utils """
    test_mov = os.path.join(".", "test_data", "003_crop.tif")
    test_seg = os.path.join(".", "test_data", "003_crop_epyseg.tif")
    viewer = make_napari_viewer()
    epic = epi.EpiCure(viewer)
    epic.load_movie(test_mov)
    epic.go_epicure("epics", test_seg)
    cell = epic.seg[0,160,80]
    assert cell > 0
    ut.changeLabel( epic.seglayer, cell, 30)
    cell = epic.seg[0,160,80]
    assert cell == 30

    ## read value under click 
    event = napari.utils.events.Event("mouse_press") 
    event.position = [0,160,80]
    event.view_direction = None
    event.dims_displayed = [0,1, 1] 
    cell = ut.getCellValue( epic.seglayer, event )
    assert cell == 30

    

if __name__ == "__main__":
    test_get_free_label()
    utils_value()
    print("********* Test operations cure completed ***********")
