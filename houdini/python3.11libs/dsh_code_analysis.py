"""Static request analysis shared by preflight, Raw Gate and execution evidence.

No Houdini imports or scene reads. Each request parses once and carries the same
classification into admission and result reporting.
"""
from __future__ import annotations

import ast
import hashlib
import os
import sys
import sysconfig
import types
from importlib.machinery import BuiltinImporter, FrozenImporter, ModuleSpec, PathFinder

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


_GATE_READ_ONLY_PREFIX_COLLISIONS = {"displayNode", "renderNode"}


def _mutation_method_name(name):
    """Match a verb word, not arbitrary text such as settings or copysign.

    HOM uses camelCase; Python extension helpers can use snake_case. This is
    a discovery heuristic, not a proof about arbitrary Python side effects.
    Known covered operations are still matched independently above this rule.
    """
    return name not in _GATE_READ_ONLY_PREFIX_COLLISIONS and any(
        name == prefix or name.startswith(prefix) and
        (name[len(prefix)].isupper() or name[len(prefix)] == '_')
        for prefix in _GATE_MUTATING_PREFIXES)


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


def _standard_module_resolver():
    """Resolve interpreter stdlib API origins without executing an import.

    Third-party/project modules can re-export HOM, so their names never confer
    Python provenance. For the interpreter's own stdlib API, a direct callable
    is Python; its result remains unknown. This does not promise purity of
    callbacks/imports or sandbox arbitrary Python. Existing module attributes
    are checked separately so a known monkeypatch cannot retain this proof.
    """
    roots = {os.path.normcase(os.path.realpath(path)) for path in (
        sysconfig.get_path('stdlib'), sysconfig.get_path('platstdlib'),
        os.path.join(sys.base_prefix, 'DLLs'),
        os.path.join(sys.base_prefix, f'python{sys.version_info.major}{sys.version_info.minor}.zip'),
    ) if path}
    cache = {}

    def trusted(spec):
        if type(spec) is not ModuleSpec or type(spec.name) is not str:
            return False
        if spec.loader is BuiltinImporter or spec.loader is FrozenImporter:
            return spec.name.split('.')[0] in sys.stdlib_module_names
        if type(spec.origin) is not str:
            return False
        origin = os.path.normcase(os.path.realpath(spec.origin))
        if {'site-packages', 'dist-packages'} & set(origin.replace('\\', '/').split('/')):
            return False
        for root in roots:
            try:
                if os.path.commonpath((origin, root)) == root:
                    return True
            except ValueError:
                pass
        return False

    def resolve(module_name):
        if type(module_name) is not str or not module_name or module_name.split('.')[0] not in sys.stdlib_module_names:
            return None
        if module_name in cache:
            return cache[module_name]
        module = sys.modules.get(module_name)
        if module is not None:
            spec = vars(module).get('__spec__') if type(module) is types.ModuleType else None
        else:
            parent_name, _, _ = module_name.rpartition('.')
            parent = resolve(parent_name) if parent_name else None
            if parent_name and parent is None:
                return None
            search = parent.submodule_search_locations if parent_name else None
            if parent_name and (type(search) not in (list, tuple) or any(type(item) is not str for item in search)):
                return None
            spec = (BuiltinImporter.find_spec(module_name) or FrozenImporter.find_spec(module_name)
                    or PathFinder.find_spec(module_name, search))
        cache[module_name] = spec if trusted(spec) and spec.name == module_name else None
        return cache[module_name]

    return resolve


