import geff
import networkx as nx
import numpy as np
from zarr.storage import StoreLike

import epicure.Utils as ut


def _check_preconditions(graph: nx.Graph, metadata: geff.GeffMetadata | None) -> None:
    """
    Check that the graph meets the preconditions for import: directed graph and no merging cells.

    Args:
        graph (nx.Graph): The GEFF graph to check.
        metadata (geff.GeffMetadata | None): The GEFF metadata.
    """

    if metadata is None:
        if not isinstance(graph, nx.DiGraph):
            ut.show_error(f"The GEFF graph must be directed. Found type: {type(graph)}.")
    else:
        if not metadata.directed:
            ut.show_error(
                "The GEFF graph must be directed. Metadata indicates an undirected graph."
            )

    assert isinstance(graph, nx.DiGraph), (
        f"The GEFF graph must be directed. Found type: {type(graph)}."
    )
    fusions = [n for n in graph.nodes() if graph.in_degree(n) > 1]
    if len(fusions) > 0:
        ut.show_warning(
            f"Merging cells detected (nodes: {fusions}). EpiCure behavior may be affected."
        )


def _identify_labels_path(metadata: geff.GeffMetadata) -> tuple[str | None, str | None]:
    """
    Identify the label key and path to the labels image from GEFF metadata.

    Args:
        metadata (geff.GeffMetadata): The GEFF metadata.

    Returns:
        tuple[str | None, str | None]: A tuple containing the label key 
            and the path to the labels image if present, None otherwise.
    """
    if metadata.related_objects is None:
        return None, None

    related_objects = [obj for obj in metadata.related_objects if obj.type == "labels"]
    if len(related_objects) == 0:
        return None, None
    elif len(related_objects) > 1:
        ut.show_warning(
            "Multiple related objects of type 'labels' found in GEFF metadata. "
            "Cannot determine which one to use. No labels image will be imported."
        )
        return None, None
    else:
        obj = related_objects[0]
        ut.show_debug(
            f"Labels image path identified from GEFF metadata: '{obj.path}'.",
        )
        if obj.label_prop is not None:
            ut.show_debug(
                f"Label property for labels image identified from GEFF metadata: '{obj.label_prop}'.",
            )
            return obj.label_prop, obj.path
        else:
            ut.show_warning(
                "Label property for labels image not specified in GEFF metadata. "
                "Falling back to 'label'.",
            )
            return "label", obj.path


def _identify_prop(
    geff_md: geff.GeffMetadata | None,
    geff_graph: nx.DiGraph,
    prop_name: str,
) -> str | None:
    """
    Identify the actual name of a property if it exists, given a property name to look for.

    Args:
        geff_md (geff.GeffMetadata | None): The GEFF metadata.
        geff_graph (nx.DiGraph): The GEFF graph.
        prop_name (str): The name of the property to check.

    Returns:
        str | None: The actual name of the property if present in all graph nodes, None otherwise.
    """
    if geff_md is not None and geff_md.node_props_metadata:
        for prop_id in geff_md.node_props_metadata.keys():
            if prop_id.lower() == prop_name.lower():
                if all(prop_id in geff_graph.nodes[node] for node in geff_graph.nodes):
                    ut.show_debug(
                        f"Property '{prop_id}' found in GEFF metadata and present in all graph nodes.",
                    )
                    return prop_id
                else:
                    ut.show_debug(
                        f"Property '{prop_id}' found in GEFF metadata but not present in all graph nodes.",
                    )

    return None


def _identify_time_axis(
    geff_md: geff.GeffMetadata | None,
    geff_graph: nx.DiGraph,
) -> str:
    """
    Identify the time axis from GEFF metadata.

    The function will try to infer it first from the display hints, then from the axes.
    In case the function fallbacks to the GEFF axes, it will take time axes in order
    and check if the corresponding key exists in the graph. The first one to be found
    will be returned as the time axis.

    Args:
        geff_md (geff.GeffMetadata | None): The GEFF metadata.
        geff_graph (nx.DiGraph): The GEFF graph.

    Returns:
        str: The identified time axis.
    """
    # Check for time in display hints.
    time_key = None
    hints = geff_md.display_hints if geff_md is not None else None
    if hints is not None:
        time_key = getattr(hints, "display_time", None)
        if time_key is not None:
            if all(time_key in geff_graph.nodes[node] for node in geff_graph.nodes):
                ut.show_debug(
                    f"Valid time axis inferred from GEFF display hints: '{time_key}'.",
                )
            else:
                ut.show_debug(
                    f"Time axis '{time_key}' inferred from GEFF display hints is not present "
                    "in all the graph nodes. Falling back to GEFF axes to identify it.",
                )
                time_key = None

    # Fallback to GEFF axes.
    axes = geff_md.axes if geff_md is not None else None
    if time_key is None and axes is not None:
        time_axes = [axis for axis in axes if axis.type == "time"]
        for axis in time_axes:
            if axis.name is not None and all(
                axis.name in geff_graph.nodes[node] for node in geff_graph.nodes
            ):
                time_key = axis.name
                ut.show_debug(
                    f"Valid time axis inferred from GEFF axes: '{time_key}'.",
                )
                break

    if time_key is None:
        ut.show_error(
            "No valid time axis found. Please ensure that the GEFF file contains "
            "a time axis or a time display hint."
        )

    return time_key


