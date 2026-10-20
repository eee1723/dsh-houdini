"""Static request analysis shared by preflight, Raw Gate and execution evidence.

No Houdini imports or scene reads. Each request parses once and carries the same
classification into admission and result reporting.
"""
from __future__ import annotations

import ast
import hashlib
import os

_RAW_HOU_VERB_MAP = {
    "saveItemsToFile": "component_export",
    "loadItemsFromFile": "component_import",
    "saveChildrenToFile": "component_export",
    "loadChildrenFromFile": "component_import",
    "hipFile.save": "scene_save",
    "hipFile.setName": "scene_save_as",
    "createNode": "search_tab_entries + tab_create/tab_apply",
    "setInput": "connect, set_object_parent, or disconnect_input",
    "setFirstInput": "connect, set_object_parent, or disconnect_input",
    "connectInputs": "connect",
    "setName": "rename_node",
    "destroy": "delete_node",
    "cook": "cook_node",
    "setDisplayFlag": "sop_set_output or set_object_visible",
    "setRenderFlag": "sop_set_output",
    "layoutChildren": "layout_nodes",
    "moveToGoodPosition": "layout_nodes",
    "createNetworkBox": "network_boxes",
    "createStickyNote": "network_notes",
    "networkBox.addItem": "network_boxes",
    "networkBox.addNode": "network_boxes",
    "networkBox.removeItem": "network_boxes",
    "networkBox.removeNode": "network_boxes",
    "networkBox.removeAllItems": "network_boxes",
    "networkBox.removeAllNodes": "network_boxes",
    "networkBox.setComment": "network_boxes",
    "networkBox.setColor": "network_boxes",
    "networkBox.setAlpha": "network_boxes",
    "networkBox.setAutoFit": "network_boxes",
    "networkBox.setBounds": "network_boxes",
    "networkBox.setMinimized": "network_boxes",
    "networkBox.fitAroundContents": "network_boxes",
    "networkBox.destroy": "network_boxes or delete_node",
    "parm().set": "set_parm",   # Includes parameter-object and bound-setter aliases.
    "setExpression": "set_parm",  # set_parm 收到字符串值即走表达式路由
    "createDigitalAsset": "hda_create",
    "allowEditingOfContents": "hda_edit",
    "updateFromNode": "hda_edit",
    "matchCurrentDefinition": "hda_edit",
    "removeSpareParms": "hda_edit",
    "setParmTemplateGroup": "hda_set_interface or create_spare_parms",
    "addSpareParmTuple": "create_spare_parms",
    "setKeyframe": "set_keyframes",
    "setKeyframes": "set_keyframes",
    "deleteAllKeyframes": "set_keyframes or set_parm",
    "addSection": "hda_set_section",
    "copyToHDAFile": "hda_version (source library) or hda_fork (independent tool)",
    "changeNodeType": "hda_switch_version",
    "loadPackage": "tool_package_action",
    "unloadPackage": "tool_package_action",
    "activatePackage": "tool_package_action",
    "deactivatePackage": "tool_package_action",
    "setConditional": "hda_set_interface",
}


_NETWORK_BOX_MUTATORS = {
    'addItem', 'addNode', 'removeItem', 'removeNode', 'removeAllItems', 'removeAllNodes', 'setComment', 'setColor',
    'setAlpha', 'setAutoFit', 'setBounds', 'setMinimized',
    'fitAroundContents', 'destroy',
}

_NETWORK_NOTE_MUTATORS = {
    'setText', 'setPosition', 'move', 'shiftPosition', 'setSize', 'resize', 'setBounds',
    'setColor', 'setTextColor', 'setTextSize', 'setMinimized', 'setDrawBackground',
    'setName', 'setSelected', 'setPicked', 'setFromData', 'destroy',
}
_RAW_HOU_VERB_MAP.update({'stickyNote.' + method: 'network_notes' for method in _NETWORK_NOTE_MUTATORS})


_GATE_MUTATING_PREFIXES = (
    "set", "add", "create", "delete", "destroy", "remove", "rename",
    "save", "cook", "render", "bake", "lock", "unlock", "install",
    "copy", "move", "enable", "disable", "press", "reloadPackage", "loadPackageArchive",
)


_GATE_SAFE_PYTHON_METHODS = {"setdefault"}


_GATE_READ_ONLY_PREFIX_COLLISIONS = {"displayNode", "renderNode"}


_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


_REPO_WRITE_HINTS = (
    ".write(", ".write_text(", ".write_bytes(", "shutil.copy", "shutil.move",
    ".save(", "hipfile.save(", "render_frame(", "render_view(",
    "viewport_screenshot(", ".render(", "json.dump(", "pickle.dump(",
    ".export", "makedirs(", "mkdir(", ".touch(",
)


def _literal_attribute(value):
    """Static attribute syntax, including the equivalent literal getattr form."""
    if isinstance(value, ast.Attribute):
        return value.value, value.attr
    if (isinstance(value, ast.Call) and isinstance(value.func, ast.Name)
            and value.func.id == 'getattr' and 2 <= len(value.args) <= 3
            and isinstance(value.args[1], ast.Constant) and isinstance(value.args[1].value, str)):
        return value.args[0], value.args[1].value
    return None, None


