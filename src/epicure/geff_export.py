import os
from typing import Dict, List

import geff
import geff_spec
import networkx as nx
import numpy as np
import pandas as pd
from scipy.cluster.hierarchy import DisjointSet

import epicure.Utils as ut


def create_label_to_track_mapping(
    divisions: Dict[int, List[int]], unique_labels: List[int]
) -> Dict[int, int]:
    """
    Create a mapping from labels to track IDs using scipy's DisjointSet for efficient track grouping.

    Args:
        divisions: dict of {daughter_label: [mother_labels]} from epic.tracking.graph
        unique_labels: list of unique labels present in the tracking data

    Returns:
        dict: {label: track_id} - mapping from each label to its track ID
    """
    if not divisions:
        # No divisions - each unique label is its own track.
        return {label: label for label in unique_labels}

    ds = DisjointSet(unique_labels)

    # Union connected labels based on mother-daughter relationships.
    for daughter, mothers in divisions.items():
        if daughter not in unique_labels:  # weirdly, this can happen
            continue
        for mother in mothers:
            if mother in unique_labels:
                ds.merge(daughter, mother)

    # A connected component is a track. We use the root as track ID.
    # Create a mapping from label to track_id (root).
    label_to_track_id = {}
    for label in unique_labels:
        root = ds[label]
        label_to_track_id[label] = root

    return label_to_track_id


def build_nodes_df(
    track_data: np.ndarray, divisions: Dict[int, List[int]]
) -> pd.DataFrame:
    """
    Build a DataFrame representing the nodes for the GEFF graph.

    Args:
        track_data: numpy array with columns [label, frame, y, x]
        divisions: dict of {daughter_label: [mother_labels]} from epic.tracking.graph

    Returns:
        pd.DataFrame with columns [node_id, label, frame, y, x, track_id]
    """
    df = pd.DataFrame(track_data, columns=["label", "frame", "y", "x"])
    df["node_id"] = df.index

    # Generate and assign track IDs.
    labels = list(df["label"].unique())
    label_to_track_id = create_label_to_track_mapping(divisions, labels)
    df["track_id"] = df["label"].map(label_to_track_id)

    return df


def build_edges_df(divisions: Dict[int, List[int]], df_nodes: pd.DataFrame):
    """
    Build a DataFrame representing the edges for the GEFF graph.

    Args:
        divisions: dict of {daughter_label: [mother_labels]} from epic.tracking.graph
        df_nodes: DataFrame with node information

    Returns:
        pd.DataFrame with columns [in_id, out_id]
    """
    if divisions is not None:
        for daughter, mothers in divisions.items():
            if len(mothers) > 1:
                ut.show_error(
                    f"Merge event detected. Label {daughter} "
                    f"has the following mother labels: {mothers}."
                )
    # TODO: does GEFF support merge events?

    # Division edges: for each daughter-mother pair, create an edge.
    edges_data = [
        {"daughter": daughter, "mother": mother}
        for daughter, mothers in divisions.items()
        for mother in mothers
    ]
    df_edges = pd.DataFrame(edges_data)
    # Labels stay the same until there is a division. But node IDs are unique.
    # It means that in df_nodes, labels appears multiple times. Because of this
    # we cannot easily map between df_nodes and df_edges. So we create intermediary
    # columns to ease the mapping.
    df_nodes["first_frame"] = df_nodes.groupby("label")["frame"].transform("min")
    df_nodes["last_frame"] = df_nodes.groupby("label")["frame"].transform("max")
    # A daughter is at the first frame of its label, a mother at the last frame of its label.
    df_nodes["daughter"] = df_nodes["first_frame"] == df_nodes["frame"]
    df_nodes["mother"] = df_nodes["last_frame"] == df_nodes["frame"]
    df_nodes.drop(columns=["first_frame", "last_frame"], inplace=True)
    # Now we can map between df_nodes and df_edges.
    # The in_id is the node ID of the matching label that is a mother,
    # and the out_id is the node ID of the matching label that is a daughter.
    df_edges["in_id"] = df_edges["mother"].map(
        df_nodes[df_nodes["mother"]].set_index("label")["node_id"]
    )
    df_edges["out_id"] = df_edges["daughter"].map(
        df_nodes[df_nodes["daughter"]].set_index("label")["node_id"]
    )
    df_nodes.drop(columns=["daughter", "mother"], inplace=True)

    # Non-division edges: for each label, connect consecutive nodes within that label.
    non_division_edges = []
    for label in df_nodes["label"].unique():
        label_spots = df_nodes[df_nodes["label"] == label].sort_values("frame")
        if len(label_spots) > 1:
            for i in range(len(label_spots) - 1):
                current_spot = label_spots.iloc[i]
                next_spot = label_spots.iloc[i + 1]
                non_division_edges.append(
                    {"in_id": current_spot["node_id"], "out_id": next_spot["node_id"]}
                )

    # Combine division and non-division edges.
    df_non_division_edges = pd.DataFrame(non_division_edges)
    if not df_edges.empty and not df_non_division_edges.empty:
        # Make sure both dataframes have the same columns.
        df_edges = df_edges[["in_id", "out_id"]]
        df_edges = pd.concat([df_edges, df_non_division_edges], ignore_index=True)
    elif not df_non_division_edges.empty:
        df_edges = df_non_division_edges

    # Final cleanup and type conversion.
    if not df_edges.empty:
        # We can have NaN if a label has no mother (appears at first frame)
        # or no daughter (disappears at last frame).
        df_edges.dropna(inplace=True)
        # Convert to int in case of NaN.
        df_edges["in_id"] = df_edges["in_id"].astype(int)
        df_edges["out_id"] = df_edges["out_id"].astype(int)

    return df_edges


