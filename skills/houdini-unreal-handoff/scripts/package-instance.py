"""Run with isolated hython on a trusted standalone SOP HDA, not in a live scene."""
import argparse
import json
import shutil
import struct
from collections import defaultdict
from pathlib import Path
from urllib.parse import unquote, urlsplit

import hou


def inspect_outputs(instance):
    outputs = []
    nodes = [node for node in instance.children() if node.type().name() == "output"]
    for node in sorted(nodes, key=lambda item: item.evalParm("outputidx")) or [instance]:
        geometry = node.geometry()
        if geometry is None or node.errors():
            raise ValueError(f"Output failed: {node.path()} {node.errors()}")
        references = defaultdict(set)
        seen = set()

        def inspect(geo):
            for attr in (*geo.pointAttribs(), *geo.primAttribs(), *geo.globalAttribs()):
                if attr.name() in ("unreal_material", "unreal_material_instance", "unreal_instance") and attr.dataType() == hou.attribData.String:
                    readers = {hou.attribType.Point: geo.pointStringAttribValues,
                               hou.attribType.Prim: geo.primStringAttribValues}
                    values = readers[attr.type()](attr.name()) if attr.type() in readers else [geo.attribValue(attr)]
                    references[attr.name()].update(filter(None, values))
            for packed in geo.iterPrimsOfType(hou.primType.PackedGeometry):
                identity = packed.intrinsicValue("geometryid")
                if identity not in seen:
                    seen.add(identity)
                    inspect(packed.getEmbeddedGeometry())

        inspect(geometry)
        outputs.append({"node": instance.relativePathTo(node), "points": geometry.pointCount(),
                        "primitives": geometry.primCount(), "ue": {key: sorted(values) for key, values in references.items()}})
    return outputs


def collect(instance, library):
    root = library.parent
    factory = Path(hou.getenv("HFS")).resolve()
    sources = defaultdict(set)
    external = defaultdict(set)
    problems = []

    def include(file, owner):
        if not file.is_absolute():
            file = Path(hou.text.expandString("$HIP")) / file
        file = file.resolve()
        if file.is_relative_to(factory):
            return
        if not file.is_relative_to(root) or not file.is_file():
            problems.append({"reference": str(file), "owner": owner})
            return
        name = file.relative_to(root).as_posix()
        fresh = name not in sources
        sources[name].add(owner)
        if fresh and file.suffix.lower() in (".gltf", ".glb"):
            if file.suffix.lower() == ".gltf":
                document = json.loads(file.read_text(encoding="utf-8-sig"))
            else:
                with file.open("rb") as stream:
                    magic, version, size, length, kind = struct.unpack("<4sIII4s", stream.read(20))
                    if (magic, version, kind) != (b"glTF", 2, b"JSON") or length > size - 20:
                        raise ValueError(f"invalid GLB header: {name}")
                    document = json.loads(stream.read(length))
            for entry in document.get("buffers", []) + document.get("images", []):
                uri = entry.get("uri")
                if uri and not uri.startswith("data:"):
                    parsed = urlsplit(uri)
                    if parsed.scheme or parsed.netloc:
                        problems.append({"reference": uri, "owner": name})
                    else:
                        include(file.parent / unquote(parsed.path), name)

    children = instance.allSubChildren(sync_delayed_definition=True)
    for child in children:
        definition = child.type().definition()
        if definition and Path(definition.libraryFilePath()).resolve() != library:
            include(Path(definition.libraryFilePath()), instance.relativePathTo(child))
    for parm, raw in hou.fileReferences():
        if not parm or not parm.path().startswith(instance.path() + "/"):
            continue
        owner = parm.path()[len(instance.path()) + 1:]
        value = parm.evalAsString()
        if not value:
            continue
        if value.startswith("op:"):
            target = parm.node().node(value[3:])
            if target and (target == instance or target.path().startswith(instance.path() + "/")):
                continue
            problems.append({"reference": value, "owner": owner})
            continue
        if value.startswith("opdef:"):
            typename, _, section = value.removeprefix("opdef:").partition("?")
            node_type = parm.node().type() if typename == "." else hou.nodeType(typename.lstrip("/"))
            definition = node_type.definition() if node_type else None
            if not definition or section not in definition.sections():
                problems.append({"reference": value, "owner": owner})
            elif Path(definition.libraryFilePath()).resolve() != library:
                include(Path(definition.libraryFilePath()), owner)
            continue
        if parm.node().type().name() == "font" and parm.name() == "file" and not (Path(value).is_absolute() and Path(value).resolve().is_relative_to(root)):
            external[value].add(owner)
        else:
            include(Path(value), owner)
    return {"files": sorted(sources), "fileConsumers": {key: sorted(values) for key, values in sources.items()},
            "hostFonts": {key: sorted(values) for key, values in external.items()}, "unresolved": problems}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("library", type=Path)
    parser.add_argument("destination", type=Path, help="new directory; never overwritten")
    parser.add_argument("--type", help="required if the library has multiple SOP definitions")
    parser.add_argument("--values", type=json.loads, help="JSON object of scalar public parameter overrides")
    parser.add_argument("--verify", action="store_true", help="recook the relocated library; compare its generated manifest")
    args = parser.parse_args()
    library = args.library.resolve(strict=True)
    dest = args.destination.resolve()
    expected = json.loads((library.parent / "delivery.json").read_text(encoding="utf-8")) if args.verify else None
    if expected:
        args.type = expected["type"]
        args.values = expected.get("parameters")
    if not args.verify and dest.is_relative_to(library.parent):
        parser.error("destination must be outside the source package")
    definitions = [definition for definition in hou.hda.definitionsInFile(str(library))
                   if definition.nodeTypeCategory() == hou.sopNodeTypeCategory()
                   and (not args.type or definition.nodeTypeName() == args.type)]
    if len(definitions) != 1:
        parser.error("select exactly one SOP definition with --type")
    if hou.node("/obj").children():
        parser.error("use a fresh hython process")
    hou.hda.installFile(str(library), force_use_assets=True)
    instance = hou.node("/obj").createNode("geo", run_init_scripts=False).createNode(definitions[0].nodeTypeName(), exact_type_name=True)
    if Path(instance.type().definition().libraryFilePath()).resolve() != library:
        raise ValueError("instance did not resolve to selected definition")
    if args.values:
        instance.setParms(args.values)
    report = collect(instance, library)
    report.update(schemaVersion=1, hda=library.name, type=instance.type().name(), houdini=hou.applicationVersionString(),
                  frame=hou.frame(), outputs=inspect_outputs(instance))
    if args.values:
        report["parameters"] = args.values
    if args.verify:
        if report["unresolved"] or report != expected:
            raise ValueError("relocation changed dependencies, outputs or definition")
        dest.mkdir(parents=True, exist_ok=False)
        (dest / "relocation.json").write_text(json.dumps({"ok": True, "files": len(report["files"]),
            "type": report["type"], "scope": "sampled instance and frame"}), encoding="utf-8")
        return
    dest.mkdir(parents=True, exist_ok=False)
    if report["unresolved"]:
        (dest / "unresolved.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        raise ValueError("unresolved dependencies; no delivery created")
    for name in [library.name, *report["files"]]:
        target = dest / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(library.parent / name, target)
    (dest / "delivery.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