def _network_box_mutation_calls(tree) -> dict[int, str]:
    """Receiver-aware raw classification for proven Network Box variables."""
    boxes = set()
    assignments = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            assignments.extend((target, node.value) for target in node.targets)
        elif isinstance(node, ast.AnnAssign):
            assignments.append((node.target, node.value))
        elif isinstance(node, ast.For) and isinstance(node.target, ast.Name):
            value = node.iter
            if (isinstance(value, ast.Call) and isinstance(value.func, ast.Attribute)
                    and value.func.attr in ('networkBoxes', 'iterNetworkBoxes')):
                boxes.add(node.target.id)
    for _ in range(len(assignments) + 1):
        previous = len(boxes)
        for target, value in assignments:
            if not isinstance(target, ast.Name):
                continue
            if isinstance(value, ast.Name) and value.id in boxes:
                boxes.add(target.id)
            elif (isinstance(value, ast.Call) and isinstance(value.func, ast.Attribute)
                  and value.func.attr in ('createNetworkBox', 'findNetworkBox', 'networkBoxBySessionId')):
                boxes.add(target.id)
        if len(boxes) == previous:
            break
    setters = {}
    def mutation(value):
        if isinstance(value, ast.Name):
            return setters.get(value.id)
        receiver, attr = _literal_attribute(value)
        if attr not in _NETWORK_BOX_MUTATORS:
            return None
        proven = isinstance(receiver, ast.Name) and receiver.id in boxes
        proven = proven or (isinstance(receiver, ast.Call)
            and _literal_attribute(receiver.func)[1] in ('createNetworkBox', 'findNetworkBox', 'networkBoxBySessionId'))
        return 'networkBox.' + attr if proven else None
    for _ in range(len(assignments) + 1):
        previous = len(setters)
        for target, value in assignments:
            if isinstance(target, ast.Name) and (method := mutation(value)):
                setters[target.id] = method
        if len(setters) == previous:
            break
    result = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and (method := mutation(node.func)):
            result[id(node)] = method
    return result


def _network_note_mutation_calls(tree) -> dict[int, str]:
    """Classify only proven Sticky Note receivers, including bound setters."""
    notes, lists, setters, factory_aliases, assignments = set(), set(), {}, {}, []
    factories = {'createStickyNote', 'findStickyNote', 'stickyNoteBySessionId'}
    rebound = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store)}
    def factory(value):
        if isinstance(value, ast.Name): return factory_aliases.get(value.id)
        attr = _literal_attribute(value)[1]
        return 'note' if attr in factories else 'list' if attr == 'stickyNotes' else None
    def note_expression(value):
        if isinstance(value, ast.Name): return value.id in notes
        if isinstance(value, ast.Subscript):
            return not isinstance(value.slice, ast.Slice) and list_expression(value.value)
        if not isinstance(value, ast.Call): return False
        if factory(value.func) == 'note': return True
        attr = _literal_attribute(value.func)[1]
        if attr == 'itemBySessionId' and value.args:
            return _literal_attribute(value.args[0])[1] == 'StickyNote'
        return False
    def list_expression(value):
        if isinstance(value, ast.Name): return value.id in lists
        if isinstance(value, ast.Subscript):
            return isinstance(value.slice, ast.Slice) and list_expression(value.value)
        if not isinstance(value, ast.Call): return False
        if factory(value.func) == 'list': return True
        return (isinstance(value.func, ast.Name) and value.func.id in ('list', 'tuple')
                and value.func.id not in rebound and len(value.args) == 1 and not value.keywords
                and list_expression(value.args[0]))
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            assignments.extend((target, node.value) for target in node.targets)
        elif isinstance(node, (ast.AnnAssign, ast.NamedExpr)):
            assignments.append((node.target, node.value))
    for _ in range(len(assignments) + 2):
        previous = (len(notes), len(lists), len(factory_aliases))
        for target, value in assignments:
            if isinstance(target, ast.Name):
                if kind := factory(value): factory_aliases[target.id] = kind
                if note_expression(value): notes.add(target.id)
                if list_expression(value): lists.add(target.id)
        for node in ast.walk(tree):
            if isinstance(node, (ast.For, ast.comprehension)) and isinstance(node.target, ast.Name) and list_expression(node.iter):
                notes.add(node.target.id)
        if previous == (len(notes), len(lists), len(factory_aliases)): break
    def mutation(value):
        if isinstance(value, ast.Name): return setters.get(value.id)
        receiver, attr = _literal_attribute(value)
        if attr not in _NETWORK_NOTE_MUTATORS: return None
        proven = note_expression(receiver) or _literal_attribute(receiver)[1] in ('StickyNote', 'OpStickyNote', 'UniStickyNote')
        return 'stickyNote.' + attr if proven else None
    for _ in range(len(assignments) + 1):
        previous = len(setters)
        for target, value in assignments:
            if isinstance(target, ast.Name) and (method := mutation(value)):
                setters[target.id] = method
        if len(setters) == previous: break
    return {id(node): method for node in ast.walk(tree)
            if isinstance(node, ast.Call) and (method := mutation(node.func))}


