import numpy as np
import os
import epicure.epicuring as epi
import epicure.Utils as ut
#from unittest.mock import Mock
#from vispy import keys
import napari


def test_output_selected( make_napari_viewer ):
    """ Selection of cells to export segmentation as ROI/labels """
    test_img = os.path.join(".", "test_data", "area3_Composite.tif")
    test_seg = os.path.join(".", "test_data", "area3_Composite_epyseg.tif")
    viewer = make_napari_viewer()
    epic = epi.EpiCure(viewer)
    resaxis, resval = epic.load_movie(test_img)
    epic.set_chanel(1, 1)
    assert epic.viewer is not None
    epic.go_epicure("test_epics", test_seg)

    ## test changing the current selection of export (one cell or all cells)
    output = epic.outputing
    assert output is not None
    output.output_mode.setCurrentText("All cells")
    sel = output.get_selection_name()
    assert sel == ""
    output.output_mode.setCurrentText("Only selected cell")
    sel = output.get_selection_name()
    assert sel == "_cell_1"
    ## export a cell segmentation as Fiji ROI
    output.save_choice.setCurrentText("ROI")
    roi_file = os.path.join(".", "test_data", "test_epics", "area3_Composite_rois_cell_1.zip")
    if os.path.exists(roi_file):
        os.remove(roi_file)
    output.save_segmentation()
    assert os.path.exists(roi_file)
    
def test_measure_vertices( make_napari_viewer ):
    """ Find the vertices (TCJ) and measure their intensity and nb of neighbors """

    test_img = os.path.join(".", "test_data", "area3_Composite.tif")
    test_seg = os.path.join(".", "test_data", "area3_Composite_epyseg.tif")
    viewer = make_napari_viewer()
    epic = epi.EpiCure(viewer)
    resaxis, resval = epic.load_movie(test_img)
    epic.set_chanel(1, 1)
    assert epic.viewer is not None
    epic.go_epicure("test_epics", test_seg)

    output = epic.outputing
    assert output is not None

    # Default vertex sizes
    output.vertice_radius.setText("1.25")
    output.measure_vertices()
    assert "Vertices" in viewer.layers
    vertices = viewer.layers["Vertices"].data
    frame = 1
    props = ut.binary_properties(vertices[frame])
    nvertex = len(props)
    assert nvertex > 150
    assert nvertex < 250
    nneigh = np.array((output.table["nb_neighbors"]))
    ## Nb of neighbor shuold in majority 3, and between 2 and 6-ish max
    assert np.min(nneigh>=2)
    assert np.max(nneigh<=6)
    assert np.floor(np.median(nneigh)) == 3

    ## Take bigger vertex: merge neighboring ones
    output.vertice_radius.setText("4")
    output.measure_vertices()
    vertices = viewer.layers["Vertices"].data
    props = ut.binary_properties(vertices[frame])
    assert len(props)>100
    assert len(props)<nvertex

def test_measure_intensities(make_napari_viewer ):
    """ Test measure of cell features, in particular intensity measurement """

    test_img = os.path.join(".", "test_data", "area3_Composite.tif")
    test_seg = os.path.join(".", "test_data", "area3_Composite_epyseg.tif")
    viewer = make_napari_viewer()
    epic = epi.EpiCure(viewer)
    resaxis, resval = epic.load_movie(test_img)
    epic.set_chanel(1, 1)
    # test when there are two channels to measure
    epic.add_other_chanels(0, 1)  ## keep also the first channel to measure intensity in it
    assert epic.viewer is not None
    epic.go_epicure("test_epics", test_seg)

    output = epic.outputing
    assert output is not None
    output.output_mode.setCurrentText("All cells")

    ## Make sure that intensity_junction_cytoplasm measure is selected
    output.cell_features.select_all("intensity")

    ## select the two channels to measure
    output.cell_features.chan_list.item(0).setSelected(True)
    output.cell_features.chan_list.item(1).setSelected(True)

    ## go measure the cell features
    output.measure_features()

    ## check that the intensity measurements were done in both channels
    assert "intensity_mean_MovieChannel_1" in output.table.keys()
    assert "intensity_mean" in output.table.keys()
    assert "intensity_junction_MovieChannel_1" in output.table.keys()

    ## now remove the other channels to check it runs on only one channel
    epic.others = None
    output.cell_features.chan_list = None
    ## go measure the cell features
    output.measure_features()
    ## check that it measured only the movie channel
    assert "intensity_mean" in output.table.keys()
    assert "intensity_mean_MovieChannel_1" not in output.table.keys()

def test_measure_events(make_napari_viewer ):
    """ Measure/export of events """
    test_img = os.path.join(".", "test_data", "013_crop.tif")
    viewer = make_napari_viewer()
    epic = epi.EpiCure(viewer)
    epic.load_movie(test_img)
    epic.go_epicure("epics")
    output = epic.outputing

    ## Export of number of events by frame
    output.output_mode.setCurrentText("All cells") ## ensure to measure all cells
    tab = output.count_events()
    ## should have only one division at frame 3
    assert int(tab.loc[tab["frame"]==2, 'division'].iloc[0]) == 0
    assert int(tab.loc[tab["frame"]==3, 'division'].iloc[0]) == 1
    assert np.sum(tab['extrusion']) == 0

if __name__ == "__main__":
    #test_output_selected()
    #test_measure_events()
    test_measure_vertices()
    print("********* Test outputs cure completed ***********")
