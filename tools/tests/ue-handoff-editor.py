"""UE editor integration test for a disposable empty project. No editor service."""
import json
import os
import runpy
import time
import traceback
from collections import Counter
from pathlib import Path

import unreal as ue


exports = runpy.run_path(str(Path(__file__).resolve().parents[2] / "skills/houdini-unreal-handoff/scripts/ue-content-files.py"))
root = Path(os.environ["DSH_UE_CASE"]).resolve()
case = json.loads((root / "case.json").read_text(encoding="utf-8-sig"))
project = Path(ue.Paths.convert_relative_path_to_full(ue.Paths.project_dir())).resolve()
reopen = os.environ.get("DSH_UE_REOPEN") == "1"
assert project == (root / ("Reopen" if reopen else "Project")).resolve()
delivery = root / "Delivery"
manifest = json.loads((delivery / "delivery.json").read_text(encoding="utf-8"))
level = "/Game/HandoffTest/Baked"
receipt = root / ("reopen.json" if reopen else "cook.json")
assert not receipt.exists()
library = ue.EditorAssetLibrary
levels = ue.get_editor_subsystem(ue.LevelEditorSubsystem)
actors = ue.get_editor_subsystem(ue.EditorActorSubsystem)
state = {"phase": "initial"}
report = {"engine": ue.SystemLibrary.get_engine_version(), "map": level, "ok": False}
started = time.monotonic()


def snapshot():
    slots = []
    lights = []
    procedural = []
    for actor in actors.get_all_level_actors():
        if actor.get_class().get_name() == "HoudiniAssetActor":
            procedural.append(actor.get_path_name())
        for component in actor.get_components_by_class(ue.StaticMeshComponent):
            mesh = component.static_mesh
            if not mesh:
                continue
            count = component.get_instance_count() if isinstance(component, ue.InstancedStaticMeshComponent) else 1
            slot_names = component.get_material_slot_names()
            materials = component.get_materials()
            assert len(materials) == len(slot_names)
            slots.append([count, [[str(name), material.get_path_name() if material else None]
                                  for name, material in zip(slot_names, materials)]])
        for light in actor.get_components_by_class(ue.PointLightComponent):
            lights.append({"tags": sorted(str(tag) for tag in actor.tags), "lm": light.intensity,
                           "units": str(light.intensity_units), "radius": light.attenuation_radius,
                           "movable": light.mobility == ue.ComponentMobility.MOVABLE,
                           "location": [round(value, 2) for value in light.get_world_location().to_tuple()] if hasattr(light, "get_world_location") else [round(value, 2) for value in actor.get_actor_location().to_tuple()]})
    return {"slots": sorted(slots, key=str), "lights": sorted(lights, key=str), "hda": procedural}


def slot_counts(scene):
    counts = Counter()
    for count, slots in scene["slots"]:
        counts[tuple(tuple(slot) for slot in slots)] += count
    return counts




def finish(error=None):
    state["phase"] = "done"
    report.update(ok=error is None, error=error)
    receipt.write_text(json.dumps(report, indent=2), encoding="utf-8")
    ue.EditorPythonScripting.set_keep_python_script_alive(False)
    ue.SystemLibrary.quit_editor()


def verify_lights(scene, expected):
    assert len(scene["lights"]) == expected["count"], scene["lights"]
    gate = [light for light in scene["lights"] if case["group"] in light["tags"]]
    assert len(gate) == expected["groupCount"]
    assert all(light["movable"] and "LUMENS" in light["units"] and
               abs(light["lm"] - expected["lm"]) < .01 and
               abs(light["radius"] - expected["radius"]) < .01 for light in gate), gate