def _call_path(node: ast.AST) -> str | None:
    """Return a dotted call path rooted at ``hou`` when one is statically visible.

    ``hou.node(...)`` becomes ``hou.node`` and ``hou.hipFile.save()`` becomes
    ``hou.hipFile.save``.  Calls made through a local alias cannot be proven to
    be HOM here and are deliberately omitted instead of being mislabeled.
    """
    parts: list[str] = []
    current = node
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if not isinstance(current, ast.Name) or current.id != "hou":
        return None
    return ".".join(["hou", *reversed(parts)])


def _python_set_names(tree: ast.AST) -> set[str]:
    """Find set receivers whose bindings all prove a Python set initializer."""
    names: set[str] = set()
    proven_bindings = set()
    rebound = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)
               and isinstance(node.ctx, (ast.Store, ast.Del))}
    rebound.update(node.arg for node in ast.walk(tree) if isinstance(node, ast.arg))
    rebound.update(node.name for node in ast.walk(tree)
                   if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)))
    rebound.update(item.asname or item.name.split('.')[0] for node in ast.walk(tree)
                   if isinstance(node, (ast.Import, ast.ImportFrom)) for item in node.names)
    def bind(target, value):
        if (isinstance(target, (ast.Tuple, ast.List))
                and isinstance(value, (ast.Tuple, ast.List))
                and len(target.elts) == len(value.elts)):
            for item, initial in zip(target.elts, value.elts):
                bind(item, initial)
            return
        is_set = isinstance(value, ast.Set) or (
            isinstance(value, ast.Call)
            and isinstance(value.func, ast.Name)
            and value.func.id == "set"
            and 'set' not in rebound
        )
        if is_set and isinstance(target, ast.Name):
            names.add(target.id)
            proven_bindings.add(id(target))
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Assign, ast.AnnAssign, ast.NamedExpr)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        for target in targets:
            bind(target, node.value)
    # A later assignment, loop binding, argument or import can replace the set
    # with a HOM group. An exemption based on any earlier initializer would
    # then let group.add mutate geometry through the read-only query path.
    unknown_bindings = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)
                        and isinstance(node.ctx, (ast.Store, ast.Del))
                        and id(node) not in proven_bindings}
    unknown_bindings.update(node.arg for node in ast.walk(tree) if isinstance(node, ast.arg))
    unknown_bindings.update(node.name for node in ast.walk(tree)
                            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)))
    unknown_bindings.update(item.asname or item.name.split('.')[0] for node in ast.walk(tree)
                            if isinstance(node, (ast.Import, ast.ImportFrom)) for item in node.names)
    return names - unknown_bindings


def _is_safe_python_method(node: ast.Call, python_sets: set[str]) -> bool:
    if not isinstance(node.func, ast.Attribute):
        return False
    if node.func.attr in _GATE_SAFE_PYTHON_METHODS or node.func.attr in _GATE_READ_ONLY_PREFIX_COLLISIONS:
        return True
    # Real trace: ``names = set(); names.add(...)`` is read-only scene
    # aggregation.  Treat only receivers statically proven to be Python sets as
    # safe; ``hou.Geometry.addAttrib`` and other HOM ``add*`` calls remain gated.
    return (
        node.func.attr == "add"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id in python_sets
    )


def _parameter_write_calls(tree):
    """Conservative lexical aliases, never execute expressions to identify a receiver.

    Track parameter objects and bound setters through assignments. Rebindings
    remain conservative within the submitted batch; this is not a Python sandbox.
    """
    parms, setters = set(), set()
    def parameter(expr):
        return (isinstance(expr, ast.Name) and expr.id in parms or
                isinstance(expr, ast.Call) and _literal_attribute(expr.func)[1] in ('parm', 'parmTuple'))
    def setter(expr):
        receiver, attr = _literal_attribute(expr)
        return (isinstance(expr, ast.Name) and expr.id in setters or
                attr == 'set' and parameter(receiver))
    assignments = []
    def bind(target, value):
        if isinstance(target, ast.Name):
            assignments.append((target.id, value))
        elif isinstance(target, (ast.Tuple, ast.List)) and isinstance(value, (ast.Tuple, ast.List)):
            for t, v in zip(target.elts, value.elts):
                bind(t, v)
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                bind(target, node.value)
        elif isinstance(node, (ast.AnnAssign, ast.NamedExpr)):
            bind(node.target, node.value)
    for _ in range(len(assignments) + 1):
        previous = (len(parms), len(setters))
        for name, expr in assignments:
            if parameter(expr):
                parms.add(name)
            if setter(expr):
                setters.add(name)
        if previous == (len(parms), len(setters)):
            break
    return {id(node) for node in ast.walk(tree) if isinstance(node, ast.Call) and setter(node.func)}


