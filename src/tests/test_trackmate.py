"""
Test the "export to trackmate XML" options in Output. 
Corresponding code in src/epicure/trackmate_export.py
"""

import epicure.epicuring as epicure
import os

def test_export_trackmate(make_napari_viewer):
    """ Export tracks as a TrackMate XML file """
    raw_path = os.path.join( ".", "test_data", "013_crop.tif" )
    xml_path = os.path.join(".", "test_data", "epics", "013_crop.xml")
    if os.path.exists(xml_path):
        os.remove(xml_path)

    viewer = make_napari_viewer()
    epic = epicure.EpiCure(viewer)
    epic.verbose = 3  # 0: minimal to 3: debug informations
    epic.load_movie(raw_path)
    epic.go_epicure(outdir="epics")

    epic.outputing.output_mode.setCurrentText("All cells")
    epic.outputing.save_tm_xml()

    ## check that metadata were well read
    assert epic.epi_metadata["ScaleXY"]==0.2
    assert int(epic.epi_metadata["ScaleT"])==300 
    ## check that TrackMate file was generated
    assert os.path.exists(xml_path)

def test_tm_loader_trackmate():
    """ Test functions to import a Trackmate .xml tracks """
    import epicure.tm_loader as tm
    import numpy as np
    from pathlib import Path
    tm_file = "test_data/FakeTracks_with_fusions.xml"
    # tm_file = "/media/lxenard/data/Code/pycellin/pycellin/sample_data/Ecoli_growth_on_agar_pad.xml"
    # tm_file = "/home/lxenard/snap/trackMateMoiCa/epics/013_crop.xml"
    np.set_printoptions(suppress=True, floatmode="maxprec_equal")

    img_data_tag = tm._get_ImageData_tag(Path(tm_file))
    metadata = tm._get_metadata(img_data_tag)
    seg_shape = (int(metadata["nframes"]), int(metadata["height"]), int(metadata["width"]))
    segmentation = np.zeros(seg_shape, dtype=np.uint16)
    positions, tracks = tm._parse_Model_tag(Path(tm_file), metadata, segmentation)
    label_mapping = tm._build_label_mapping(positions, tracks)
    positions = tm.relabel_positions(label_mapping, positions)
    tracks = tm.relabel_tracks(label_mapping, tracks)
    segmentation = tm.relabel_segmentation(label_mapping, segmentation)

    # import matplotlib.pyplot as plt

    # n_frames = segmentation.shape[0]
    # n_cols = 10
    # n_rows = (n_frames + n_cols - 1) // n_cols
    # fig, axes = plt.subplots(n_rows, n_cols, figsize=(40, 2 * n_rows))
    # for i in range(n_frames):
    #     ax = axes[i // n_cols, i % n_cols]
    #     ax.imshow(segmentation[i], cmap="gray")
    #     ax.set_title(f"Frame {i}")
    #     ax.axis("off")
    # plt.tight_layout()
    # plt.show()

    ## Test relabeling
    # Expected mapping from TrackMate labels to EpiCure labels for the test file.
    expected_tracklets = {
        "a": [2004, 2005, 2007, 2009, 2010, 2011, 2013, 2014, 2015],
        "b": [2006, 2008],
        "c": [2012],
        "d": [2017, 2020, 2021, 2024, 2026, 2028, 2029, 2031, 2034, 2038, 2042, 2045, 2047, 2051, 2053, 2056, 2059, 2064],
        "e": [2016, 2019, 2022, 2023, 2025, 2027, 2030],
        "f": [2018],
        "g": [2033, 2036, 2039, 2043, 2044, 2049, 2052, 2054, 2058, 2060, 2062, 2065, 2068, 2070],
        "h": [2032, 2035, 2040, 2041, 2046, 2048, 2050, 2055, 2057, 2061, 2063],
        "i": [2037],
        "j": [2066, 2067, 2071, 2072, 2074, 2076, 2078, 2080, 2083, 2084, 2085, 2088, 2090, 2092, 2095],
        "k": [2069],
        "l": [2073],
        "m": [2075, 2077, 2079, 2081],
        "n": [2082],
        "o": [2086],
        "p": [2087, 2089],
        "q": [2091, 2093, 2096, 2097, 2099, 2100, 2102, 2103, 2105, 2108],
        "r": [2094],
        "s": [2098],
        "t": [2101],
        "u": [2106, 2109],
        "v": [2107, 2110],
    }

    # Test that we have the same number of tracklets as expected.
    nb_tracklets_exp = len(expected_tracklets)
    nb_tracklets_obt = len(set(positions[:, 0]))
    assert nb_tracklets_exp == nb_tracklets_obt, f"Expected {nb_tracklets_exp} tracklets, but got {nb_tracklets_obt}."

    # Test that detections get grouped into tracklets as expected
    # Build a mapping from new labels to sets of original TrackMate IDs
    obtained_tracklets = {}
    for old_label, new_label in label_mapping.items():
        if new_label not in obtained_tracklets:
            obtained_tracklets[new_label] = []
        obtained_tracklets[new_label].append(old_label)
    # Convert to sets for easier comparison
    obtained_tracklet_sets = [set(ids) for ids in obtained_tracklets.values()]
    expected_tracklet_sets = [set(ids) for ids in expected_tracklets.values()]

    # Check that each expected tracklet matches exactly one obtained tracklet
    for exp_name, exp_ids in expected_tracklets.items():
        exp_set = set(exp_ids)
        matching_obtained = [obt_set for obt_set in obtained_tracklet_sets if obt_set == exp_set]
        assert len(matching_obtained) == 1, f"Expected tracklet '{exp_name}' with IDs {exp_ids} was not found exactly once. Found {len(matching_obtained)} matches."

    # Check that no two expected tracklets are merged into one
    for obt_label, obt_ids in obtained_tracklets.items():
        obt_set = set(obt_ids)
        # Count how many expected tracklets have all their IDs in this obtained tracklet
        contain_expected = [exp_name for exp_name, exp_ids in expected_tracklets.items() if set(exp_ids).issubset(obt_set)]
        assert len(contain_expected) <= 1, f"Obtained tracklet with label {obt_label} contains IDs from multiple expected tracklets: {contain_expected}. IDs: {obt_ids}"

def test_import_trackmate(make_napari_viewer):
    """ Test import a Trackmate .xml tracks into EpiCure structure """
    raw_path = os.path.join( ".", "test_data", "013_crop.tif" )
    xml_path = os.path.join(".", "test_data", "epics", "013_crop.xml")

    viewer = make_napari_viewer()
    epic = epicure.EpiCure(viewer)
    epic.verbose = 3  # 0: minimal to 3: debug informations
    epic.load_movie(raw_path)
    epic.go_epicure("epics", xml_path)
    ## should be tracked
    assert epic.tracked>0
    ## should have loaded divisions from the trackmate graph
    assert epic.nb_divisions()>0


if __name__ == "__main__":
    test_import_trackmate()
    print("********* Test import/export to TrackMate XML completed ***********")