def _callable_references(tree: ast.AST) -> dict[int, tuple | None]:
    """One lexical provenance for Python, HOM and unknown callable references.

    Every binding in the lexical scope must prove the same value kind. This
    intentionally loses precision after an unknown reassignment, including one
    in a closure or a conditional. Containers never confer their kind on their
    elements. No authored expression, import or descriptor is executed here.
    Imported module names do not prove safe members or safe return values.
    """
    builtin_types = {value.__name__: value for value in
                     (str, bytes, bytearray, list, tuple, dict, set, frozenset)}
    literals = {ast.List: list, ast.Tuple: tuple, ast.Set: set, ast.Dict: dict,
                ast.ListComp: list, ast.SetComp: set, ast.DictComp: dict, ast.JoinedStr: str}
    scopes, escaped, writes, classes, function_scopes = {}, set(), [], {}, {}
    standard_module = _standard_module_resolver()

    def ordinary_class(node):
        # Only source-defined ordinary classes have Python's known method
        # lookup. Inheritance, decorators and custom lookup/allocation do not.
        return (not node.bases and not node.keywords and not node.decorator_list
                and not any((isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
                             and item.name in ('__getattribute__', '__getattr__', '__new__'))
                            or (isinstance(item, ast.Name) and isinstance(item.ctx, ast.Store)
                                and item.id in ('__getattribute__', '__getattr__', '__new__'))
                            for item in ast.walk(node)))

    class Scope:
        def __init__(self, parent=None, *, class_scope=False, class_node=None):
            self.parent, self.class_scope, self.bindings = parent, class_scope, {}
            self.wildcard, self.class_node = False, class_node

        def bind(self, target, value):
            if isinstance(target, ast.Name):
                self.bindings.setdefault(target.id, []).append(value)
            elif isinstance(target, (ast.Tuple, ast.List)):
                values = (value.elts if isinstance(value, (ast.Tuple, ast.List))
                          and len(target.elts) == len(value.elts) else [None] * len(target.elts))
                for item, initial in zip(target.elts, values):
                    self.bind(item, initial)

    class Collect(ast.NodeVisitor):
        def __init__(self, scope):
            self.scope, self.namedexpr_scope = scope, scope

        def visit(self, node):
            scopes[id(node)] = self.scope
            return super().visit(node)

        def closure_parent(self):
            parent = self.scope
            while parent.class_scope:
                parent = parent.parent
            return parent

        def visit_Name(self, node):
            if isinstance(node.ctx, (ast.Store, ast.Del)):
                self.scope.bind(node, None)

        def target(self, node):
            # Store targets can contain executable receiver/index expressions.
            # Index them in their real scope without inventing another binding
            # for the simple names already handled by Scope.bind.
            scopes[id(node)] = self.scope
            if isinstance(node, (ast.Tuple, ast.List)):
                for item in node.elts:
                    self.target(item)
            elif isinstance(node, ast.Starred):
                self.target(node.value)
            elif isinstance(node, (ast.Attribute, ast.Subscript)):
                self.visit(node.value)
                if isinstance(node, ast.Subscript):
                    self.visit(node.slice)

        def write(self, target, value):
            if isinstance(target, ast.Starred):
                self.write(target.value, None)
                return
            if isinstance(target, (ast.Tuple, ast.List)):
                values = (value.elts if isinstance(value, (ast.Tuple, ast.List))
                          and len(target.elts) == len(value.elts) else [None] * len(target.elts))
                for item, initial in zip(target.elts, values):
                    self.write(item, initial)
                return
            self.scope.bind(target, value)
            if isinstance(target, (ast.Attribute, ast.Subscript)):
                writes.append((target, value))
            self.target(target)

        def visit_Delete(self, node):
            for target in node.targets:
                self.write(target, None)

        def visit_Assign(self, node):
            self.visit(node.value)
            for target in node.targets:
                self.write(target, node.value)
        def visit_AnnAssign(self, node):
            self.visit(node.annotation)
            if node.value is not None:
                self.visit(node.value)
            self.write(node.target, node.value)
        def visit_AugAssign(self, node):
            self.visit(node.value)
            self.write(node.target, None)
        def visit_NamedExpr(self, node):
            self.visit(node.value)
            self.namedexpr_scope.bind(node.target, node.value)
            self.target(node.target)

        def visit_Import(self, node):
            for item in node.names:
                imported = item.name if item.asname else item.name.split('.')[0]
                value = (imported,) if imported in ('hou', 'builtins') else ('module', imported)
                self.scope.bind(ast.Name(id=item.asname or item.name.split('.')[0]), value)
        def visit_ImportFrom(self, node):
            for item in node.names:
                if item.name == '*':
                    # Star imports can replace any builtin or inferred value.
                    self.scope.wildcard = True
                    continue
                value = ('constructor', builtin_types[item.name]) if node.module == 'builtins' and item.name in builtin_types else (
                    (item.name,) if node.module == 'builtins' and item.name in ('getattr', 'setattr', 'delattr', 'vars', 'locals', 'globals', 'type') else (
                        ('hom_method', 'hou', item.name) if node.module == 'hou' and not node.level else (
                            'imported_member', node.module if not node.level else None, item.name)))
                self.scope.bind(ast.Name(id=item.asname or item.name), value)

        def function(self, node, body):
            for value in (*node.args.defaults, *node.args.kw_defaults):
                if value is not None:
                    self.visit(value)
            for value in getattr(node, 'decorator_list', ()):
                self.visit(value)
            child = Collect(Scope(self.closure_parent()))
            function_scopes[id(node)] = child.scope
            args = (*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs,
                    node.args.vararg, node.args.kwarg)
            positional = (*node.args.posonlyargs, *node.args.args)
            for arg in args:
                if arg is not None:
                    if arg.annotation is not None:
                        self.visit(arg.annotation)
                    initial = ('value', tuple) if arg is node.args.vararg else (
                        ('value', dict) if arg is node.args.kwarg else None)
                    if (self.scope.class_node is not None and positional and arg is positional[0]
                            and not getattr(node, 'decorator_list', ()) and ordinary_class(self.scope.class_node)):
                        initial = ('local_instance', self.scope.class_node)
                    child.scope.bind(ast.Name(id=arg.arg), initial)
            if getattr(node, 'returns', None) is not None:
                self.visit(node.returns)
            for item in body:
                child.visit(item)
        def visit_FunctionDef(self, node):
            self.scope.bind(ast.Name(id=node.name), ('local_function', node) if not node.decorator_list else None)
            self.function(node, node.body)
        visit_AsyncFunctionDef = visit_FunctionDef
        def visit_Lambda(self, node):
            self.function(node, [node.body])

        def visit_ClassDef(self, node):
            self.scope.bind(ast.Name(id=node.name), ('local_class', node) if ordinary_class(node) else None)
            for value in (*node.decorator_list, *node.bases, *(item.value for item in node.keywords)):
                self.visit(value)
            child = Collect(Scope(self.closure_parent(), class_scope=True, class_node=node))
            classes[id(node)] = child.scope
            for item in node.body:
                child.visit(item)

        def visit_For(self, node):
            self.visit(node.iter)
            self.write(node.target, ('iteration', node.iter))
            for item in (*node.body, *node.orelse):
                self.visit(item)
        visit_AsyncFor = visit_For

        def visit_With(self, node):
            for item in node.items:
                self.visit(item.context_expr)
                if item.optional_vars is not None:
                    self.write(item.optional_vars, None)
            for item in node.body:
                self.visit(item)
        visit_AsyncWith = visit_With

        def visit_ListComp(self, node):
            self.visit(node.generators[0].iter)
            child = Collect(Scope(self.closure_parent()))
            child.namedexpr_scope = self.namedexpr_scope
            for index, generator in enumerate(node.generators):
                if index:
                    child.visit(generator.iter)
                child.write(generator.target, ('iteration', generator.iter))
                for value in generator.ifs:
                    child.visit(value)
            for key in ('elt', 'key', 'value'):
                if hasattr(node, key):
                    child.visit(getattr(node, key))
        visit_SetComp = visit_ListComp
        visit_DictComp = visit_ListComp
        visit_GeneratorExp = visit_ListComp

        def visit_Global(self, node):
            escaped.update(node.names)
        visit_Nonlocal = visit_Global
        def visit_ExceptHandler(self, node):
            if node.name:
                self.scope.bind(ast.Name(id=node.name), None)
            self.generic_visit(node)
        def visit_MatchAs(self, node):
            if node.name:
                self.scope.bind(ast.Name(id=node.name), None)
            self.generic_visit(node)
        visit_MatchStar = visit_MatchAs
        def visit_MatchMapping(self, node):
            if node.rest:
                self.scope.bind(ast.Name(id=node.rest), None)
            self.generic_visit(node)

    root = Scope()
    Collect(root).visit(tree)
    resolving, cache = set(), {}

    def name(scope, key):
        if key in escaped or scope.wildcard:
            return None
        identity = (id(scope), key)
        if identity in cache:
            return cache[identity]
        if identity in resolving:
            return None
        resolving.add(identity)
        if key in scope.bindings:
            values = [kind(value) for value in scope.bindings[key]]
            result = values[0] if values and all(value == values[0] for value in values) else (
                ('uncertain_callable', tuple(value for value in values if value and value[0] in
                    ('hom_method', 'unknown_method', 'uncertain_callable'))) if any(
                        value and value[0] in ('hom_method', 'unknown_method', 'uncertain_callable') for value in values) else None)
        elif scope.parent is not None:
            result = name(scope.parent, key)
        else:
            result = ('constructor', builtin_types[key]) if key in builtin_types else (
                (key,) if key in ('hou', 'getattr', 'setattr', 'delattr', 'vars', 'locals', 'globals', 'type') else None)
        resolving.remove(identity)
        cache[identity] = result
        return result

    def kind(value):
        if isinstance(value, tuple):
            if value[0] == 'iteration':
                return ('node',) if kind(value[1]) == ('nodes',) else None
            if value[0] == 'imported_member':
                found = module_member(value[1], value[2])
                # A bare helper import is not a receiver method. Preserve its
                # unknown source instead of imposing HOM naming rules on every
                # Python function (including ordinary project builders).
                return ('unknown_callable',) if found[0] == 'unknown_method' else found
            return value
        if value is None:
            return None
        if isinstance(value, ast.Name):
            return name(scopes.get(id(value), root), value.id)
        if type(value) in literals:
            return ('value', literals[type(value)])
        if isinstance(value, ast.Constant) and type(value.value) in builtin_types.values():
            return ('value', type(value.value))
        if isinstance(value, ast.NamedExpr):
            return kind(value.value)
        if isinstance(value, ast.Subscript) and isinstance(value.slice, ast.Slice):
            base = kind(value.value)
            return base if base and base[0] == 'value' and base[1] in (str, bytes, bytearray, list, tuple) else None
        receiver, attr = _literal_attribute(value)
        if (isinstance(value, ast.Call) and len(value.args) >= 2
                and kind(value.func) == ('getattr',) and isinstance(value.args[1], ast.Constant)
                and isinstance(value.args[1].value, str)):
            receiver, attr = value.args[0], value.args[1].value
        if attr is not None:
            if isinstance(value, ast.Call) and kind(value.func) != ('getattr',):
                return ('unknown_method', attr)
            owner = kind(receiver)
            if (owner and owner[0] in ('global_dict', 'module_dict', 'local_dict')
                    and attr not in {'clear', 'pop', 'popitem', 'setdefault', 'update', '__setitem__', '__delitem__', '__ior__', '__init__'}
                    and callable(getattr(dict, attr, None))):
                return ('python_method', dict, attr)
            if owner and owner[0] in ('value', 'constructor') and callable(getattr(owner[1], attr, None)):
                return ('python_method', owner[1], attr)
            if owner and owner[0] in ('hou', 'node', 'node_type', 'parm'):
                return ('hom_method', owner[0], attr)
            if owner == ('builtins',) and attr in builtin_types:
                return ('constructor', builtin_types[attr])
            if owner == ('builtins',) and attr in ('getattr', 'setattr', 'delattr', 'vars', 'locals', 'globals', 'type'):
                return (attr,)
            if owner and owner[0] in ('local_class', 'local_instance'):
                if attr == '__dict__':
                    return ('local_dict', owner[1])
                if attr == '__class__' and owner[0] == 'local_instance':
                    return ('local_class', owner[1])
                if attr in ('__setattr__', '__delattr__'):
                    return ('local_attribute_writer', owner[1], int(owner[0] == 'local_class'))
                member = local_member(owner[1], attr)
                return ('local_method', owner[1], member[1], owner[0] == 'local_instance') if member[0] == 'local_function' else member
            if owner and owner[0] == 'local_method':
                # Exposing a bound method's function/receiver permits lookup
                # changes that no longer follow the source class definition.
                return ('local_dict', owner[1]) if attr in (
                    '__self__', '__func__', '__dict__', '__code__', '__globals__') else ('unknown_method', attr)
            if owner and owner[0] == 'module':
                if attr == '__dict__':
                    return ('module_dict', owner[1])
                return module_member(owner[1], attr)
            return ('unknown_method', attr)
        if isinstance(value, ast.Call):
            callable_kind = kind(value.func)
            if callable_kind and callable_kind[0] == 'constructor':
                return ('value', callable_kind[1])
            if callable_kind and callable_kind[0] == 'local_class':
                return ('local_instance', callable_kind[1])
            if callable_kind and callable_kind[0] in ('local_function', 'local_method'):
                return local_return(callable_kind[1] if callable_kind[0] == 'local_function' else callable_kind[2])
            if callable_kind in (('globals',), ('locals',), ('vars',)) and not value.args and not value.keywords:
                scope = scopes.get(id(value), root)
                if callable_kind != ('globals',) and scope.class_node is not None:
                    return ('local_dict', scope.class_node)
                # Namespace maps permit dictionary reads, never provenance of
                # their values or a new proof for namespace-mutating methods.
                if callable_kind == ('globals',) or scope.parent is None:
                    return ('global_dict',)
                return ('value', dict)
            if callable_kind == ('type',) and len(value.args) == 1:
                owner = kind(value.args[0])
                if owner and owner[0] == 'local_instance':
                    return ('local_class', owner[1])
            if callable_kind == ('vars',) and len(value.args) == 1:
                owner = kind(value.args[0])
                if owner and owner[0] == 'module':
                    return ('module_dict', owner[1])
                if owner and owner[0] in ('local_class', 'local_instance'):
                    return ('local_dict', owner[1])
            # Explicit read-only HOM return facts; unknown .name() methods do
            # not become strings merely because they share the spelling.
            if callable_kind and callable_kind[0] == 'hom_method':
                _, owner, method = callable_kind
                if (owner == 'hou' and method in ('node', 'pwd', 'nodeBySessionId')
                        or owner == 'node' and method in ('node', 'parent')):
                    return ('node',)
                if owner == 'node' and method in ('children', 'allSubChildren', 'inputs', 'outputs'):
                    return ('nodes',)
                if owner == 'node' and method == 'type':
                    return ('node_type',)
                if owner in ('hou', 'node') and method in ('parm', 'parmTuple'):
                    return ('parm',)
                if (owner in ('node', 'node_type') and method == 'name'
                        or owner == 'node' and method == 'path'):
                    return ('value', str)
        return None

    modified, resolving_members, exposed_namespaces, resolving_returns = {}, set(), set(), set()

    def local_return(node):
        # Preserve explicitly returned callable origins, not general execution
        # or argument inference. A local wrapper must not erase a HOM setter.
        if isinstance(node, ast.AsyncFunctionDef) or id(node) in resolving_returns:
            return None
        class Returns(ast.NodeVisitor):
            def __init__(self): self.values, self.generator = [], False
            def visit_Return(self, value): self.values.append(value.value)
            def visit_Yield(self, value): self.generator = True
            visit_YieldFrom = visit_Yield
            def visit_FunctionDef(self, value): pass
            visit_AsyncFunctionDef = visit_FunctionDef
            visit_Lambda = visit_FunctionDef
            visit_ClassDef = visit_FunctionDef
        returns = Returns()
        for item in node.body:
            returns.visit(item)
        if returns.generator:
            return None
        resolving_returns.add(id(node))
        values = [kind(value) for value in returns.values]
        resolving_returns.remove(id(node))
        retained = [value for value in values if value and value[0] in (
            'hom_method', 'unknown_method', 'uncertain_callable', 'local_function', 'local_method')]
        return (retained[0] if len(retained) == len(values) and retained and all(value == retained[0] for value in retained)
                else ('uncertain_callable', tuple(retained)) if retained else None)

    def local_member(class_node, member):
        identity = ('local', id(class_node))
        key = (identity, member)
        if key in resolving_members:
            return ('unknown_method', member)
        changes = [*modified.get(key, ()), *modified.get((identity, None), ())]
        resolving_members.add(key)
        if changes:
            values = [kind(value) or ('unknown_method', member) for value in changes]
            result = values[0] if all(value == values[0] for value in values) else ('uncertain_callable', tuple(values))
        elif (identity in exposed_namespaces or any(modified.get((identity, hook))
              for hook in ('__class__', '__getattribute__', '__getattr__', '__new__'))):
            result = ('unknown_method', member)
        else:
            # A missing class attribute cannot fall through into its closure.
            result = name(classes[id(class_node)], member) if member in classes[id(class_node)].bindings else None
        resolving_members.remove(key)
        if result and result[0] in ('local_class', 'local_instance', 'unknown_callable'):
            # An authored object stored in a class can be a descriptor. Its
            # lookup result (or an unknown imported callable) is not a proven
            # ordinary Python method.
            result = None
        if result and result[0] == 'uncertain_callable':
            result = ('uncertain_callable', tuple(
                ('unknown_method', member) if not value or value[0] in (
                    'local_class', 'local_instance', 'unknown_callable') else value
                for value in result[1]))
        return result or ('unknown_method', member)

    def namespace(owner):
        if owner and owner[0] in ('module', 'module_dict'):
            return owner[1]
        if owner and owner[0] in ('local_class', 'local_instance', 'local_method', 'local_dict'):
            return ('local', id(owner[1]))
        return None

    def callback_parameters():
        # Only retain known HOM/unknown method callback provenance at explicit
        # local call sites. Do not infer safe receiver/return types for arbitrary
        # parameters or execute a helper to discover what it does.
        for _ in range(len(function_scopes) + 1):
            changed = False
            cache.clear()
            for call in ast.walk(tree):
                if not isinstance(call, ast.Call):
                    continue
                function = kind(call.func)
                if function and function[0] == 'local_class':
                    initializer = name(classes[id(function[1])], '__init__')
                    function = (*initializer[:2], 1) if initializer and initializer[0] == 'local_function' else None
                if function and function[0] == 'local_method':
                    function = ('local_function', function[2], int(function[3]))
                if not function or function[0] != 'local_function':
                    continue
                node = function[1]
                params = (*node.args.posonlyargs, *node.args.args)
                offset = function[2] if len(function) > 2 else 0
                arguments = local_arguments(call)
                if arguments is None:
                    continue
                positional, keywords = arguments
                supplied = [(arg.arg, value) for arg, value in zip(params[offset:], positional)]
                supplied.extend(keywords)
                supplied.extend((arg.arg, value) for arg, value in zip(params[-len(node.args.defaults):], node.args.defaults))
                supplied.extend((arg.arg, value) for arg, value in zip(node.args.kwonlyargs, node.args.kw_defaults) if value is not None)
                scope = function_scopes[id(node)]
                for key, value in supplied:
                    found = kind(value)
                    if key in scope.bindings and _referenced_methods(found) and not any(existing is value for existing in scope.bindings[key]):
                        scope.bindings[key].append(value)
                        changed = True
            if not changed:
                break
        cache.clear()

    def local_arguments(call):
        """Unpack only explicit literal argument lists/dicts, never evaluate data."""
        positional, keywords = [], []
        for value in call.args:
            if isinstance(value, ast.Starred):
                if not isinstance(value.value, (ast.List, ast.Tuple)) or any(isinstance(item, ast.Starred) for item in value.value.elts):
                    return None
                positional.extend(value.value.elts)
            else:
                positional.append(value)
        for item in call.keywords:
            if item.arg is not None:
                keywords.append((item.arg, item.value))
            elif isinstance(item.value, ast.Dict) and all(isinstance(key, ast.Constant) and isinstance(key.value, str) for key in item.value.keys):
                keywords.extend((key.value, value) for key, value in zip(item.value.keys, item.value.values))
            else:
                return None
        return positional, keywords

    def imported_reference(value, fallback):
        if type(value) is types.ModuleType:
            module_name = vars(value).get('__name__')
            return ('module', module_name) if standard_module(module_name) else ('unknown_method', fallback)
        if type(value) in (types.FunctionType, types.BuiltinFunctionType, types.MethodType, type):
            module_name = value.__module__
            if type(module_name) is not str:
                return ('unknown_method', fallback)
            if module_name in ('hou', '_hou'):
                return ('hom_method', 'hou', value.__name__)
            if (spec := standard_module(module_name)) is not None:
                function = value.__func__ if isinstance(value, types.MethodType) else value
                if isinstance(function, types.FunctionType):
                    origin = function.__code__.co_filename
                    if origin != spec.origin and origin != f'<frozen {module_name}>':
                        return ('unknown_method', fallback)
                return ('python_method', module_name, fallback)
        return ('unknown_method', fallback)

    def module_member(module_name, member):
        key = (module_name, member)
        if key in resolving_members:
            return ('unknown_method', member)
        writes = [*modified.get(key, ()), *modified.get((module_name, None), ())]
        if writes:
            resolving_members.add(key)
            values = [kind(value) for value in writes]
            resolving_members.remove(key)
            return ('uncertain_callable', tuple(value or ('unknown_method', member) for value in values))
        if module_name in exposed_namespaces:
            return ('unknown_method', member)
        module = sys.modules.get(module_name)
        if type(module) is types.ModuleType:
            found = imported_reference(vars(module).get(member), member)
            if found[0] == 'hom_method' or standard_module(module_name):
                return found
        if standard_module(module_name):
            return ('python_method', module_name, member)
        return ('unknown_method', member)

    # Resolve writes through the same lexical aliases as calls. Explicit module
    # monkeypatches cannot inherit the original stdlib member's provenance.
    # Once its mutable namespace is exposed, there is no ordinary-API proof to
    # preserve. Do not grow a second interpreter for every possible dict call.
    callback_parameters()
    for node in ast.walk(tree):
        if (found := kind(node)) and found[0] in ('module_dict', 'local_dict'):
            exposed_namespaces.add(namespace(found))
        if isinstance(node, ast.Call):
            target = kind(node.func)
            if target in (('getattr',), ('setattr',), ('delattr',), ('vars',), ('type',)) or (
                    target and target[0] == 'local_attribute_writer'):
                continue  # Literal reflection and writes use the same resolver.
            for index, value in enumerate([*node.args, *(item.value for item in node.keywords)]):
                found = kind(value)
                if found and found[0] in ('local_class', 'local_instance', 'local_method'):
                    if (index == 0 and target and target[0] == 'local_method' and not target[3]
                            and found == ('local_instance', target[1])):
                        continue  # Explicit self in a source-defined unbound call.
                    exposed_namespaces.add(namespace(found))
    cache.clear()
    for target, value in writes:
        owner = kind(target.value)
        if owner and owner[0] == 'local_method':
            exposed_namespaces.add(namespace(owner))
        if owner and ((isinstance(target, ast.Attribute) and owner[0] in ('module', 'local_class', 'local_instance'))
                      or (isinstance(target, ast.Subscript) and owner[0] in ('module_dict', 'local_dict'))):
            member = target.attr if isinstance(target, ast.Attribute) else (
                target.slice.value if isinstance(target.slice, ast.Constant) and isinstance(target.slice.value, str) else None)
            modified.setdefault((namespace(owner), member), []).append(value)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and kind(node.func) in (('setattr',), ('delattr',)) and len(node.args) >= 2:
            if (owner := kind(node.args[0])) and owner[0] in ('module', 'local_class', 'local_instance'):
                member = node.args[1].value if isinstance(node.args[1], ast.Constant) and isinstance(node.args[1].value, str) else None
                modified.setdefault((namespace(owner), member), []).append(
                    node.args[2] if len(node.args) >= 3 else None)
        if isinstance(node, ast.Call):
            writer = kind(node.func)
            offset = writer[2] if writer and writer[0] == 'local_attribute_writer' else None
            key = ('local', id(writer[1])) if offset is not None else None
            if offset is None and _literal_attribute(node.func)[1] in ('__setattr__', '__delattr__') and node.args:
                owner = kind(node.args[0])
                if owner and owner[0] in ('local_class', 'local_instance'):
                    key, offset = namespace(owner), 1
            if offset is not None and len(node.args) > offset:
                field = node.args[offset]
                member = field.value if isinstance(field, ast.Constant) and isinstance(field.value, str) else None
                modified.setdefault((key, member), []).append(
                    node.args[offset + 1] if len(node.args) > offset + 1 else None)
    cache.clear()
    callback_parameters()
    result = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        found = kind(node.func)
        if found and found[0] in ('local_function', 'local_method'):
            function = found[1] if found[0] == 'local_function' else found[2]
            offset = int(found[3]) if found[0] == 'local_method' else 0
            arguments = local_arguments(node)
            if arguments is not None:
                params = (*function.args.posonlyargs, *function.args.args)
                positional, keywords = arguments
                known = {arg.arg for arg in (*params[offset:], *function.args.kwonlyargs)}
                unbound = [*positional[len(params) - offset:], *(value for key, value in keywords if key not in known)]
                callbacks = [kind(value) for value in unbound if _referenced_methods(kind(value))]
                if callbacks:
                    found = ('uncertain_callable', (found, *callbacks))
        result[id(node)] = found
    return result


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