def _bound_mutation_calls(tree, python_sets):
    """Keep known raw methods classified after binding them to local names."""
    aliases, assignments = {}, []
    def bind(target, value):
        if isinstance(target, ast.Name):
            assignments.append((target.id, value))
        elif (isinstance(target, (ast.Tuple, ast.List)) and isinstance(value, (ast.Tuple, ast.List))
                and len(target.elts) == len(value.elts)):
            for item, initial in zip(target.elts, value.elts):
                bind(item, initial)
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                bind(target, node.value)
        elif isinstance(node, (ast.AnnAssign, ast.NamedExpr)):
            bind(node.target, node.value)
    def classify(value):
        if isinstance(value, ast.Name):
            return aliases.get(value.id)
        receiver, attr = _literal_attribute(value)
        if attr in _RAW_HOU_VERB_MAP:
            return 'coveredMutations', attr
        if (attr is None or attr in _GATE_SAFE_PYTHON_METHODS or attr in _GATE_READ_ONLY_PREFIX_COLLISIONS
                or attr == 'add' and isinstance(receiver, ast.Name) and receiver.id in python_sets):
            return None
        if attr.startswith(_GATE_MUTATING_PREFIXES):
            return 'suspectedMutations', attr
        return None
    for _ in range(len(assignments) + 1):
        previous = len(aliases)
        for name, value in assignments:
            if mutation := classify(value):
                aliases[name] = mutation
        if len(aliases) == previous:
            break
    return {id(node): mutation for node in ast.walk(tree) if isinstance(node, ast.Call)
            and (mutation := classify(node.func)) is not None}


def _raw_usage_from_tree(tree: ast.AST) -> dict:
    """Describe raw HOM syntax and gate-relevant mutations for UI/auditing.

    This is structured execution evidence, not a source-code regex.  It shares
    the same covered/suspected mutation rules as the Raw Gate so the client can
    distinguish harmless reads, blocked writes and audited exemptions.
    """
    python_sets = _python_set_names(tree)
    parameter_writes = _parameter_write_calls(tree)
    box_writes = _network_box_mutation_calls(tree)
    note_writes = _network_note_mutation_calls(tree)
    hip_calls = _hip_file_calls(tree)
    bound_mutations = _bound_mutation_calls(tree, python_sets)
    direct: dict[str, int] = {}
    covered: dict[str, int] = {}
    suspected: dict[str, int] = {}
    for node in ast.walk(tree):
        if id(node) in note_writes:
            key = note_writes[id(node)]
            covered[key] = covered.get(key, 0) + 1
            continue
        if id(node) in box_writes:
            key = box_writes[id(node)]
            covered[key] = covered.get(key, 0) + 1
            continue
        if id(node) in parameter_writes:
            covered['parm().set'] = covered.get('parm().set', 0) + 1
            continue
        if hip_calls.get(id(node)) in ('save', 'setName'):
            key = 'hipFile.' + hip_calls[id(node)]
            covered[key] = covered.get(key, 0) + 1
            path = _call_path(node.func)
            if path is not None:
                direct[path] = direct.get(path, 0) + 1
            continue
        if id(node) in bound_mutations and not isinstance(node.func, ast.Attribute):
            kind, key = bound_mutations[id(node)]
            target = covered if kind == 'coveredMutations' else suspected
            target[key] = target.get(key, 0) + 1
            continue
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        path = _call_path(node.func)
        if path is not None:
            direct[path] = direct.get(path, 0) + 1
        attr = node.func.attr
        if path in ("hou.hipFile.save", "hou.hipFile.setName"):
            key = path.removeprefix("hou.")
            covered[key] = covered.get(key, 0) + 1
        elif attr in _RAW_HOU_VERB_MAP:
            covered[attr] = covered.get(attr, 0) + 1
        elif (
            attr == "set"
            and isinstance(node.func.value, ast.Call)
            and isinstance(node.func.value.func, ast.Attribute)
            and node.func.value.func.attr in ("parm", "parmTuple")
        ):
            covered["parm().set"] = covered.get("parm().set", 0) + 1
        elif (
            not _is_safe_python_method(node, python_sets)
            and attr.startswith(_GATE_MUTATING_PREFIXES)
        ):
            suspected[attr] = suspected.get(attr, 0) + 1
    return {
        "directCalls": [
            {"name": name, "count": count}
            for name, count in sorted(direct.items())
        ],
        "coveredMutations": [
            {"name": name, "count": count, "verb": _RAW_HOU_VERB_MAP[name]}
            for name, count in sorted(covered.items())
        ],
        "suspectedMutations": [
            {"name": name, "count": count}
            for name, count in sorted(suspected.items())
        ],
    }


def script_program(code, script):
    """Bind the exact Host-read source to its invocation without reading files here."""
    if script is None:
        return code, None
    if not isinstance(script, dict) or set(script) - {'path', 'sha256', 'bytes', 'entry'}:
        raise ValueError('script must contain only path, sha256, bytes and optional entry')
    filename, expected, size = (script.get(key) for key in ('path', 'sha256', 'bytes'))
    if not isinstance(filename, str) or not os.path.isabs(filename):
        raise ValueError('script.path must be an absolute Host-read source path')
    if not isinstance(code, str):
        raise ValueError('script source must be UTF-8 text')
    encoded = code.encode('utf-8')
    actual = hashlib.sha256(encoded).hexdigest()
    if (not isinstance(expected, str) or expected.lower() != actual
            or type(size) is not int or size != len(encoded)):
        raise ValueError('script source differs from its recorded SHA-256 or byte length; no code was executed')
    entry = script.get('entry')
    if entry is not None and (not isinstance(entry, str) or not entry.strip()):
        raise ValueError('script.entry must be nonempty Python code when provided')
    source = code.removeprefix('\ufeff')
    recorded = {'path': filename, 'sha256': actual, 'bytes': len(encoded)}
    if entry is not None:
        recorded['entry'] = entry
    return source, recorded


