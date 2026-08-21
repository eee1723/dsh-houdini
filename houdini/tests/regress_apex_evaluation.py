"""H21/H22 headless smoke for a real, non-interactive APEX graph evaluation.

The fixture is SideFX's version-matched example HDA under ``$HFS/houdini/help``.
It proves the installed APEX Graph -> APEX Invoke Graph data contract without
automating the Animate state, authoring a private graph recipe, or touching a
user HIP file.

Run:
    D:/houdini/bin/hython.exe houdini/tests/regress_apex_evaluation.py
    D:/Houdini22/bin/hython.exe houdini/tests/regress_apex_evaluation.py
"""

from __future__ import annotations

import os

import hou


failures: list[str] = []


def check(label, fn):
    try:
        fn()
        print(f"PASS  {label}")
    except Exception as exc:
        failures.append(label)
        print(f"FAIL  {label}: {type(exc).__name__}: {exc}")


def sidefx_example_hda() -> str:
    hfs = hou.text.expandString("$HFS")
    candidates = [
        os.path.join(
            hfs, "houdini", "help", "examples", "nodes", "sop",
            "apex--graph", "APEXGraphExamples.hda",
        ),
        os.path.join(
            hfs, "houdini", "help", "examples", "nodes", "sop",
            "apex--editgraph", "APEXGraphExamples.hda",
        ),
    ]
    found = next((path for path in candidates if os.path.isfile(path)), None)
    if found is None:
        raise AssertionError(f"SideFX APEX example HDA not found under {hfs}")
    return found


example_hda = sidefx_example_hda()
example = None


try:
    def type_discovery():
        types = hou.sopNodeTypeCategory().nodeTypes()
        assert "apex::graph" in types
        assert "apex::invokegraph" in types
        assert types["apex::invokegraph"].minNumInputs() == 1


    check("APEX Graph and Invoke Graph types are installed", type_discovery)

    def install_official_fixture():
        global example
        definitions = hou.hda.definitionsInFile(example_hda)
        assert len(definitions) == 1
        assert definitions[0].nodeTypeName() == "APEXGraphExamples"
        assert definitions[0].nodeTypeCategory().name() == "Object"
        hou.hda.installFile(example_hda)
        old = hou.node("/obj/__dsh_apex_regression__")
        if old is not None:
            old.destroy()
        example = hou.node("/obj").createNode(
            "APEXGraphExamples", "__dsh_apex_regression__",
        )
        assert example is not None


    check("version-matched SideFX APEX fixture installs", install_official_fixture)

    def evaluate_node():
        assert example is not None
        node = example.node("add_two_values/evaluate_graph")
        graph = example.node("add_two_values/add_operation_graph_logic")
        inputs = example.node("add_two_values/define_inputs")
        assert node is not None and graph is not None and inputs is not None
        assert node.type().name() == "apex::invokegraph"
        assert graph.type().name() == "apex::graph"
        assert node.inputs()[0] == graph
        assert node.inputs()[1] == inputs
        node.cook(force=True)
        assert not node.errors(), node.errors()
        assert not node.warnings(), node.warnings()
        result = node.geometry().attribValue("output_parms")
        assert isinstance(result, dict), result
        assert abs(float(result["result"]) - 5.5) < 1e-8, result


    check("official APEX graph evaluates 2 + 3.5 to detail dict 5.5", evaluate_node)

    def reevaluate_changed_inputs():
        assert example is not None
        inputs = example.node("add_two_values/define_inputs")
        node = example.node("add_two_values/evaluate_graph")
        assert inputs is not None and node is not None
        inputs.parm("valf1").set(10.0)
        inputs.parm("valf2").set(-4.0)
        node.cook(force=True)
        result = node.geometry().attribValue("output_parms")
        assert abs(float(result["result"]) - 6.0) < 1e-8, result


    check("APEX evaluation reacts to changed dictionary inputs", reevaluate_changed_inputs)

    def error_contract():
        container = hou.node("/obj").createNode("geo", "__dsh_apex_error__")
        try:
            for child in list(container.children()):
                child.destroy()
            invoke = container.createNode("apex::invokegraph", "missing_graph")
            menu = invoke.parm("errorhandlingmode").parmTemplate()
            assert list(menu.menuItems()) == ["ignore", "warn", "abort"]
            try:
                invoke.cook(force=True)
            except hou.OperationFailed:
                pass
            else:
                raise AssertionError("missing graph input did not abort the cook")
            assert any("Not enough sources" in message for message in invoke.errors()), invoke.errors()
        finally:
            container.destroy()


    check("missing APEX graph reports a readable cook error", error_contract)
finally:
    if example is not None:
        example.destroy()
    try:
        hou.hda.uninstallFile(example_hda)
    except hou.Error:
        pass


if failures:
    raise SystemExit("APEX evaluation regression failures: " + ", ".join(failures))

print(
    "ALL APEX EVALUATION REGRESSIONS PASSED "
    f"({hou.applicationVersionString()}; {example_hda})"
)