def build_nx_digraph(epic) -> nx.DiGraph:
    """
    Build a NetworkX directed graph from EpiCure data.

    Args:
        epic: EpiCure instance with tracking data and graph

    Returns:
        nx.DiGraph: directed graph representing the cell lineages
    """

    df_nodes = build_nodes_df(epic.tracking.track_data, epic.tracking.graph)
    df_edges = build_edges_df(epic.tracking.graph, df_nodes)

    graph = nx.DiGraph()
    for _, row in df_nodes.iterrows():
        graph.add_node(row["node_id"], **row.to_dict())
    for _, edge in df_edges.iterrows():
        graph.add_edge(edge["in_id"], edge["out_id"])

    node_attrs = {row["node_id"]: row.to_dict() for _, row in df_nodes.iterrows()}
    nx.set_node_attributes(graph, node_attrs)

    return graph


def build_props_metadata() -> Dict[str, geff_spec.PropMetadata]:
    """
    Build GEFF properties metadata.

    Returns:
        dict: mapping from property names to their metadata
    """
    md_x = geff_spec.PropMetadata(
        identifier="x",
        dtype="int",
        varlength=False,
        unit="pixel",
        name="x",
        description="X coordinate of center of the cell",
    )
    md_y = geff_spec.PropMetadata(
        identifier="y",
        dtype="int",
        varlength=False,
        unit="pixel",
        name="y",
        description="Y coordinate of the center of the cell",
    )
    md_t = geff_spec.PropMetadata(
        identifier="frame",
        dtype="int32",
        varlength=False,
        unit="frame",
        name="frame",
        description="Time",
    )
    md_label = geff_spec.PropMetadata(
        identifier="label",
        dtype="int64",
        varlength=False,
        name="label",
        description="Label of the cell",
    )
    md_nid = geff_spec.PropMetadata(
        identifier="node_id",
        dtype="int64",
        varlength=False,
        name="node_id",
        description="Unique identifier of the node",
    )

    return {"x": md_x, "y": md_y, "frame": md_t, "label": md_label, "node_id": md_nid}


def build_geff_metadata(epic):
    """
    Build GEFF metadata.

    Args:
        epic: EpiCure instance with metadata information
    """
    axes = [
        geff_spec.Axis(
            name="x",
            type="space",
            unit="pixel",
            scale=epic.epi_metadata.get("ScaleXY", 1),
            scaled_unit=epic.epi_metadata.get("UnitXY"),
        ),
        geff_spec.Axis(
            name="y",
            type="space",
            unit="pixel",
            scale=epic.epi_metadata.get("ScaleXY", 1),
            scaled_unit=epic.epi_metadata.get("UnitXY"),
        ),
        geff_spec.Axis(
            name="frame",
            type="time",
            unit="frame",
            scale=epic.epi_metadata.get("ScaleT", 1),
            scaled_unit=epic.epi_metadata.get("UnitT"),
        ),
    ]
    display_hints = geff_spec.DisplayHint(
        display_horizontal="x",
        display_vertical="y",
        display_time="frame",
    )

    return geff.GeffMetadata(
        directed=True,
        axes=axes,
        display_hints=display_hints,
        node_props_metadata=build_props_metadata(),
        edge_props_metadata={},
        track_node_props={"lineage": "track_id", "tracklet": "label"},
        related_objects=[
            geff_spec.RelatedObject(
                type="labels",
                path=os.path.join("..", epic.imgname + "_labels.tif"),
                label_prop="label",
            ),
        ],
    )


def save_geff(epic, outname):
    """
    Save EpiCure tracking data as a GEFF file.

    Args:
        epic: EpiCure instance with tracking data and graph
        outname: path to save the GEFF file
    """
    geff_graph = build_nx_digraph(epic)
    geff_md = build_geff_metadata(epic)

    geff.write(
        geff_graph,
        outname,
        metadata=geff_md,
        zarr_format=2,  # could be 3 but 2 by default in GEFF
        structure_validation=True,
        overwrite=True,
    )