def _hidden_execution_message(tree):
    """Known Python loaders cannot hide a second program from this request's AST.

    This is lexical admission, not a Python sandbox or an import interceptor.
    Ordinary compile() remains available for authoring callback/source text.
    """
    if tree is None:
        return None
    other, module, loader = frozenset(), frozenset({'module'}), frozenset({'loader'})

    class Bindings(ast.NodeVisitor):
        """Only lexical locals; nested scopes have their own bindings."""
        def __init__(self):
            self.names, self.outside = set(), set()
        def visit_Name(self, node):
            if isinstance(node.ctx, (ast.Store, ast.Del)):
                self.names.add(node.id)
        def visit_Import(self, node):
            self.names.update(item.asname or item.name.split('.')[0] for item in node.names)
        def visit_ImportFrom(self, node):
            self.names.update(item.asname or item.name for item in node.names if item.name != '*')
        def visit_FunctionDef(self, node):
            self.names.add(node.name)
        visit_AsyncFunctionDef = visit_FunctionDef
        visit_ClassDef = visit_FunctionDef
        def visit_Lambda(self, node):
            pass
        def visit_ListComp(self, node):
            # Iteration targets belong to the comprehension, while assignment
            # expressions in its expressions bind the containing function.
            for generator in node.generators:
                self.visit(generator.iter)
                for value in generator.ifs:
                    self.visit(value)
            for key in ('elt', 'key', 'value'):
                if hasattr(node, key):
                    self.visit(getattr(node, key))
        visit_SetComp = visit_ListComp
        visit_DictComp = visit_ListComp
        visit_GeneratorExp = visit_ListComp
        def visit_Global(self, node):
            self.outside.update(node.names)
        visit_Nonlocal = visit_Global

    class Scan(ast.NodeVisitor):
        def __init__(self, parent=None, local_names=(), parameters=(), *, class_scope=False):
            self.parent, self.locals = parent, set(local_names)
            self.values = dict.fromkeys(parameters, other)
            self.class_scope, self.conditional, self.blocked = class_scope, False, False
            self.namedexpr_scope = self

        def name(self, name):
            if name in self.values:
                return self.values[name]
            if name in self.locals:
                return other  # A function local never falls back to the builtin.
            if self.parent is not None:
                return self.parent.name(name)
            return loader if name in ('exec', 'eval') else module if name in ('builtins', '__builtins__') else other

        def kind(self, value):
            if isinstance(value, ast.Name):
                return self.name(value.id)
            if isinstance(value, ast.NamedExpr):
                return self.kind(value.value)
            receiver, attr = _literal_attribute(value)
            if attr in ('exec', 'eval') and 'module' in self.kind(receiver):
                return loader
            if attr == '__dict__' and 'module' in self.kind(receiver):
                return module
            if (isinstance(value, ast.Subscript) and isinstance(value.slice, ast.Constant)
                    and value.slice.value in ('exec', 'eval') and 'module' in self.kind(value.value)):
                return loader
            return other

        def bind(self, target, value):
            prepared = []
            def collect(item, initial):
                if isinstance(item, ast.Name):
                    prepared.append((item.id, self.kind(initial) if isinstance(initial, ast.AST) else initial))
                elif isinstance(item, (ast.Tuple, ast.List)):
                    values = initial.elts if isinstance(initial, (ast.Tuple, ast.List)) and len(item.elts) == len(initial.elts) else [other] * len(item.elts)
                    for child, value in zip(item.elts, values):
                        collect(child, value)
            collect(target, value)
            # Tuple RHS names resolve before any target is rebound.
            for name, found in prepared:
                self.values[name] = self.name(name) | found if self.conditional else found

        def visit_Call(self, node):
            self.blocked |= 'loader' in self.kind(node.func)
            self.generic_visit(node)

        def visit_Assign(self, node):
            self.visit(node.value)
            for target in node.targets:
                self.bind(target, node.value)
        def visit_AnnAssign(self, node):
            if node.value is not None:
                self.visit(node.value)
                self.bind(node.target, node.value)
        def visit_NamedExpr(self, node):
            self.visit(node.value)
            self.namedexpr_scope.bind(node.target, self.kind(node.value))

        def visit_Import(self, node):
            for item in node.names:
                self.bind(ast.Name(id=item.asname or item.name.split('.')[0]), module if item.name == 'builtins' else other)
        def visit_ImportFrom(self, node):
            for item in node.names:
                if item.name != '*':
                    self.bind(ast.Name(id=item.asname or item.name), loader if node.module == 'builtins' and item.name in ('exec', 'eval') else other)

        def function(self, node, body):
            # Defaults/decorators execute in the surrounding scope. Methods do
            # not close over their class namespace; enclosing function locals do.
            for value in (*node.args.defaults, *node.args.kw_defaults):
                if value is not None:
                    self.visit(value)
            args = (*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs)
            for arg in (*args, node.args.vararg, node.args.kwarg):
                if arg is not None and arg.annotation is not None:
                    self.visit(arg.annotation)
            if getattr(node, 'returns', None) is not None:
                self.visit(node.returns)
            parameters = [arg.arg for arg in args]
            parameters.extend(arg.arg for arg in (node.args.vararg, node.args.kwarg) if arg is not None)
            bindings = Bindings()
            for item in body:
                bindings.visit(item)
            parent = self.parent if self.class_scope else self
            child = Scan(parent, bindings.names - bindings.outside, parameters)
            for item in body:
                child.visit(item)
            self.blocked |= child.blocked

        def visit_FunctionDef(self, node):
            for value in node.decorator_list:
                self.visit(value)
            self.bind(ast.Name(id=node.name), other)
            self.function(node, node.body)
        visit_AsyncFunctionDef = visit_FunctionDef
        def visit_Lambda(self, node):
            self.function(node, [node.body])

        def visit_ClassDef(self, node):
            for value in (*node.decorator_list, *node.bases, *(item.value for item in node.keywords)):
                self.visit(value)
            child = Scan(self, class_scope=True)
            for item in node.body:
                child.visit(item)
            self.blocked |= child.blocked
            self.bind(ast.Name(id=node.name), other)

        def visit_ListComp(self, node):
            self.visit(node.generators[0].iter)
            child = Scan(self)
            child.namedexpr_scope = self.namedexpr_scope
            for index, generator in enumerate(node.generators):
                if index:
                    child.visit(generator.iter)
                child.bind(generator.target, other)
                for value in generator.ifs:
                    child.visit(value)
            for key in ('elt', 'key', 'value'):
                if hasattr(node, key):
                    child.visit(getattr(node, key))
            self.blocked |= child.blocked
        visit_SetComp = visit_ListComp
        visit_DictComp = visit_ListComp
        visit_GeneratorExp = visit_ListComp

        def conditional_body(self, node):
            previous, self.conditional = self.conditional, True
            self.generic_visit(node)
            self.conditional = previous
        visit_If = conditional_body
        visit_IfExp = conditional_body
        visit_For = conditional_body
        visit_AsyncFor = conditional_body
        visit_While = conditional_body
        visit_Try = conditional_body

    scan = Scan()
    scan.visit(tree)
    if scan.blocked:
        return ('Dynamic exec/eval hides executable source from Raw Gate and read-only analysis. '
                'Submit the complete Python batch, or use houdini_exec(script=absolute_path, '
                'code=optional_invocation, expected_sha256=optional_verified_hash); '
                'houdini_job_submit accepts the same source inputs. compile() alone is supported. '
                'allow_raw cannot exempt hidden executable source.')
    return None


