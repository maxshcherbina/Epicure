"""
Test IO options for GEFF, and some critical GEFF related functions.
Corresponding code in src/epicure/geff_import.py and src/epicure/geff_export.py
"""

import os
import shutil

import geff
import napari
import networkx as nx

import epicure.epicuring as epicure
from epicure.geff_import import _generate_label


def test_generate_label():
    """Test the _generate_label function which generates labels for each linear path in the graph."""

    # There are 2 components in this graph, with splits and merges.
    digraph = nx.DiGraph()
    digraph.add_nodes_from(
        [
            (1, {"frame": 0, "manual_label": 0}),
            (2, {"frame": 1, "manual_label": 0}),
            (3, {"frame": 2, "manual_label": 0}),
            (4, {"frame": 3, "manual_label": 1}),
            (5, {"frame": 3, "manual_label": 2}),
            (6, {"frame": 3, "manual_label": 3}),
            (7, {"frame": 4, "manual_label": 1}),
            (8, {"frame": 4, "manual_label": 2}),
            (9, {"frame": 4, "manual_label": 3}),
            (10, {"frame": 5, "manual_label": 4}),
            (11, {"frame": 5, "manual_label": 5}),
            (12, {"frame": 5, "manual_label": 6}),
            (13, {"frame": 5, "manual_label": 7}),
            (14, {"frame": 6, "manual_label": 4}),
            (15, {"frame": 6, "manual_label": 5}),
            (16, {"frame": 0, "manual_label": 8}),
            (17, {"frame": 1, "manual_label": 9}),
            (18, {"frame": 1, "manual_label": 10}),
            (19, {"frame": 2, "manual_label": 11}),
            (20, {"frame": 2, "manual_label": 12}),
            (21, {"frame": 3, "manual_label": 13}),
            (22, {"frame": 4, "manual_label": 14}),
            (23, {"frame": 4, "manual_label": 15}),
        ]
    )
    digraph.add_edges_from(
        [
            (1, 2),
            (2, 3),
            (3, 4),
            (4, 7),
            (7, 10),
            (10, 14),
            (7, 11),
            (11, 15),
            (3, 5),
            (5, 8),
            (8, 12),
            (3, 6),
            (6, 9),
            (9, 12),
            (9, 13),
            (16, 17),
            (17, 19),
            (19, 21),
            (17, 20),
            (20, 21),
            (21, 22),
            (21, 23),
            (16, 18),
        ]
    )

    _generate_label(digraph)
    for node in digraph.nodes():
        msg = f"Node {node} expected label {digraph.nodes[node]['manual_label']} but got {digraph.nodes[node]['label']}"
        assert digraph.nodes[node]["label"] == digraph.nodes[node]["manual_label"], msg


def test_export_geff(make_napari_viewer):
    """Export tracks as a GEFF file"""

    raw_path = os.path.join(".", "test_data", "013_crop.tif")
    geff_path = os.path.join(".", "test_data", "epics", "013_crop.geff")
    if os.path.exists(geff_path):
        shutil.rmtree(geff_path)

    # viewer = napari.Viewer(show=False)
    viewer = make_napari_viewer()
    epic = epicure.EpiCure(viewer)
    epic.verbose = 3  # 0: minimal to 3: debug informations
    epic.load_movie(raw_path)
    epic.go_epicure(outdir="epics")
    epic.outputing.output_mode.setCurrentText("All cells")
    epic.outputing.save_geff()

    geff_graph, geff_md = geff.read(geff_path, structure_validation=True)

    ## Metadata check
    assert "pixel" == geff_md.axes[0].unit
    assert epic.epi_metadata["ScaleXY"] == geff_md.axes[0].scale
    assert epic.epi_metadata.get("UnitXY") == geff_md.axes[0].scaled_unit
    assert "frame" == geff_md.axes[2].unit
    assert epic.epi_metadata["ScaleT"] == geff_md.axes[2].scale
    assert epic.epi_metadata.get("UnitT") == geff_md.axes[2].scaled_unit

    ## Data check
    # Check that the GEFF file was generated and saved.
    assert os.path.exists(geff_path)
    # Check that there is the same number of divisions.
    n_divs = epic.nb_divisions()
    n_divs_geff = len([n for n in geff_graph.nodes() if geff_graph.out_degree(n) > 1])
    assert n_divs == n_divs_geff, (
        f"Expected {n_divs} divisions but found {n_divs_geff} in the GEFF."
    )
    # Check that the labels are identical.
    labels = set(int(label) for label in epic.tracking.track_data[:, 0])
    labels_geff = set(geff_graph.nodes[n]["label"] for n in geff_graph.nodes())
    diff_left = list(labels.difference(labels_geff))
    diff_right = list(labels_geff.difference(labels))
    msg = f"Missing labels in GEFF: {diff_left}, extra labels in GEFF: {diff_right}."
    assert labels == labels_geff, msg
    # Check that there is the same number of detections.
    n_detections = epic.tracking.track_data.shape[0]
    n_detections_geff = len(geff_graph.nodes())
    assert n_detections == n_detections_geff, (
        f"Expected {n_detections} detections but found {n_detections_geff} in the GEFF."
    )