def processed(wrapper):
    try:
        phase = state["phase"]
        if phase not in ("initial", "variant"):
            return
        scene = report[phase] = snapshot()
        verify_lights(scene, case[phase])
        assigned = {material for count, slots in scene["slots"] for name, material in slots}
        assert scene["slots"] and None not in assigned
        expected = {ref for output in manifest["outputs"] for ref in output["ue"].get("unreal_material", [])}
        assert not expected - assigned, sorted(expected - assigned)
        if phase == "variant":
            assert slot_counts(scene) == slot_counts(report["initial"]), "slot names, bindings or placements changed"
        state["phase"] = "change" if phase == "initial" else "bake"
    except Exception:
        finish(traceback.format_exc())


def baked(wrapper, success):
    state["phase"] = "remove" if success else "failed"


def tick(delta):
    try:
        phase = state["phase"]
        if phase == "done":
            return
        if time.monotonic() - started > 1200:
            raise TimeoutError(phase)
        wrapper = state["wrapper"]
        if phase == "change":
            state["phase"] = "variant"
            parameters = {key: ue.HoudiniParameterTuple(**{("int32_values" if type(value) is int else "float_values"): [value]})
                          for key, value in case["parameters"].items()}
            assert wrapper.set_parameter_tuples(parameters)
            wrapper.recook()
        elif phase == "bake":
            state["phase"] = "baking"
            wrapper.set_bake_folder(ue.DirectoryPath("/Game/HandoffTest/Meshes"))
            assert wrapper.bake_all_outputs_with_settings(ue.HoudiniEngineBakeOption.TO_ACTOR, False, False)
        elif phase == "remove":
            state["phase"] = "save"
            wrapper.delete_instantiated_asset()
        elif phase == "save":
            scene = report["baked"] = snapshot()
            assert not scene["hda"]
            assert slot_counts(scene) == slot_counts(report["variant"]), "bake changed slot bindings"
            assert scene["lights"] == report["variant"]["lights"], "bake changed light properties"
            world = ue.get_editor_subsystem(ue.UnrealEditorSubsystem).get_editor_world()
            assert ue.EditorLoadingAndSavingUtils.save_map(world, level)
            ue.EditorLoadingAndSavingUtils.save_dirty_packages(True, True)
            bindings = {material.split(".")[0] for count, slots in scene["slots"] for name, material in slots}
            report["bakeDependencies"] = exports["export_dependencies"]([level, *bindings], root / "BakedProjectContent")
            finish()
        elif phase == "failed":
            raise ValueError("bake failed")
    except Exception:
        finish(traceback.format_exc())


try:
    ue.EditorPythonScripting.set_keep_python_script_alive(True)
    if reopen:
        assert not hasattr(ue, "HoudiniPublicAPI"), "reopen must disable Houdini Engine"
        assert levels.load_level(level)
        reopened = report["reopened"] = snapshot()
        previous = json.loads((root / "cook.json").read_text(encoding="utf-8"))
        assert previous["ok"] and not reopened["hda"]
        assert reopened["lights"] == previous["baked"]["lights"]
        assert slot_counts(reopened) == slot_counts(previous["baked"])
        finish()
    else:
        assert not library.does_asset_exist(level) and levels.new_level(level)
        report["receiverDependencies"] = exports["export_for_delivery"](delivery / "delivery.json", root / "ReceiverContent")
        api = ue.HoudiniPublicAPIBlueprintLib.get_api()
        if not api.is_session_valid():
            api.create_session()
        assert api.is_session_valid()
        task = ue.AssetImportTask()
        task.filename = str(delivery / manifest["hda"])
        task.destination_path = "/Game/HandoffTest/Source"
        task.automated = task.save = True
        ue.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
        asset = library.load_asset(task.imported_object_paths[0])
        wrapper = api.instantiate_asset(asset, ue.Transform())
        assert not wrapper.is_proxy_mesh_enabled(), "fixture requires final meshes (bEnableProxyStaticMesh=False)"
        state.update(wrapper=wrapper, api=api, asset=asset)
        wrapper.on_post_processing_delegate.add_callable(processed)
        wrapper.on_post_bake_delegate.add_callable(baked)
        state["tick"] = ue.register_slate_post_tick_callback(tick)
except Exception:
    finish(traceback.format_exc())