class CodeAnalysis:
    """One submitted program and its single, reusable lexical analysis."""

    def __init__(self, code: str, *, entry: str | None = None, filename: str = '<dsh-houdini>'):
        self.code = code if entry is None else code + '\n\n' + entry
        self.filename = filename
        self.syntax_error = None
        try:
            self.tree = ast.parse(code, filename=filename)
            if entry is not None:
                # Parse each authored program before joining ASTs: an invocation
                # must not close a broken string or consume a dangling backslash.
                tail = ast.parse(entry, filename=filename)
                ast.increment_lineno(tail, code.count('\n') + 2)
                self.tree.body.extend(tail.body)
                self.tree.type_ignores.extend(tail.type_ignores)
        except SyntaxError as error:
            self.tree = None
            self.syntax_error = error
        self.raw_usage = _raw_usage_from_tree(self.tree) if self.tree is not None else {}

    def preflight(self, *, mutating_verbs, read_only, raw_gate, allow_raw):
        error = _forbidden_hip_lifecycle_message(self) or _blocking_host_traversal_message(self)
        if error:
            return error, 'forbidden'
        if read_only or raw_gate:
            error = _hidden_execution_message(self.tree)
            if error:
                return error, 'read_only_blocked' if read_only else 'blocked'
        if read_only:
            error = _query_mutation_message(self, mutating_verbs)
            if error:
                return error, 'read_only_blocked'
        if raw_gate:
            error = _gate_message(self, allow_raw)
            if error:
                return error, 'blocked'
        return None, 'not_applicable'

    def compile(self):
        if self.syntax_error is not None:
            raise self.syntax_error
        return compile(self.tree, self.filename, 'exec')


def _analysis(code):
    return code if isinstance(code, CodeAnalysis) else CodeAnalysis(code)


def _raw_usage_analysis(code) -> dict:
    return _analysis(code).raw_usage


def _raw_hou_calls(code) -> dict[str, int]:
    return {item['name']: item['count'] for item in _raw_usage_analysis(code).get('coveredMutations', [])}


def _raw_hou_advisory(code: str, verb_ledger: list) -> str | None:
    """Advisory text when code bypassed the verb vocabulary with raw hou calls."""
    if verb_ledger:
        return None
    counts = _raw_hou_calls(code)
    if not counts:
        return None
    verbs = sorted({_RAW_HOU_VERB_MAP[key] for key in counts})
    detail = ", ".join(f"{key}x{n}" for key, n in sorted(counts.items()))
    return (
        f"{sum(counts.values())} raw hou call(s) bypassed the verb vocabulary "
        f"({detail}). These are covered by verbs: {', '.join(verbs)}. "
        "Prefer the verbs next time — raw hou is the escape hatch for what the "
        "vocabulary does not cover."
    )