def _identify_space_axes(
    geff_md: geff.GeffMetadata | None,
    geff_graph: nx.DiGraph,
) -> tuple[str, str]:
    """
    Identify the space axes (x, y) from GEFF metadata.

    The function will try to infer them from the GEFF metadata,
    first from the display hints, then from the axes.

    Args:
        geff_md (geff.GeffMetadata | None): The GEFF metadata.
        geff_graph (nx.DiGraph): The GEFF graph.

    Returns:
        tuple[str, str]: The identified space axes.
    """
    space_keys = [None, None]

    # Check for space in display hints.
    hints = geff_md.display_hints if geff_md is not None else None
    hint_fields = ["display_horizontal", "display_vertical"]
    for i, hint_field in enumerate(hint_fields):
        if hints is not None:
            space_key = getattr(hints, hint_field, None)
            if space_key is not None:
                if all(space_key in geff_graph.nodes[node] for node in geff_graph.nodes):
                    ut.show_debug(
                        f"Valid space axis inferred from GEFF display hints: '{space_key}'.",
                    )
                else:
                    ut.show_debug(
                        f"Space axis '{space_key}' inferred from GEFF display hints is not present "
                        "in all the graph nodes. Falling back to GEFF axes to identify it.",
                    )
                    space_key = None
            space_keys[i] = space_key

    # Fallback to GEFF axes: space axes are consumed in order.
    axes = geff_md.axes if geff_md is not None else None
    if axes is not None:
        space_axes = iter(axis for axis in axes if axis.type == "space")
        for i, key in enumerate(space_keys):
            if key is None:
                for axis in space_axes:
                    if axis.name is not None and all(
                        axis.name in geff_graph.nodes[node] for node in geff_graph.nodes
                    ):
                        space_keys[i] = axis.name
                        ut.show_debug(
                            f"Valid space axis inferred from GEFF axes: '{space_keys[i]}'.",
                        )
                        break

    if space_keys[0] is None or space_keys[1] is None:
        ut.show_error(
            "No valid space axes found. Please ensure that the GEFF file contains "
            "space axes or space display hints."
        )

    return space_keys[0], space_keys[1]


def _generate_label(geff_graph: nx.DiGraph) -> None:
    """
    Add a 'label' node attribute to each node in the graph.
    Each linear path (unbranched segment) receives a unique label starting from 0.

    Args:
        geff_graph (nx.DiGraph): The graph to label. Modified in-place.

    Modifies:
        geff_graph (nx.DiGraph): Adds a 'label' attribute to each node.
    """
    labeled_nodes = set()
    label_counter = 0

    for start_node in geff_graph.nodes():
        if start_node in labeled_nodes:
            continue

        # Start a new linear path.
        current = start_node
        path_nodes = []

        # Follow the chain as long as we have a single successor
        # with a single predecessor (linear continuation).
        while current is not None and current not in labeled_nodes:
            path_nodes.append(current)
            labeled_nodes.add(current)

            successors = list(geff_graph.successors(current))

            if len(successors) == 1:
                next_node = successors[0]
                predecessors = list(geff_graph.predecessors(next_node))
                # Continue only if next node has exactly one predecessor.
                if len(predecessors) == 1:
                    current = next_node
                else:
                    current = None  # branching point ahead
            else:
                current = None  # end of linear path

        # Assign label to all nodes in this path.
        for node in path_nodes:
            geff_graph.nodes[node]["label"] = label_counter

        label_counter += 1


def _build_positions_array(
    geff_graph: nx.DiGraph,
    label_key: str,
    time_key: str,
    x_key: str,
    y_key: str,
) -> np.ndarray:
    """
    Build the positions array from the GEFF graph.

    Args:
        geff_graph (nx.DiGraph): The GEFF graph containing the nodes with their attributes.
        label_key (str): The key for the label attribute in the graph nodes.
        time_key (str): The key for the time/frame attribute in the graph nodes.
        x_key (str): The key for the x coordinate attribute in the graph nodes.
        y_key (str): The key for the y coordinate attribute in the graph nodes.

    Returns:
        np.ndarray: The filled positions array with columns [label, time, y, x].
    """
    positions = np.empty((len(geff_graph), 4), dtype=np.float32)
    for i, node in enumerate(geff_graph.nodes()):
        node_data = geff_graph.nodes[node]
        positions[i, 0] = node_data[label_key]
        positions[i, 1] = node_data[time_key]
        positions[i, 2] = node_data[y_key]
        positions[i, 3] = node_data[x_key]
    # TODO @Gaëlle: do we need to sort the positions by time? by label?
    return positions


