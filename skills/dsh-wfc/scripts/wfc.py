#!/usr/bin/env python3
"""Deterministic simple-tiled WFC with backtracking and Houdini instance resolution.

Standard-library only. The solver knows structure and sockets, never visual assets.
"""
from __future__ import annotations

import argparse
import copy
from collections import deque
import hashlib
import heapq
import itertools
import json
import math
from pathlib import Path
import random
import sys
import time


class WfcError(ValueError):
    def __init__(self, code, message, **details):
        super().__init__(message)
        self.code = code
        self.details = details


class Contradiction(Exception):
    pass


class BudgetExceeded(Exception):
    pass


def _keys(value, allowed, where, required=()):
    if not isinstance(value, dict):
        raise WfcError("invalid_schema", f"{where} must be an object")
    unknown = set(value) - set(allowed)
    missing = set(required) - set(value)
    if unknown or missing:
        raise WfcError("invalid_schema", f"{where} has unknown or missing fields",
                       unknown=sorted(unknown), missing=sorted(missing))


def _string(value, where):
    if not isinstance(value, str) or not value.strip():
        raise WfcError("invalid_schema", f"{where} must be a nonempty string")
    return value


def _number(value, where, positive=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise WfcError("invalid_schema", f"{where} must be a finite number")
    if positive and value <= 0:
        raise WfcError("invalid_schema", f"{where} must be positive")
    return float(value)


def _integer(value, where, minimum=None):
    if isinstance(value, bool) or not isinstance(value, int):
        raise WfcError("invalid_schema", f"{where} must be an integer")
    if minimum is not None and value < minimum:
        raise WfcError("invalid_schema", f"{where} must be at least {minimum}")
    return value


def _vec(value, where, length=3, positive=False, integer=False):
    if not isinstance(value, list) or len(value) != length:
        raise WfcError("invalid_schema", f"{where} must contain {length} numbers")
    if integer:
        return [_integer(v, f"{where}[{i}]", 1 if positive else None) for i, v in enumerate(value)]
    return [_number(v, f"{where}[{i}]", positive=positive) for i, v in enumerate(value)]


def _tags(value, where):
    if not isinstance(value, list):
        raise WfcError("invalid_schema", f"{where} must be an array")
    result = [_string(v, f"{where}[{i}]") for i, v in enumerate(value)]
    if len(set(result)) != len(result):
        raise WfcError("invalid_schema", f"{where} contains duplicate tags")
    return tuple(result)


def _bits(mask):
    while mask:
        bit = mask & -mask
        yield bit.bit_length() - 1
        mask ^= bit


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _digest(value):
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def read_json(filename):
    path = Path(filename)
    try:
        with path.open("r", encoding="utf-8") as stream:
            value = json.load(stream)
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise WfcError("invalid_json", f"Cannot read JSON: {path}: {error}") from error
    return value


def write_json(filename, value, force=False):
    path = Path(filename)
    if not path.parent.is_dir():
        raise WfcError("invalid_output", f"Output directory does not exist: {path.parent}")
    try:
        with path.open("w" if force else "x", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
    except FileExistsError as error:
        raise WfcError("output_exists", f"Refusing to overwrite {path}; use --force") from error
    except OSError as error:
        raise WfcError("invalid_output", f"Cannot write {path}: {error}") from error


DEFAULT_DIRECTIONS = {
    "px": {"opposite": "nx", "delta": [1, 0, 0]},
    "nx": {"opposite": "px", "delta": [-1, 0, 0]},
    "py": {"opposite": "ny", "delta": [0, 1, 0]},
    "ny": {"opposite": "py", "delta": [0, -1, 0]},
    "pz": {"opposite": "nz", "delta": [0, 0, 1]},
    "nz": {"opposite": "pz", "delta": [0, 0, -1]},
}
# Local +Z is forward, +Y is up. Positive Houdini yaw sends +X to -Z.
YAW_DIRECTION = {
    0: {"px": "px", "nx": "nx", "pz": "pz", "nz": "nz", "py": "py", "ny": "ny"},
    90: {"px": "nz", "nx": "pz", "pz": "px", "nz": "nx", "py": "py", "ny": "ny"},
    180: {"px": "nx", "nx": "px", "pz": "nz", "nz": "pz", "py": "py", "ny": "ny"},
    270: {"px": "pz", "nx": "nz", "pz": "nx", "nz": "px", "py": "py", "ny": "ny"},
}


def rotate_y(vector, yaw):
    x, y, z = vector
    if yaw == 0:
        return [x, y, z]
    if yaw == 90:
        return [z, y, -x]
    if yaw == 180:
        return [-x, y, -z]
    if yaw == 270:
        return [-z, y, x]
    raise WfcError("invalid_yaw", f"Unsupported yaw: {yaw}")


def yaw_quaternion(yaw):
    angle = math.radians(yaw)
    return [0.0, math.sin(angle / 2), 0.0, math.cos(angle / 2)]


class Problem:
    """Validated immutable problem definition and adjacency index."""

    def __init__(self, spec):
        _keys(spec, {
            "schema_version", "name", "shape", "cell_size", "origin", "pivot_offset",
            "directions", "modules", "socket_pairs", "constraints", "boundary_sockets",
            "counts", "connectivity", "seed", "active", "cells", "edges", "budget",
        }, "spec", {"schema_version", "modules"})
        if spec["schema_version"] != 1:
            raise WfcError("invalid_schema", "Only schema_version 1 is supported")
        self.spec = spec
        self.seed = _integer(spec.get("seed", 0), "seed")
        self.cell_size = _vec(spec.get("cell_size", [1, 1, 1]), "cell_size", positive=True)
        self.origin = _vec(spec.get("origin", [0, 0, 0]), "origin")
        self.pivot_offset = _vec(spec.get("pivot_offset", [.5, 0, .5]), "pivot_offset")
        self.directions = self._read_directions(spec.get("directions", DEFAULT_DIRECTIONS))
        self._read_cells(spec)
        self._read_states(spec["modules"])
        self.pairs = {(socket, socket) for state in self.states for socket in state["sockets"].values()}
        for i, pair in enumerate(spec.get("socket_pairs", [])):
            if not isinstance(pair, list) or len(pair) != 2:
                raise WfcError("invalid_schema", f"socket_pairs[{i}] must contain two socket names")
            a, b = (_string(v, f"socket_pairs[{i}]") for v in pair)
            self.pairs.update(((a, b), (b, a)))
        self._read_edges(spec)
        self._read_supports(spec.get("boundary_sockets", {}))
        self.initial = self._read_constraints(spec.get("constraints", []))
        self.counts = self._read_counts(spec.get("counts", []))
        self.connectivity = self._read_connectivity(spec.get("connectivity"))
        self.spec_sha256 = _digest(spec)

    def _read_directions(self, value):
        if not isinstance(value, dict) or not value:
            raise WfcError("invalid_schema", "directions must be a nonempty object")
        result = {}
        for name, entry in value.items():
            _string(name, "direction name")
            _keys(entry, {"opposite", "delta"}, f"directions.{name}", {"opposite", "delta"})
            result[name] = {
                "opposite": _string(entry["opposite"], f"directions.{name}.opposite"),
                "delta": _vec(entry["delta"], f"directions.{name}.delta", integer=True),
            }
            if not any(result[name]["delta"]):
                raise WfcError("invalid_schema", f"directions.{name}.delta cannot be zero")
        for name, entry in result.items():
            opposite = entry["opposite"]
            if opposite not in result or result[opposite]["opposite"] != name:
                raise WfcError("invalid_schema", f"Direction opposites are inconsistent at {name}")
            if entry["delta"] != [-v for v in result[opposite]["delta"]]:
                raise WfcError("invalid_schema", f"Direction deltas are inconsistent at {name}")
        return result

    def _read_cells(self, spec):
        has_shape = "shape" in spec
        has_cells = "cells" in spec
        if has_shape == has_cells:
            raise WfcError("invalid_schema", "Declare exactly one of shape or cells")
        self.cells = []
        if has_shape:
            self.shape = _vec(spec["shape"], "shape", positive=True, integer=True)
            active = None
            if "active" in spec:
                if not isinstance(spec["active"], list):
                    raise WfcError("invalid_schema", "active must be an array of grid coordinates")
                active = {tuple(_vec(v, f"active[{i}]", integer=True))
                          for i, v in enumerate(spec["active"])}
                if len(active) != len(spec["active"]):
                    raise WfcError("invalid_schema", "active contains duplicate cells")
            nx, ny, nz = self.shape
            for z, y, x in itertools.product(range(nz), range(ny), range(nx)):
                coord = (x, y, z)
                if active is None or coord in active:
                    if any(coord[i] < 0 or coord[i] >= self.shape[i] for i in range(3)):
                        raise WfcError("invalid_schema", f"active cell {coord} is outside shape")
                    self.cells.append({"id": ",".join(map(str, coord)), "coord": list(coord)})
        else:
            if "active" in spec:
                raise WfcError("invalid_schema", "active requires shape; cells uses explicit ids")
            if not isinstance(spec["cells"], list) or not spec["cells"]:
                raise WfcError("invalid_schema", "cells must be a nonempty array")
            for i, entry in enumerate(spec["cells"]):
                _keys(entry, {"id", "coord"}, f"cells[{i}]", {"id", "coord"})
                self.cells.append({"id": _string(entry["id"], f"cells[{i}].id"),
                                   "coord": _vec(entry["coord"], f"cells[{i}].coord")})
        if not self.cells:
            raise WfcError("invalid_schema", "No active cells")
        self.index = {}
        self.coord_index = {}
        for i, cell in enumerate(self.cells):
            if cell["id"] in self.index:
                raise WfcError("invalid_schema", f"Duplicate cell id: {cell['id']}")
            self.index[cell["id"]] = i
            self.coord_index.setdefault(tuple(cell["coord"]), []).append(i)

    def _read_states(self, modules):
        if not isinstance(modules, list) or not modules:
            raise WfcError("invalid_schema", "modules must be a nonempty array")
        self.states = []
        self.state_index = {}
        self.prototype_states = {}
        prototypes = set()
        for i, module in enumerate(modules):
            _keys(module, {"id", "asset_key", "weight", "tags", "yaw_variants", "sockets"},
                  f"modules[{i}]", {"id", "sockets"})
            prototype = _string(module["id"], f"modules[{i}].id")
            if prototype in prototypes:
                raise WfcError("invalid_schema", f"Duplicate module id: {prototype}")
            prototypes.add(prototype)
            weight = _number(module.get("weight", 1), f"modules[{i}].weight", positive=True)
            tags = _tags(module.get("tags", []), f"modules[{i}].tags")
            asset_key = _string(module.get("asset_key", prototype), f"modules[{i}].asset_key")
            sockets = module["sockets"]
            if not isinstance(sockets, dict) or set(sockets) != set(self.directions):
                raise WfcError("invalid_schema", f"modules[{i}].sockets must name every direction exactly once")
            sockets = {name: _string(sockets[name], f"modules[{i}].sockets.{name}")
                       for name in self.directions}
            yaws = module.get("yaw_variants", [0])
            if not isinstance(yaws, list) or not yaws:
                raise WfcError("invalid_schema", f"modules[{i}].yaw_variants must be a nonempty array")
            for yaw in yaws:
                _integer(yaw, f"modules[{i}].yaw_variants")
                if yaw not in YAW_DIRECTION:
                    raise WfcError("invalid_schema", f"modules[{i}].yaw_variants accepts only 0/90/180/270")
            if len(set(yaws)) != len(yaws):
                raise WfcError("invalid_schema", f"modules[{i}].yaw_variants must be unique angles")
            if any(yaw and (not {"px", "nx", "pz", "nz"}.issubset(self.directions)
                            or any(name not in YAW_DIRECTION[yaw] for name in self.directions))
                   for yaw in yaws):
                raise WfcError("invalid_schema",
                               "Nonzero yaw requires px/nx/pz/nz and optional py/ny directions")
            self.prototype_states[prototype] = []
            for yaw in yaws:
                state = {
                    "id": f"{prototype}@{yaw}", "prototype": prototype, "yaw": yaw,
                    "asset_key": asset_key, "weight": weight / len(yaws), "tags": tags,
                    "sockets": {YAW_DIRECTION[yaw][local]: socket for local, socket in sockets.items()},
                }
                self.state_index[state["id"]] = len(self.states)
                self.prototype_states[prototype].append(len(self.states))
                self.states.append(state)

    def cell(self, selector, where="cell"):
        if isinstance(selector, str):
            if selector not in self.index:
                raise WfcError("invalid_schema", f"Unknown cell id at {where}: {selector}")
            return self.index[selector]
        coord = tuple(_vec(selector, where))
        matches = self.coord_index.get(coord, [])
        if len(matches) != 1:
            raise WfcError("invalid_schema", f"Cell coordinate at {where} is missing or ambiguous; use its id")
        return matches[0]

    def _read_edges(self, spec):
        count = len(self.cells)
        self.neighbors = [[] for _ in range(count)]
        self.edges = []
        seen = set()
        if "edges" in spec:
            if not isinstance(spec["edges"], list):
                raise WfcError("invalid_schema", "edges must be an array")
            for i, entry in enumerate(spec["edges"]):
                _keys(entry, {"a", "direction", "b"}, f"edges[{i}]", {"a", "direction", "b"})
                a = self.cell(entry["a"], f"edges[{i}].a")
                b = self.cell(entry["b"], f"edges[{i}].b")
                direction = _string(entry["direction"], f"edges[{i}].direction")
                if direction not in self.directions or a == b:
                    raise WfcError("invalid_schema", f"Invalid direction or self-edge at edges[{i}]")
                key = tuple(sorted((a, b)))
                if key in seen:
                    raise WfcError("invalid_schema", f"Duplicate graph edge at edges[{i}]")
                seen.add(key)
                self._add_edge(a, direction, b)
        elif "shape" in spec:
            for a, cell in enumerate(self.cells):
                for direction, entry in self.directions.items():
                    coord = tuple(cell["coord"][i] + entry["delta"][i] for i in range(3))
                    matches = self.coord_index.get(coord, [])
                    if not matches:
                        continue
                    b = matches[0]
                    key = tuple(sorted((a, b)))
                    if key in seen:
                        continue
                    seen.add(key)
                    self._add_edge(a, direction, b)
        self.external = []
        for neighbors in self.neighbors:
            connected = {direction for direction, _ in neighbors}
            self.external.append([name for name in self.directions if name not in connected])

    def _add_edge(self, a, direction, b):
        opposite = self.directions[direction]["opposite"]
        self.edges.append((a, direction, b))
        self.neighbors[a].append((direction, b))
        self.neighbors[b].append((opposite, a))

    def _tag_mask(self, tags):
        required = set(tags)
        mask = 0
        for i, state in enumerate(self.states):
            if required.issubset(state["tags"]):
                mask |= 1 << i
        return mask

    def _read_supports(self, boundary):
        if not isinstance(boundary, dict) or not set(boundary).issubset(self.directions):
            raise WfcError("invalid_schema", "boundary_sockets contains unknown directions")
        self.boundary = {name: _string(socket, f"boundary_sockets.{name}")
                         for name, socket in boundary.items()}
        self.supports = {}
        self.boundary_masks = {}
        for direction in self.directions:
            opposite = self.directions[direction]["opposite"]
            rows = []
            for source in self.states:
                mask = 0
                for target, state in enumerate(self.states):
                    if (source["sockets"][direction], state["sockets"][opposite]) in self.pairs:
                        mask |= 1 << target
                rows.append(mask)
            self.supports[direction] = rows
            if direction in self.boundary:
                self.boundary_masks[direction] = sum(
                    1 << i for i, state in enumerate(self.states)
                    if (state["sockets"][direction], self.boundary[direction]) in self.pairs)

    def _read_constraints(self, constraints):
        initial = [(1 << len(self.states)) - 1 for _ in self.cells]
        for cell, directions in enumerate(self.external):
            for direction in directions:
                if direction in self.boundary_masks:
                    initial[cell] &= self.boundary_masks[direction]
        if not isinstance(constraints, list):
            raise WfcError("invalid_schema", "constraints must be an array")
        for i, entry in enumerate(constraints):
            _keys(entry, {"cell", "module", "yaw", "require_tags", "exclude_tags"},
                  f"constraints[{i}]", {"cell"})
            cell = self.cell(entry["cell"], f"constraints[{i}].cell")
            mask = initial[cell]
            if "module" in entry:
                prototype = _string(entry["module"], f"constraints[{i}].module")
                if prototype not in self.prototype_states:
                    raise WfcError("invalid_schema", f"Unknown module at constraints[{i}]")
                selected = self.prototype_states[prototype]
                if "yaw" in entry:
                    selected = [s for s in selected if self.states[s]["yaw"] == entry["yaw"]]
                mask &= sum(1 << s for s in selected)
            elif "yaw" in entry:
                mask &= sum(1 << s for s, state in enumerate(self.states) if state["yaw"] == entry["yaw"])
            if "require_tags" in entry:
                mask &= self._tag_mask(_tags(entry["require_tags"], f"constraints[{i}].require_tags"))
            if "exclude_tags" in entry:
                excluded = self._tag_mask(_tags(entry["exclude_tags"], f"constraints[{i}].exclude_tags"))
                mask &= ~excluded
            initial[cell] = mask
        return initial

    def _read_counts(self, counts):
        result = []
        if not isinstance(counts, list):
            raise WfcError("invalid_schema", "counts must be an array")
        for i, entry in enumerate(counts):
            _keys(entry, {"id", "tags", "min", "max"}, f"counts[{i}]", {"tags"})
            tags = _tags(entry["tags"], f"counts[{i}].tags")
            if not tags:
                raise WfcError("invalid_schema", f"counts[{i}].tags cannot be empty")
            minimum = _integer(entry.get("min", 0), f"counts[{i}].min", 0)
            maximum = _integer(entry.get("max", len(self.cells)), f"counts[{i}].max", 0)
            if minimum > maximum:
                raise WfcError("invalid_schema", f"counts[{i}].min exceeds max")
            result.append({"id": entry.get("id", f"count_{i}"), "mask": self._tag_mask(tags),
                           "min": minimum, "max": maximum})
        return result

    def _read_connectivity(self, entry):
        if entry is None:
            return None
        _keys(entry, {"id", "tags", "root"}, "connectivity", {"tags"})
        tags = _tags(entry["tags"], "connectivity.tags")
        if not tags:
            raise WfcError("invalid_schema", "connectivity.tags cannot be empty")
        return {"id": entry.get("id", "connectivity"), "mask": self._tag_mask(tags),
                "root": self.cell(entry["root"], "connectivity.root") if "root" in entry else None}

    def metadata(self):
        return {"cell_size": self.cell_size, "origin": self.origin, "pivot_offset": self.pivot_offset}

    def component(self, selected):
        """Read-only subproblem for independent cells; global rules stay outside."""
        result = copy.copy(self)
        remap = {old: new for new, old in enumerate(selected)}
        result.cells = [self.cells[old] for old in selected]
        result.index = {cell["id"]: i for i, cell in enumerate(result.cells)}
        result.coord_index = {}
        for i, cell in enumerate(result.cells):
            result.coord_index.setdefault(tuple(cell["coord"]), []).append(i)
        result.edges = [(remap[a], direction, remap[b]) for a, direction, b in self.edges
                        if a in remap and b in remap]
        result.neighbors = [[(direction, remap[target]) for direction, target in self.neighbors[old]
                             if target in remap] for old in selected]
        result.external = [[name for name in self.directions
                            if name not in {direction for direction, _ in neighbors}]
                           for neighbors in result.neighbors]
        result.initial = [self.initial[old] for old in selected]
        result.counts = []
        result.connectivity = None
        return result


class Solver:
    def __init__(self, problem, budget=None, seed=None):
        self.p = problem
        self.seed = problem.seed if seed is None else _integer(seed, "seed")
        self.rng = random.Random(self.seed)
        defaults = {"max_steps": 100000, "max_backtracks": 10000, "max_seconds": 30.0}
        supplied = problem.spec.get("budget", {})
        _keys(supplied, set(defaults), "budget")
        defaults.update(supplied)
        defaults.update(budget or {})
        self.max_steps = _integer(defaults["max_steps"], "max_steps", 0)
        self.max_backtracks = _integer(defaults["max_backtracks"], "max_backtracks", 0)
        self.max_seconds = _number(defaults["max_seconds"], "max_seconds", positive=True)
        self.deadline = time.monotonic() + self.max_seconds
        self.domains = problem.initial.copy()
        self.versions = [0] * len(self.domains)
        self.heap = [(domain.bit_count(), 0, cell) for cell, domain in enumerate(self.domains)]
        heapq.heapify(self.heap)
        self.trail = []
        self.queue = deque(range(len(self.domains)))
        self.stats = {"steps": 0, "backtracks": 0, "domain_reductions": 0, "global_conflicts": 0}
        self.last_reason = "no solution"

    def _check_time(self):
        if time.monotonic() >= self.deadline:
            raise BudgetExceeded("max_seconds")

    def _restrict(self, cell, mask, reason):
        old = self.domains[cell]
        new = old & mask
        if new == old:
            return False
        self.trail.append((cell, old))
        self.domains[cell] = new
        self.versions[cell] += 1
        self.stats["domain_reductions"] += 1
        if new.bit_count() > 1:
            heapq.heappush(self.heap, (new.bit_count(), self.versions[cell], cell))
        self.queue.append(cell)
        if not new:
            self.last_reason = reason
            raise Contradiction(reason)
        return True

    def _propagate(self):
        while True:
            while self.queue:
                self._check_time()
                source = self.queue.popleft()
                domain = self.domains[source]
                for direction, target in self.p.neighbors[source]:
                    allowed = 0
                    for state in _bits(domain):
                        allowed |= self.p.supports[direction][state]
                    self._restrict(target, allowed, f"socket:{self.p.cells[source]['id']}:{direction}")
            changed = False
            for rule in self.p.counts:
                assigned = possible = 0
                for domain in self.domains:
                    if domain & (domain - 1) == 0 and domain & rule["mask"]:
                        assigned += 1
                    if domain & rule["mask"]:
                        possible += 1
                if assigned > rule["max"] or possible < rule["min"]:
                    self.last_reason = f"count:{rule['id']}"
                    raise Contradiction(self.last_reason)
                for cell, domain in enumerate(self.domains):
                    if domain & (domain - 1) == 0:
                        continue
                    if assigned == rule["max"]:
                        changed |= self._restrict(cell, ~rule["mask"], f"count:{rule['id']}")
                    elif possible == rule["min"]:
                        changed |= self._restrict(cell, rule["mask"], f"count:{rule['id']}")
            if not changed:
                return

    def _select(self):
        while self.heap:
            count, version, cell = heapq.heappop(self.heap)
            if version == self.versions[cell] and count == self.domains[cell].bit_count() and count > 1:
                return cell
        return None

    def _ordered_candidates(self, mask):
        candidates = [(state, self.p.states[state]["weight"]) for state in _bits(mask)]
        result = []
        while candidates:
            value = self.rng.random() * sum(weight for _, weight in candidates)
            for i, (state, weight) in enumerate(candidates):
                value -= weight
                if value < 0:
                    result.append(candidates.pop(i)[0])
                    break
        return result

    def _restore(self, mark):
        changed = set()
        while len(self.trail) > mark:
            cell, old = self.trail.pop()
            self.domains[cell] = old
            changed.add(cell)
        self.queue.clear()
        for cell in changed:
            self.versions[cell] += 1
            count = self.domains[cell].bit_count()
            if count > 1:
                heapq.heappush(self.heap, (count, self.versions[cell], cell))

    def _connectivity_failure(self):
        rule = self.p.connectivity
        if not rule:
            return None
        selected = {cell for cell, domain in enumerate(self.domains) if bool(domain & rule["mask"])}
        if rule["root"] is not None and rule["root"] not in selected:
            return f"connectivity:{rule['id']}:root"
        if not selected:
            return None
        reached = {rule["root"] if rule["root"] is not None else min(selected)}
        pending = list(reached)
        while pending:
            source = pending.pop()
            for _, target in self.p.neighbors[source]:
                if target in selected and target not in reached:
                    reached.add(target)
                    pending.append(target)
        return None if reached == selected else f"connectivity:{rule['id']}"

    def _report(self, status, reason=None):
        result = {
            "schema_version": 1, "status": status, "seed": self.seed,
            "spec_sha256": self.p.spec_sha256, **self.p.metadata(),
            "statistics": self.stats,
            "budget": {"max_steps": self.max_steps, "max_backtracks": self.max_backtracks,
                       "max_seconds": self.max_seconds},
        }
        if reason:
            result["reason"] = reason
        if status == "solved":
            result["cells"] = []
            for cell, domain in enumerate(self.domains):
                state = self.p.states[domain.bit_length() - 1]
                result["cells"].append({"index": cell, **self.p.cells[cell], "module": state["id"],
                                        "prototype": state["prototype"], "yaw": state["yaw"],
                                        "asset_key": state["asset_key"], "tags": list(state["tags"])})
        return result

    def _solve_independent_components(self):
        """Avoid cross-component backtracking; all parts share one global budget."""
        unseen = set(range(len(self.p.cells)))
        components = []
        while unseen:
            pending = [min(unseen)]
            unseen.remove(pending[0])
            component = []
            while pending:
                cell = pending.pop()
                component.append(cell)
                for _, target in self.p.neighbors[cell]:
                    if target in unseen:
                        unseen.remove(target)
                        pending.append(target)
            components.append(sorted(component))
        if len(components) < 2:
            return None
        budget = {"max_steps": self.max_steps, "max_backtracks": self.max_backtracks,
                  "max_seconds": self.max_seconds}
        for cells in components:
            self._check_time()
            solver = Solver(self.p.component(cells), budget, self.seed)
            solver.deadline = self.deadline
            solver.rng = self.rng
            solver.stats = self.stats
            result = solver.solve()
            if result["status"] != "solved":
                return self._report(result["status"], result.get("reason"))
            for cell in result["cells"]:
                self.domains[self.p.index[cell["id"]]] = 1 << self.p.state_index[cell["module"]]
        return self._report("solved")

    def solve(self):
        if not self.p.counts and not self.p.connectivity:
            try:
                result = self._solve_independent_components()
                if result is not None:
                    return result
            except BudgetExceeded as error:
                return self._report("budget_exceeded", str(error))
        if any(not domain for domain in self.domains):
            return self._report("unsatisfiable", "empty_initial_domain")
        try:
            self._propagate()
        except Contradiction:
            return self._report("unsatisfiable", self.last_reason)
        except BudgetExceeded as error:
            return self._report("budget_exceeded", str(error))
        decisions = []
        while True:
            try:
                self._check_time()
                cell = self._select()
                needs_restore = False
                if cell is None:
                    failure = self._connectivity_failure()
                    if failure is None:
                        return self._report("solved")
                    self.last_reason = failure
                    self.stats["global_conflicts"] += 1
                    needs_restore = True
                else:
                    decisions.append({"cell": cell, "mark": len(self.trail),
                                      "remaining": self._ordered_candidates(self.domains[cell])})
                while True:
                    if not decisions:
                        return self._report("unsatisfiable", self.last_reason)
                    decision = decisions[-1]
                    if needs_restore:
                        if self.stats["backtracks"] >= self.max_backtracks:
                            raise BudgetExceeded("max_backtracks")
                        self.stats["backtracks"] += 1
                        self._restore(decision["mark"])
                    if not decision["remaining"]:
                        decisions.pop()
                        needs_restore = True
                        continue
                    if self.stats["steps"] >= self.max_steps:
                        raise BudgetExceeded("max_steps")
                    self.stats["steps"] += 1
                    candidate = decision["remaining"].pop(0)
                    try:
                        self._restrict(decision["cell"], 1 << candidate, "decision")
                        self._propagate()
                        break
                    except Contradiction:
                        needs_restore = True
            except BudgetExceeded as error:
                return self._report("budget_exceeded", str(error))


def verify_layout(problem, layout):
    _keys(layout, {"schema_version", "status", "seed", "spec_sha256", "cell_size", "origin",
                   "pivot_offset", "statistics", "budget", "cells", "reason"}, "layout",
          {"schema_version", "status", "spec_sha256", "cells"})
    if layout["schema_version"] != 1 or layout["status"] != "solved":
        raise WfcError("invalid_layout", "Only a solved schema_version 1 layout can be verified")
    if layout["spec_sha256"] != problem.spec_sha256:
        raise WfcError("invalid_layout", "Layout belongs to a different spec")
    for key, value in problem.metadata().items():
        if key in layout and layout[key] != value:
            raise WfcError("invalid_layout", f"Layout {key} differs from spec")
    if not isinstance(layout["cells"], list) or len(layout["cells"]) != len(problem.cells):
        raise WfcError("invalid_layout", "Layout cell count differs from spec")
    selected = {}
    for i, entry in enumerate(layout["cells"]):
        if not isinstance(entry, dict) or "id" not in entry or "module" not in entry:
            raise WfcError("invalid_layout", f"cells[{i}] requires id and module")
        if entry["id"] not in problem.index or entry["id"] in selected:
            raise WfcError("invalid_layout", f"Unknown or duplicate cell: {entry['id']}")
        cell = problem.index[entry["id"]]
        if entry.get("coord", problem.cells[cell]["coord"]) != problem.cells[cell]["coord"]:
            raise WfcError("invalid_layout", f"Cell coordinates differ: {entry['id']}")
        if entry["module"] not in problem.state_index:
            raise WfcError("invalid_layout", f"Unknown structural state: {entry['module']}")
        state_index = problem.state_index[entry["module"]]
        if not (problem.initial[cell] >> state_index) & 1:
            raise WfcError("invalid_layout", f"Fixed/boundary constraint failed at {entry['id']}")
        state = problem.states[state_index]
        for key in ("prototype", "yaw", "asset_key"):
            if key in entry and entry[key] != state[key]:
                raise WfcError("invalid_layout", f"State metadata differs at {entry['id']}: {key}")
        selected[cell] = state_index
    if len(selected) != len(problem.cells):
        raise WfcError("invalid_layout", "Layout omits active cells")
    for a, direction, b in problem.edges:
        opposite = problem.directions[direction]["opposite"]
        pair = (problem.states[selected[a]]["sockets"][direction],
                problem.states[selected[b]]["sockets"][opposite])
        if pair not in problem.pairs:
            raise WfcError("invalid_layout", "Socket mismatch", cells=[problem.cells[a]["id"], problem.cells[b]["id"]],
                           direction=direction, sockets=list(pair))
    for rule in problem.counts:
        actual = sum(bool((1 << state) & rule["mask"]) for state in selected.values())
        if not rule["min"] <= actual <= rule["max"]:
            raise WfcError("invalid_layout", f"Count constraint failed: {rule['id']}", actual=actual)
    domains = [1 << selected[cell] for cell in range(len(selected))]
    checker = Solver(problem, budget={"max_seconds": 30})
    checker.domains = domains
    failure = checker._connectivity_failure()
    if failure:
        raise WfcError("invalid_layout", f"Connectivity constraint failed: {failure}")
    return {"status": "valid", "spec_sha256": problem.spec_sha256,
            "cell_count": len(selected), "edge_count": len(problem.edges)}


def _fit_variant(variant, cell_size, yaw, where):
    _keys(variant, {"id", "asset", "weight", "bounds_min", "bounds_max", "anchor", "fit"},
          where, {"id", "asset", "bounds_min", "bounds_max"})
    minimum = _vec(variant["bounds_min"], where + ".bounds_min")
    maximum = _vec(variant["bounds_max"], where + ".bounds_max")
    if any(maximum[i] < minimum[i] for i in range(3)):
        raise WfcError("invalid_catalog", f"Inverted bounds at {where}")
    anchor = _vec(variant.get("anchor", [(minimum[0] + maximum[0]) / 2, minimum[1],
                                         (minimum[2] + maximum[2]) / 2]), where + ".anchor")
    if any(not minimum[i] <= anchor[i] <= maximum[i] for i in range(3)):
        raise WfcError("invalid_catalog", f"Anchor must lie inside measured bounds at {where}")
    fit = variant.get("fit", {"mode": "none"})
    _keys(fit, {"mode", "target_size", "min_scale", "max_scale"}, where + ".fit")
    mode = fit.get("mode", "none")
    if mode not in {"none", "uniform", "axes"}:
        raise WfcError("invalid_catalog", f"Unknown fit mode at {where}: {mode}")
    source_size = [maximum[i] - minimum[i] for i in range(3)]
    if mode == "none":
        if set(fit) - {"mode"}:
            raise WfcError("invalid_catalog", f"fit.mode none does not accept scaling options at {where}")
        scale = [1.0, 1.0, 1.0]
        target = None
    else:
        if any(size <= 0 for size in source_size):
            raise WfcError("invalid_catalog", f"Degenerate bounds cannot be scaled at {where}")
        default_target = [cell_size[2], cell_size[1], cell_size[0]] if yaw in (90, 270) else cell_size
        target = _vec(fit.get("target_size", default_target), where + ".fit.target_size", positive=True)
        lower = _vec(fit.get("min_scale", [1, 1, 1]), where + ".fit.min_scale", positive=True)
        upper = _vec(fit.get("max_scale", [1, 1, 1]), where + ".fit.max_scale", positive=True)
        if any(lower[i] > upper[i] for i in range(3)):
            raise WfcError("invalid_catalog", f"min_scale exceeds max_scale at {where}")
        scale = ([target[i] / source_size[i] for i in range(3)] if mode == "axes"
                 else [min(target[i] / source_size[i] for i in range(3))] * 3)
        for i, value in enumerate(scale):
            if not lower[i] <= value <= upper[i]:
                raise WfcError("scale_limit", f"Asset {where} exceeds scale tolerance on axis {'xyz'[i]}",
                               scale=value, min_scale=lower[i], max_scale=upper[i], mode=mode)
    return {"scale": scale, "target_size": target, "source_size": source_size,
            "mode": mode, "bounds_min": minimum, "bounds_max": maximum, "anchor": anchor}


def _choose_variant(variants, seed, cell_id, asset_key):
    ordered = sorted(variants, key=lambda item: item.get("id", ""))
    digest = hashlib.sha256(f"{seed}\0{cell_id}\0{asset_key}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:8], "big") / 2**64 * sum(v["weight"] for v in ordered)
    for variant in ordered:
        value -= variant["weight"]
        if value < 0:
            return variant
    return ordered[-1]


def _world_bounds(fit, position, yaw):
    corners = itertools.product(*zip(fit["bounds_min"], fit["bounds_max"]))
    transformed = []
    for corner in corners:
        local = [fit["scale"][i] * (corner[i] - fit["anchor"][i]) for i in range(3)]
        rotated = rotate_y(local, yaw)
        transformed.append([position[i] + rotated[i] for i in range(3)])
    return {"min": [min(p[i] for p in transformed) for i in range(3)],
            "max": [max(p[i] for p in transformed) for i in range(3)]}


def resolve_instances(layout, catalog, style, catalog_file="catalog.json", variant_seed=None):
    _keys(layout, {"schema_version", "status", "seed", "spec_sha256", "cell_size", "origin",
                   "pivot_offset", "statistics", "budget", "cells", "reason"}, "layout",
          {"schema_version", "status", "seed", "cells", "cell_size", "origin", "pivot_offset"})
    if layout["schema_version"] != 1 or layout["status"] != "solved":
        raise WfcError("invalid_layout", "Asset resolution requires a solved schema_version 1 layout")
    cell_size = _vec(layout["cell_size"], "layout.cell_size", positive=True)
    origin = _vec(layout["origin"], "layout.origin")
    pivot_offset = _vec(layout["pivot_offset"], "layout.pivot_offset")
    seed = layout["seed"] if variant_seed is None else _integer(variant_seed, "variant_seed")
    _integer(seed, "layout.seed")
    _keys(catalog, {"schema_version", "styles"}, "catalog", {"schema_version", "styles"})
    if catalog["schema_version"] != 1 or not isinstance(catalog["styles"], dict):
        raise WfcError("invalid_catalog", "Only catalog schema_version 1 with styles is supported")
    _string(style, "style")
    if style not in catalog["styles"]:
        raise WfcError("invalid_catalog", f"Unknown style: {style}")
    _keys(catalog["styles"][style], {"assets"}, f"styles.{style}", {"assets"})
    assets = catalog["styles"][style]["assets"]
    if not isinstance(assets, dict):
        raise WfcError("invalid_catalog", f"styles.{style}.assets must be an object")
    catalog_root = Path(catalog_file).resolve().parent
    instances = []
    prototypes = {}
    seen_cells = set()
    for i, cell in enumerate(layout["cells"]):
        if not isinstance(cell, dict):
            raise WfcError("invalid_layout", f"cells[{i}] must be an object")
        for key in ("id", "coord", "module", "asset_key", "yaw"):
            if key not in cell:
                raise WfcError("invalid_layout", f"cells[{i}] is missing {key}")
        cell_id = _string(cell["id"], f"cells[{i}].id")
        if cell_id in seen_cells:
            raise WfcError("invalid_layout", f"Duplicate cell id: {cell_id}")
        seen_cells.add(cell_id)
        coord = _vec(cell["coord"], f"cells[{i}].coord")
        yaw = cell["yaw"]
        if isinstance(yaw, bool) or yaw not in YAW_DIRECTION:
            raise WfcError("invalid_layout", f"Invalid yaw at {cell_id}")
        asset_key = _string(cell["asset_key"], f"cells[{i}].asset_key")
        if asset_key not in assets:
            raise WfcError("missing_asset", f"Style {style} has no asset for {asset_key}", cell=cell_id)
        _keys(assets[asset_key], {"variants"}, f"styles.{style}.assets.{asset_key}", {"variants"})
        variants = assets[asset_key]["variants"]
        if not isinstance(variants, list) or not variants:
            raise WfcError("invalid_catalog", f"No variants for {asset_key} in {style}")
        for j, variant in enumerate(variants):
            if not isinstance(variant, dict):
                raise WfcError("invalid_catalog", f"{asset_key}.variants[{j}] must be an object")
            _string(variant.get("id"), f"{asset_key}.variants[{j}].id")
            _string(variant.get("asset"), f"{asset_key}.variants[{j}].asset")
            _number(variant.get("weight", 1), f"{asset_key}.variants[{j}].weight", positive=True)
        if len({variant["id"] for variant in variants}) != len(variants):
            raise WfcError("invalid_catalog", f"Duplicate variant ids for {asset_key} in {style}")
        weighted = [{**variant, "weight": variant.get("weight", 1)} for variant in variants]
        variant = _choose_variant(weighted, seed, cell_id, asset_key)
        where = f"styles.{style}.assets.{asset_key}.variants[{variant['id']}]"
        fit = _fit_variant(variant, cell_size, yaw, where)
        asset_path = Path(variant["asset"])
        if not asset_path.is_absolute():
            asset_path = catalog_root / asset_path
        try:
            asset_path = asset_path.resolve(strict=True)
        except OSError as error:
            raise WfcError("missing_asset", f"Asset file does not exist for {where}: {asset_path}") from error
        if not asset_path.is_file():
            raise WfcError("missing_asset", f"Asset is not a file: {asset_path}")
        position = [origin[i] + (coord[i] + pivot_offset[i]) * cell_size[i] for i in range(3)]
        piece = f"{asset_key}::{variant['id']}"
        instance = {
            "index": i, "cell_id": cell_id, "coord": coord, "module": cell["module"],
            "asset_key": asset_key, "style": style, "variant": variant["id"], "piece": piece,
            "asset": asset_path.as_posix(), "yaw": yaw, "P": position,
            "pivot": fit["anchor"], "scale": fit["scale"], "orient": yaw_quaternion(yaw),
            "fit": {"mode": fit["mode"], "source_size": fit["source_size"],
                    "target_size": fit["target_size"]},
            "world_bounds": _world_bounds(fit, position, yaw),
        }
        instances.append(instance)
        if piece not in prototypes:
            prototypes[piece] = {"piece": piece, "asset_key": asset_key, "variant": variant["id"],
                                 "asset": instance["asset"], "bounds_min": fit["bounds_min"],
                                 "bounds_max": fit["bounds_max"], "anchor": fit["anchor"]}
    return {"schema_version": 1, "status": "resolved", "style": style, "variant_seed": seed,
            "layout_sha256": _digest(layout), "spec_sha256": layout.get("spec_sha256"),
            "cell_count": len(instances), "instances": instances,
            "prototypes": [prototypes[key] for key in sorted(prototypes)]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    commands = {}
    for name in ("validate", "solve", "verify", "resolve"):
        commands[name] = sub.add_parser(name)
    commands["validate"].add_argument("spec")
    commands["solve"].add_argument("spec")
    commands["solve"].add_argument("--output", required=True)
    commands["solve"].add_argument("--seed", type=int)
    commands["solve"].add_argument("--max-steps", type=int)
    commands["solve"].add_argument("--max-backtracks", type=int)
    commands["solve"].add_argument("--max-seconds", type=float)
    commands["solve"].add_argument("--force", action="store_true")
    commands["verify"].add_argument("spec")
    commands["verify"].add_argument("layout")
    commands["resolve"].add_argument("layout")
    commands["resolve"].add_argument("--catalog", required=True)
    commands["resolve"].add_argument("--style", required=True)
    commands["resolve"].add_argument("--seed", type=int, dest="variant_seed")
    commands["resolve"].add_argument("--output", required=True)
    commands["resolve"].add_argument("--force", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command == "validate":
            problem = Problem(read_json(args.spec))
            result = {"status": "valid", "spec_sha256": problem.spec_sha256,
                      "cell_count": len(problem.cells), "structural_state_count": len(problem.states),
                      "edge_count": len(problem.edges)}
            code = 0
        elif args.command == "solve":
            problem = Problem(read_json(args.spec))
            overrides = {key: getattr(args, key) for key in ("max_steps", "max_backtracks", "max_seconds")
                         if getattr(args, key) is not None}
            result = Solver(problem, overrides, args.seed).solve()
            write_json(args.output, result, args.force)
            code = {"solved": 0, "unsatisfiable": 2, "budget_exceeded": 3}[result["status"]]
        elif args.command == "verify":
            result = verify_layout(Problem(read_json(args.spec)), read_json(args.layout))
            code = 0
        else:
            result = resolve_instances(read_json(args.layout), read_json(args.catalog), args.style,
                                       args.catalog, args.variant_seed)
            write_json(args.output, result, args.force)
            code = 0
        summary = {key: value for key, value in result.items() if key not in {"cells", "instances", "prototypes"}}
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return code
    except WfcError as error:
        print(json.dumps({"status": "error", "error": {"code": error.code, "message": str(error),
                                                       "details": error.details}}, ensure_ascii=False, indent=2))
        return 1


if __name__ == "__main__":
    sys.exit(main())