def _hip_file_calls(tree):
    """Share resolved HIP operations between lifecycle and covered-write rules."""
    modules, hip_files, methods = {'hou'}, set(), {}
    assignments = []

    def bind(target, value):
        if isinstance(target, ast.Name):
            assignments.append((target.id, value))
        elif (isinstance(target, (ast.Tuple, ast.List))
                and isinstance(value, (ast.Tuple, ast.List))
                and len(target.elts) == len(value.elts)):
            for item, initial in zip(target.elts, value.elts):
                bind(item, initial)

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(item.asname or item.name for item in node.names if item.name == 'hou')
        elif isinstance(node, ast.ImportFrom) and node.module == 'hou':
            hip_files.update(item.asname or item.name for item in node.names if item.name == 'hipFile')
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                bind(target, node.value)
        elif isinstance(node, (ast.AnnAssign, ast.NamedExpr)):
            bind(node.target, node.value)

    def is_hip_file(value):
        receiver, attr = _literal_attribute(value)
        return (isinstance(value, ast.Name) and value.id in hip_files or
                attr == 'hipFile' and isinstance(receiver, ast.Name) and receiver.id in modules)

    def lifecycle_method(value):
        if isinstance(value, ast.Name):
            return methods.get(value.id)
        receiver, attr = _literal_attribute(value)
        if attr in ('load', 'clear', 'save', 'setName') and is_hip_file(receiver):
            return attr
        return None

    # Like the parameter-setter analysis, resolve lexical aliases without
    # evaluating submitted code. Binding a method must not discard the known
    # lifecycle operation; arbitrary dynamic Python remains outside this scan.
    for _ in range(len(assignments) + 1):
        previous = (len(modules), len(hip_files), len(methods))
        for name, value in assignments:
            if isinstance(value, ast.Name) and value.id in modules:
                modules.add(name)
            if is_hip_file(value):
                hip_files.add(name)
            method = lifecycle_method(value)
            if method:
                methods[name] = method
        if previous == (len(modules), len(hip_files), len(methods)):
            break
    return {id(node): method for node in ast.walk(tree) if isinstance(node, ast.Call)
            and (method := lifecycle_method(node.func)) is not None}


def _forbidden_hip_lifecycle_message(code: str) -> str | None:
    """Reject known HIP replacement/reset calls before execution.

    Loading a HIP resets the scene/process lifecycle that owns this very bridge
    request: H21 GUI reproduction lost results/images and eventually restarted
    Houdini, so neither undo nor a Python ``finally`` can make it transactional.
    """
    tree = _analysis(code).tree
    if tree is None:
        return None
    for method in _hip_file_calls(tree).values():
        if method in ('load', 'clear'):
            return (
                f"hou.hipFile.{method}() is forbidden inside dsh-houdini bridge exec: "
                "HIP replacement/reset invalidates the active exec/bridge lifecycle and can "
                "disconnect or restart the shared Houdini process. Open the HIP in "
                "the Houdini UI (including File > New), or use a future host-level "
                "reconnecting operation."
            )
    return None


def _blocking_host_traversal_message(code: str) -> str | None:
    """Keep recursive filesystem discovery off Houdini's serialized GUI thread.

    This is a narrow preflight for known unbounded traversal APIs, not a Python
    sandbox or a guarantee that arbitrary agent code can be interrupted.
    """
    tree = _analysis(code).tree
    if tree is None:
        return None
    os_aliases = {'os'}
    glob_aliases = {'glob'}
    path_modules = {'pathlib'}
    path_constructors = {'Path'}
    path_values = set()
    direct_walk = set()
    direct_glob = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for item in node.names:
                if item.name == 'os':
                    os_aliases.add(item.asname or item.name)
                elif item.name == 'glob':
                    glob_aliases.add(item.asname or item.name)
                elif item.name == 'pathlib':
                    path_modules.add(item.asname or item.name)
        elif isinstance(node, ast.ImportFrom):
            for item in node.names:
                if node.module == 'os' and item.name in ('walk', 'fwalk'):
                    direct_walk.add(item.asname or item.name)
                elif node.module == 'glob' and item.name in ('glob', 'iglob'):
                    direct_glob.add(item.asname or item.name)
                elif node.module == 'pathlib' and item.name == 'Path':
                    path_constructors.add(item.asname or item.name)
    def is_path(value):
        if isinstance(value, ast.Name):
            return value.id in path_values
        if isinstance(value, ast.BinOp) and isinstance(value.op, ast.Div):
            return is_path(value.left)
        if isinstance(value, ast.Attribute):
            return is_path(value.value)
        if not isinstance(value, ast.Call):
            return False
        func = value.func
        if isinstance(func, ast.Name):
            return func.id in path_constructors
        if isinstance(func, ast.Attribute):
            if isinstance(func.value, ast.Name) and func.value.id in path_modules and func.attr == 'Path':
                return True
            if isinstance(func.value, ast.Name) and func.value.id in path_constructors and func.attr in ('cwd', 'home'):
                return True
            return is_path(func.value)
        return False
    # Resolve simple aliases and `root / name` chains without following paths.
    for _ in range(3):
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and is_path(node.value):
                path_values.update(target.id for target in node.targets if isinstance(target, ast.Name))
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and is_path(node.value):
                path_values.add(node.target.id)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name) and (func.id in direct_walk or func.id in direct_glob):
            break
        if isinstance(func, ast.Attribute):
            owner = func.value
            if func.attr == 'rglob':
                break
            if is_path(owner) and func.attr == 'walk':
                break
            if is_path(owner) and func.attr == 'glob':
                pattern = node.args[0] if node.args else next((arg.value for arg in node.keywords if arg.arg == 'pattern'), None)
                if not isinstance(pattern, ast.Constant) or not isinstance(pattern.value, str) or '**' in pattern.value:
                    break
            if (isinstance(owner, ast.Name) and
                ((owner.id in os_aliases and func.attr in ('walk', 'fwalk')) or
                 (owner.id in glob_aliases and func.attr in ('glob', 'iglob')))):
                break
    else:
        return None
    return ('Recursive filesystem traversal is forbidden inside the Houdini bridge: '
            'it can occupy the serialized main-thread queue and leave later requests '
            'with unknown outcomes. Use a bounded file tool outside Houdini, or ask '
            'the parent to inspect project sources. Do not retry timed-out requests.')