def test_import_geff(make_napari_viewer):
    """Test import a GEFF file into EpiCure structure"""
    raw_path = os.path.join(".", "test_data", "013_crop.tif")
    geff_path = os.path.join(".", "test_data", "epics", "013_crop.geff")

    # viewer = napari.Viewer(show=False)
    viewer = make_napari_viewer()
    epic = epicure.EpiCure(viewer)
    epic.verbose = 3  # 0: minimal to 3: debug informations
    epic.load_movie(raw_path)
    epic.go_epicure("epics", geff_path)

    geff_graph, geff_md = geff.read(geff_path, structure_validation=True)

    ## Metadata check
    x_unit = geff_md.axes[0].scaled_unit
    x_unit_epi = epic.epi_metadata.get("UnitXY")
    x_scale = geff_md.axes[0].scale
    x_scale_epi = epic.epi_metadata["ScaleXY"]
    assert x_unit == x_unit_epi, f"Expected unit {x_unit} for x axis but got {x_unit_epi}"
    assert x_scale == x_scale_epi, (
        f"Expected scale {x_scale} for x axis but got {x_scale_epi}"
    )
    t_unit = geff_md.axes[2].scaled_unit
    t_unit_epi = epic.epi_metadata.get("UnitT")
    t_scale = geff_md.axes[2].scale
    t_scale_epi = epic.epi_metadata["ScaleT"]
    assert t_unit == t_unit_epi, (
        f"Expected unit {t_unit} for time axis but got {t_unit_epi}"
    )
    assert t_scale == t_scale_epi, (
        f"Expected scale {t_scale} for time axis but got {t_scale_epi}"
    )

    ## Data check
    assert epic.tracked > 0
    # Check that there is the same number of divisions.
    n_divs = len([n for n in geff_graph.nodes() if geff_graph.out_degree(n) > 1])
    n_divs_epi = epic.nb_divisions()
    assert n_divs == n_divs_epi, (
        f"Expected {n_divs} divisions but found {n_divs_epi} in the GEFF."
    )
    # Check that the labels are identical.
    labels_epi = set(int(label) for label in epic.tracking.track_data[:, 0])
    labels = set(geff_graph.nodes[n]["label"] for n in geff_graph.nodes())
    diff_left = list(labels.difference(labels_epi))
    diff_right = list(labels_epi.difference(labels))
    msg = f"Missing labels in GEFF: {diff_left}, extra labels in GEFF: {diff_right}."
    assert labels == labels_epi, msg
    # Check that there is the same number of detections.
    n_detections_epi = epic.tracking.track_data.shape[0]
    n_detections = len(geff_graph.nodes())
    assert n_detections == n_detections_epi, (
        f"Expected {n_detections} detections but found {n_detections_epi} in the GEFF."
    )


if __name__ == "__main__":
    test_generate_label()
    test_export_geff()
    test_import_geff()
    print("********* Test import/export to GEFF completed ***********")
