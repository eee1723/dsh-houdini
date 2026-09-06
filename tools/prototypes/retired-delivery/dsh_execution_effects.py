"""RETIRED v8 reference. Conservative numerical-evidence certificate.

Not a Python sandbox or a mutation gate. Unknown syntax/calls simply invalidate
cached delivery evidence. A successful certificate STILL requires fresh binding,
graph, parameter and final-geometry equality before Host reuse.
"""
import ast

# Only plain-data-returning operations with read/presentation/file-save intent.
# No creation, setters, callbacks, arbitrary HOM, cook/solver or custom ROPs.
REOBSERVE_VERBS = frozenset({
    'verb_help','node_info','find_nodes','read_parms','list_parms','scene_info',
    'sop_output_node','layout_nodes','sop_set_output','scene_save','render_view',
})
_BUILTINS = frozenset({'print','bool','len'})


def permits_numerical_reobserve(code):
    """Recognize literal calls/result packaging, not arbitrary Python programs."""
    if not isinstance(code,str) or len(code)>65536:return False
    try:tree=ast.parse(code)
    except (SyntaxError,ValueError,RecursionError):return False
    if sum(1 for _ in ast.walk(tree))>2000:return False
    reserved=REOBSERVE_VERBS|_BUILTINS|{'hou'}
    known=set()

    def target(node):
        return isinstance(node,ast.Name) and node.id not in reserved and (not node.id.startswith('__') or node.id=='__result__')

    def expr(node,names):
        if isinstance(node,ast.Constant):return type(node.value) in (str,int,float,bool,type(None))
        if isinstance(node,ast.Name):return node.id in names
        if isinstance(node,(ast.List,ast.Tuple)):return all(expr(e,names) for e in node.elts)
        if isinstance(node,ast.Dict):return all(k is not None and expr(k,names) and expr(v,names) for k,v in zip(node.keys,node.values))
        if isinstance(node,ast.Subscript):return expr(node.value,names) and expr(node.slice,names)
        if isinstance(node,ast.UnaryOp) and isinstance(node.op,(ast.USub,ast.UAdd,ast.Not)):return expr(node.operand,names)
        if isinstance(node,ast.BinOp) and isinstance(node.op,(ast.Add,ast.Sub,ast.Mult,ast.Div)):return expr(node.left,names) and expr(node.right,names)
        if isinstance(node,(ast.DictComp,ast.ListComp)):
            if len(node.generators)!=1:return False
            g=node.generators[0]
            if (not target(g.target) or g.is_async or g.ifs or not isinstance(g.iter,(ast.List,ast.Tuple))
                    or len(g.iter.elts)>32 or not all(isinstance(e,ast.Constant) for e in g.iter.elts)):return False
            local=names|{g.target.id}
            return (expr(node.key,local) and expr(node.value,local)) if isinstance(node,ast.DictComp) else expr(node.elt,local)
        if isinstance(node,ast.Call):
            if isinstance(node.func,ast.Name):safe=node.func.id in reserved-{'hou'}
            else:safe=isinstance(node.func,ast.Attribute) and node.func.attr=='get' and expr(node.func.value,names)
            return safe and all(expr(a,names) for a in node.args) and all(k.arg is not None and expr(k.value,names) for k in node.keywords)
        return False

    try:
        for statement in tree.body:
            if isinstance(statement,ast.Assign):
                if len(statement.targets)!=1 or not target(statement.targets[0]) or not expr(statement.value,known):return False
                known.add(statement.targets[0].id)
            elif isinstance(statement,ast.Expr):
                if not expr(statement.value,known):return False
            else:return False
    except RecursionError:return False
    return bool(tree.body)