def _referenced_methods(reference):
    if not reference or reference[0] == 'python_method':
        return set()
    if reference[0] == 'uncertain_callable':
        return set().union(*(_referenced_methods(value) for value in reference[1]))
    if reference == ('hom_method', 'parm', 'set'):
        return {'parm().set'}
    return {reference[-1]} if reference[0] in ('hom_method', 'unknown_method') else set()


def _raw_usage_from_tree(tree: ast.AST) -> dict:
    """Describe raw HOM syntax and gate-relevant mutations for UI/auditing.

    This is structured execution evidence, not a source-code regex.  It shares
    the same covered/suspected mutation rules as the Raw Gate so the client can
    distinguish harmless reads, blocked writes and audited exemptions.
    """
    callables = _callable_references(tree)
    parameter_writes = _parameter_write_calls(tree)
    box_writes = _network_box_mutation_calls(tree)
    note_writes = _network_note_mutation_calls(tree)
    hip_calls = _hip_file_calls(tree)
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
        if not isinstance(node, ast.Call):
            continue
        path = _call_path(node.func)
        if path is not None:
            direct[path] = direct.get(path, 0) + 1
        for attr in _referenced_methods(callables.get(id(node))):
            if attr in _RAW_HOU_VERB_MAP:
                covered[attr] = covered.get(attr, 0) + 1
            elif _mutation_method_name(attr):
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
    """Known Python loader references cannot hide a second program from the AST.

    This is lexical admission, not a Python sandbox or an import interceptor.
    Reject the builtin reference itself, before containers, returned callables or
    conditions can obscure its eventual invocation. Ordinary compile() remains
    available for authoring callback/source text.
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

        def visit_Name(self, node):
            if isinstance(node.ctx, ast.Load):
                self.blocked |= 'loader' in self.name(node.id)

        def visit_Attribute(self, node):
            if isinstance(node.ctx, ast.Load):
                self.blocked |= 'loader' in self.kind(node)
            self.generic_visit(node)

        visit_Subscript = visit_Attribute

        def bind(self, target, value):
            prepared = []
            def collect(item, initial):
                if isinstance(item, ast.Name):
                    # Loader references have already been rejected while reading
                    # the RHS; only module aliases need propagation afterward.
                    found = self.kind(initial) if isinstance(initial, ast.AST) else initial
                    prepared.append((item.id, found - loader))
                elif isinstance(item, (ast.Tuple, ast.List)):
                    values = initial.elts if isinstance(initial, (ast.Tuple, ast.List)) and len(item.elts) == len(initial.elts) else [other] * len(item.elts)
                    for child, value in zip(item.elts, values):
                        collect(child, value)
            collect(target, value)
            # Tuple RHS names resolve before any target is rebound.
            for name, found in prepared:
                self.values[name] = self.name(name) | found if self.conditional else found

        def visit_Call(self, node):
            # Literal getattr(builtins, 'exec') obtains the same forbidden
            # reference even when its result is passed through another object.
            self.blocked |= 'loader' in self.kind(node)
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
                    self.blocked |= node.module == 'builtins' and item.name in ('exec', 'eval')
                    self.bind(ast.Name(id=item.asname or item.name), other)

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
        return ('Dynamic exec/eval references hide executable source from Raw Gate and read-only analysis. '
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
            "possibly scene-mutating raw call(s) with unresolved method origin and no direct verb: "
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
            "allow_raw=\"<source and why no verb fits>\" — a one-time exemption recorded "
            "in the trace. For an inspected local Python helper, name its source and "
            "confirm that it only composes verbs or does not call raw HOM; do not rewrite "
            "ordinary builder code merely to evade source analysis."
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