def _build_tracks_dict(geff_graph: nx.DiGraph, label_key: str) -> dict[int, list[int]]:
    """
    Build the tracks dictionary from the GEFF graph ({daughter_label: [mother_labels]}).

    Args:
        geff_graph (nx.DiGraph): The GEFF graph containing the nodes and edges.
        label_key (str): The key for the label attribute in the graph nodes.

    Returns:
        dict[int, list[int]]: A dictionary mapping each daughter label to a list of its mother labels.
    """
    tracks: dict[int, list[int]] = {}
    divisions = [n for n in geff_graph.nodes() if geff_graph.out_degree(n) > 1]
    for div in divisions:
        for daughter in geff_graph.successors(div):
            mother_label = geff_graph.nodes[div][label_key]
            daughter_label = geff_graph.nodes[daughter][label_key]
            if daughter_label not in tracks:
                tracks[daughter_label] = []
            tracks[daughter_label].append(mother_label)
    return tracks


def _get_metadata(
    metadata: geff.GeffMetadata, time_key: str, x_key: str, y_key: str
) -> dict[str, str]:
    """
    Extract metadata from GEFF metadata object.

    Args:
        metadata (geff.GeffMetadata): The GEFF metadata.
        time_key (str): The key for the time/frame attribute.
        x_key (str): The key for the x coordinate attribute.
        y_key (str): The key for the y coordinate attribute.

    Returns:
        dict[str, str]: A dictionary of metadata key-value pairs.
    """
    md = {}
    x_axis = None
    y_axis = None
    if metadata.axes is not None:
        for axis in metadata.axes:
            if axis.name == time_key:
                md["UnitT"] = axis.unit
                md["ScaleT"] = axis.scale
                md["ScaledUnitT"] = axis.scaled_unit
            elif axis.name == x_key:
                x_axis = axis
            elif axis.name == y_key:
                y_axis = axis

    if x_axis is not None and y_axis is not None:
        if x_axis.unit == y_axis.unit:
            md["UnitXY"] = x_axis.unit
        else:
            ut.show_warning(
                f"Different units for x and y axes: '{x_axis.unit}' and '{y_axis.unit}'. "
                "UnitXY metadata will not be set."
            )
        if x_axis.scale == y_axis.scale:
            md["ScaleXY"] = x_axis.scale
        else:
            ut.show_warning(
                f"Different scales for x and y axes: '{x_axis.scale}' and '{y_axis.scale}'. "
                "ScaleXY metadata will not be set."
            )
        if x_axis.scaled_unit == y_axis.scaled_unit:
            md["ScaledUnitXY"] = x_axis.scaled_unit

    return md


def import_geff(
    geff_path: StoreLike,
) -> tuple[np.ndarray, dict[int, list[int]], dict[str, str], str | None]:
    """
    Import a GEFF file.

    Args:
        geff_path (StoreLike): The path to the GEFF file to import.

    Returns:
        tuple[np.ndarray, dict[int, list[int]], dict[str, str], str | None]: A tuple containing:
            - A positions array with columns [label, time, y, x].
            - A tracks dictionary mapping each daughter label to a list of its mother labels.
            - A dictionary of metadata key-value pairs.
            - The path to the labels image array if present, None otherwise.
    """
    geff_graph, geff_md = geff.read(geff_path, structure_validation=True)
    
    _check_preconditions(geff_graph, geff_md)

    if geff_md is not None:
        label_key, labels_path = _identify_labels_path(geff_md)
    else:
        label_key, labels_path = None, None
    # Even if we have a label key from the related objects, we need to check 
    # that it's actually present in the graph nodes.
    label_key = _identify_prop(geff_md, geff_graph, label_key)
    if label_key is None:
        label_key = "label"
        _generate_label(geff_graph)
        ut.show_debug("Node labels generated and assigned to 'label'.")
    else:
        ut.show_debug(f"Identified label key: '{label_key}'.")

    time_key = _identify_prop(geff_md, geff_graph, "frame")
    if time_key is None:
        ut.show_debug(
            "No frame-like property identified in GEFF metadata. "
            "Attempting to identify time axis from display hints or axes.",
        )
        time_key = _identify_time_axis(geff_md, geff_graph)

    x_key = _identify_prop(geff_md, geff_graph, "x")
    y_key = _identify_prop(geff_md, geff_graph, "y")
    if x_key is None or y_key is None:
        ut.show_debug(
            "No x/y properties identified in GEFF metadata. "
            "Attempting to identify space axes from display hints or axes.",
        )
    x_key, y_key = _identify_space_axes(geff_md, geff_graph)
    ut.show_debug(f"Identified axes: '{time_key}', x: '{x_key}', y: '{y_key}'.")

    positions = _build_positions_array(geff_graph, label_key, time_key, x_key, y_key)
    tracks = _build_tracks_dict(geff_graph, label_key)

    if geff_md is not None:
        metadata = _get_metadata(geff_md, time_key, x_key, y_key)
    else:
        metadata = {}

    return positions, tracks, metadata, labels_path
