"""Translate detection references when frame-local labels are reassigned."""

from copy import deepcopy
from dataclasses import replace

import numpy as np


def detection_mapping(before, after, start_frame=0, *, allow_partial=False):
    """Map each old detection to its sole new identity, or None if removed/split."""
    mapping = {}
    for offset, (old, new) in enumerate(zip(before, after, strict=True)):
        positive = old > 0
        pairs = np.unique(np.column_stack((old[positive], new[positive])), axis=0)
        for label in np.unique(pairs[:, 0]):
            targets = pairs[pairs[:, 0] == label, 1]
            if allow_partial:
                targets = targets[targets > 0]
            frame = start_frame + offset
            mapping[(frame, int(label))] = (
                (frame, int(targets[0]))
                if len(targets) == 1 and targets[0] > 0 else None
            )
    return mapping


def remap_references(value, mapping, tracking_range=None):
    """Translate ledger/metadata keys; keep missing endpoints as conflict evidence."""
    def key(item):
        item = tuple(item)
        target = mapping.get(item)
        return target if target is not None and target[1] > 0 else item

    if hasattr(value, "detection_endpoints"):
        missing = set(getattr(value, "missing_endpoints", ()))
        endpoints = tuple(tuple(item) if tuple(item) in missing else key(item)
                          for item in value.detection_endpoints)
        return replace(value, detection_endpoints=endpoints,
                       endpoints=tuple(label for _, label in endpoints)) if endpoints else value
    if isinstance(value, dict):
        result = {name: remap_references(item, mapping, tracking_range) for name, item in value.items()}
        for name in ("source", "target", "parent"):
            if isinstance(value.get(name), (tuple, list)) and len(value[name]) == 2:
                result[name] = key(value[name])
        if "daughters" in value:
            result["daughters"] = tuple(key(item) for item in value["daughters"])
        for prefix, frame_field in (("source", "source_frame"), ("target", "target_frame"),
                                    ("parent", "parent_frame"), ("child_a", "child_frame"),
                                    ("child_b", "child_frame")):
            label_field = prefix + "_label"
            if label_field in value and frame_field in value:
                result[label_field] = key((value[frame_field], value[label_field]))[1]
        if value.get("kind") in {"association", "division"}:
            endpoint_names = ("source", "target") if value["kind"] == "association" else ("parent",)
            endpoints = [tuple(value[name]) for name in endpoint_names]
            endpoints.extend(tuple(item) for item in value.get("daughters", ()))
            missing = {tuple(item) for item in value.get("missing_endpoints", ())}
            for endpoint in endpoints:
                in_range = tracking_range is not None and tracking_range[0] <= endpoint[0] <= tracking_range[1]
                if (endpoint in mapping and (mapping[endpoint] is None or mapping[endpoint][1] == 0)) or (in_range and endpoint not in mapping):
                    missing.add(endpoint)
            # A deleted detection cannot be resurrected merely by reusing its number.
            for name in endpoint_names:
                if tuple(value[name]) in missing:
                    result[name] = tuple(value[name])
            if "daughters" in value:
                result["daughters"] = tuple(tuple(item) if tuple(item) in missing else key(item)
                                            for item in value["daughters"])
            if missing:
                result["missing_endpoints"] = tuple(sorted(missing))
        return result
    if isinstance(value, tuple):
        return tuple(remap_references(item, mapping, tracking_range) for item in value)
    if isinstance(value, list):
        return [remap_references(item, mapping, tracking_range) for item in value]
    return deepcopy(value)
