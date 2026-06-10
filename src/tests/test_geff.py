"""
Test IO options for GEFF, and some critical GEFF related functions.
Corresponding code in src/epicure/geff_import.py and src/epicure/geff_export.py
"""

import networkx as nx

from epicure.geff_import import _generate_label


def test_generate_label():
    """Test the _generate_label function which generates labels for each linear path in the graph."""

    # There are 2 components in this graph, and splits and merges.
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


def test_export_geff():
    """Export tracks as a GEFF file"""
    # TODO
    pass


def test_import_geff():
    """Test import a GEFF file into EpiCure structure"""
    # TODO
    pass


if __name__ == "__main__":
    test_generate_label()
    print("********* Test import/export to GEFF completed ***********")
