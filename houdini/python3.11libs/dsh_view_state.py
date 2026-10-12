"""Houdini view state. Executed on the Bridge owning thread."""
from __future__ import annotations

import hou


def _snapshot_obj_visibility() -> dict:
    states = {}
    for child in hou.node("/obj").children():
        try:
            states[child.path()] = bool(child.isDisplayFlagSet())
        except Exception:
            pass
    return states


def _restore_obj_visibility(states: dict) -> list:
    errors = []
    for path, visible in states.items():
        node = hou.node(path)
        if node is None:
            errors.append(f"missing object during restore: {path}")
            continue
        try:
            node.setDisplayFlag(bool(visible))
        except Exception as error:
            errors.append(f"{path}: {error}")
    return errors


def _snapshot_selection() -> list:
    try:
        return [node.path() for node in hou.selectedNodes()]
    except Exception:
        return []


def _restore_selection(paths: list) -> list:
    errors = []
    try:
        hou.clearAllSelected()
    except Exception as error:
        return [str(error)]
    for path in paths:
        node = hou.node(path)
        if node is not None:
            try:
                node.setSelected(True)
            except Exception as error:
                errors.append(f"{path}: {error}")
    return errors


_NAMED_DIRECTIONS = {
    "iso": (1.0, 0.7, 1.0),
    "front": (0.0, 0.25, 1.0),
    "side": (1.0, 0.25, 0.0),
    "top": (0.001, 1.0, 0.001),
}