def _repo_write_advisory(code: str) -> str | None:
    """exec 代码疑似往插件仓库写文件时返回警告文本；否则 None。

    纯文本启发式（提醒层，不是安全边界）：路径由变量间接拼出的写检不到。
    """
    norm = code.replace("/", "\\").lower()
    root = _REPO_ROOT.replace("/", "\\").lower()
    if root not in norm:
        return None
    if not any(hint in norm for hint in _REPO_WRITE_HINTS):
        return None
    return (
        f"code appears to write into the dsh-houdini plugin repository ({_REPO_ROOT}). "
        "Agent outputs must anchor at $HIP (the directory of hou.hipFile.path()), "
        "never the plugin repo — write under $HIP instead (e.g. $HIP/screenshots, "
        "$HIP/render). If this write is truly intentional, explain why to the user."
    )


def _gate_message(code: str, allow_raw: str | None = None) -> str | None:
    """Return a pre-exec rejection, or ``None`` when this code may run.

    Verb-covered raw calls are never exemptible: use the verb or split the
    low-level operation into a separate, justified ``allow_raw`` call.  The
    exemption only applies to mutating calls for which the vocabulary has no
    direct intent-level operation.
    """
    analysis = _analysis(code)
    if analysis.tree is None:
        return None  # 语法错误交给 exec 自己报
    # Gate and audit must classify the same operation; formerly these loops
    # drifted independently (notably hipFile.setName versus Node.setName).
    usage = analysis.raw_usage
    covered = {item['name']: item['count'] for item in usage['coveredMutations']}
    mutating = {item['name']: item['count'] for item in usage['suspectedMutations']}
    if not covered and not mutating:
        return None
    if not covered and allow_raw:
        return None
    lines = [
        "raw-hou gate: blocked BEFORE execution (the verb vocabulary is the "
        "primary interface; raw hou is gated)."
    ]
    if covered:
        pairs = ", ".join(f"{a} -> {_RAW_HOU_VERB_MAP[a]}" for a in sorted(covered))
        lines.append(f"verb-covered raw call(s): {pairs} — use the verbs instead.")
    if mutating:
        lines.append(
            "possibly scene-mutating raw call(s) with no direct verb: "
            + ", ".join(sorted(mutating)) + "."
        )
    if covered:
        lines.append(
            "allow_raw cannot exempt verb-covered calls. Split genuine low-level "
            "work into a separate call and use verbs for the covered scene operations."
        )
    else:
        lines.append(
            "If no verb genuinely covers the operation, re-issue the SAME call with "
            "allow_raw=\"<why no verb fits>\" — a one-time exemption that is recorded "
            "in the trace (each exemption documents a vocabulary gap)."
        )
    return "\n".join(lines)


def _query_mutation_message(code, mutating_verbs) -> str | None:
    """Reject mutation intent before a ``houdini_inspect`` reaches Houdini."""
    analysis = _analysis(code)
    tree = analysis.tree
    if tree is None:
        return None
    verbs = sorted({
        node.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Name)
        and isinstance(node.ctx, ast.Load)
        and node.id in mutating_verbs
    })
    usage = analysis.raw_usage
    raw = [item["name"] for item in usage.get("coveredMutations", [])]
    raw += [item["name"] for item in usage.get("suspectedMutations", [])]
    if not verbs and not raw:
        return None
    detail = []
    if verbs:
        detail.append("mutating verb(s): " + ", ".join(verbs))
    if raw:
        detail.append("raw/suspected mutation(s): " + ", ".join(sorted(set(raw))))
    return (
        "houdini_inspect is read-only and rejected this code BEFORE execution ("
        + "; ".join(detail)
        + "). Use houdini_exec for scene changes and cooks."
    )
