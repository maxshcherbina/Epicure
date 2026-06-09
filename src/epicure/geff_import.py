import geff
import geff_spec
import networkx as nx
import numpy as np

import epicure.Utils as ut


def _check_preconditions(graph: nx.DiGraph, metadata: geff.GeffMetadata | None) -> None:
    """
    Check that the graph meets the preconditions for import: directed graph and no merging cells.

    Args:
        graph (nx.DiGraph): The GEFF graph to check.
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

    fusions = [n for n in graph.nodes() if graph.in_degree(n) > 1]
    if len(fusions) > 0:
        ut.show_warning(
            f"Merging cells detected (nodes: {fusions}). EpiCure behavior may be affected."
        )


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
) -> str | None:
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
        str | None: The identified time axis.
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
            "No valid time axis found. Please provide a valid axis argument "
            "or ensure that the GEFF file contains a time axis or a time display hint."
        )

    return time_key


def _identify_space_axes(
    geff_md: geff.GeffMetadata | None,
    geff_graph: nx.DiGraph,
) -> tuple[str | None, str | None]:
    """
    Identify the space axes (x, y) from GEFF metadata.

    The function will try to infer them from the GEFF metadata,
    first from the display hints, then from the axes.

    Args:
        geff_md (geff.GeffMetadata | None): The GEFF metadata.
        geff_graph (nx.DiGraph): The GEFF graph.

    Returns:
        tuple[str | None, str | None]: The identified space axes.
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

    return space_keys[0], space_keys[1]


def _generate_label(geff_graph: nx.DiGraph) -> None:
    """
    Add a 'label' node attribute to each node in the graph.
    Each linear path (unbranched segment) receives a unique label starting from 0.

    Args:
        geff_graph (nx.DiGraph): The graph to label. Modified in-place.
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


def import_geff(geff_path: str):
    """Import a GEFF file."""
    geff_graph, geff_md = geff.read(geff_path, structure_validation=True)

    _check_preconditions(geff_graph, geff_md)

    time_key = _identify_prop(geff_md, geff_graph, "frame")
    label_key = _identify_prop(geff_md, geff_graph, "label")

    if time_key is None:
        ut.show_debug(
            "No frame-like property identified in GEFF metadata. "
            "Attempting to identify time axis from display hints or axes.",
        )
        time_key = _identify_time_axis(geff_md, geff_graph)
    x_key, y_key = _identify_space_axes(geff_md, geff_graph)
    ut.show_debug(f"Identified axes: '{time_key}', x: '{x_key}', y: '{y_key}'.")

    units: dict[str, str] = {}
    positions: np.ndarray = np.empty((len(geff_graph), 4), dtype=np.float32)
    tracks: dict[int, list[int]] = {}

    if label_key is None:
        _generate_label(geff_graph)

    return geff_graph, geff_md
