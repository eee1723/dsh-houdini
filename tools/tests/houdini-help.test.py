"""Exact SideFX help reader contracts, using synthetic pages, never vendor text."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import warnings
import zipfile

WORKER = Path(__file__).resolve().parents[1] / "houdini-help.py"
spec = importlib.util.spec_from_file_location("houdini_help_worker", WORKER)
reader = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reader)


class HelpTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="dsh-help-")
        self.addCleanup(self.temporary.cleanup)
        self.hfs = Path(self.temporary.name)
        self.help = self.hfs / "houdini/help"
        self.help.mkdir(parents=True)
        self.text = "= Synthetic node =\nUnicode:中文😀\n" + "0123456789\n" * 120
        self.archive(self.text)

    def archive(self, text):
        with zipfile.ZipFile(self.help / "hom.zip", "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("hou/Node.txt", text)

    def read(self, **changes):
        return reader.read_help({"hfs": str(self.hfs), "version": "21.0.440", "ref": "hom/hou/Node", **changes})

    def test_exact_page_and_bounded_pages_round_trip(self):
        value = self.read(limit=17)
        self.assertEqual(value["text"], self.text[:17])
        self.assertEqual(value["source"]["member"], "hou/Node.txt")
        self.assertEqual(value["source"]["houdini_version"], "21.0.440")
        combined = value["text"]
        while value["next"]:
            next_page = value["next"]
            self.assertEqual(next_page["houdini_installation"], str(self.hfs))
            value = self.read(ref=next_page["ref"], offset=next_page["offset"], limit=next_page["limit"],
                              expected_sha256=next_page["expected_sha256"])
            combined += value["text"]
        self.assertEqual(combined, self.text)
        self.assertEqual(self.read(ref="hom/hou/Node.txt")["reference"], "hom/hou/Node")

    def test_changed_source_refuses_followup(self):
        first = self.read(limit=10)
        self.archive(self.text + "changed")
        with self.assertRaisesRegex(ValueError, "changed"):
            self.read(offset=10, expected_sha256=first["source"]["sha256"])

    def test_no_arbitrary_path_or_web_reader(self):
        for ref in ["../secret", "hom/../secret", "hom//hou/Node", "hom/./hou/Node",
                    "hom\\hou\\Node", "hom/%2e%2e/secret", "/hom/hou/Node", "C:/secret",
                    "https://www.sidefx.com/docs/houdini/hom/hou/Node.html", "other/hou/Node"]:
            with self.subTest(ref=ref), self.assertRaises(ValueError): self.read(ref=ref)
        with self.assertRaisesRegex(ValueError, "not found"): self.read(ref="hom/hou/Missing")
        with self.assertRaises(FileNotFoundError): self.read(ref="vex/functions/noise")

    def test_strict_ranges_and_page_identity(self):
        for changes in [{"offset": True}, {"offset": -1}, {"offset": 1.5}, {"limit": 0},
                        {"limit": 16001}, {"limit": True}, {"expected_sha256": "BAD"},
                        {"version": "22"}, {"hfs": "relative"}, {"extra": "unsupported"}]:
            with self.subTest(changes=changes), self.assertRaises(ValueError): self.read(**changes)
        with self.assertRaisesRegex(ValueError, "beyond"): self.read(offset=len(self.text) + 1)

    def test_oversized_and_duplicate_pages_are_not_silently_read(self):
        self.archive("x" * (reader.MAX_PAGE_BYTES + 1))
        with self.assertRaisesRegex(ValueError, "budget"): self.read()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            with zipfile.ZipFile(self.help / "hom.zip", "w") as archive:
                archive.writestr("hou/Node.txt", "one")
                archive.writestr("hou/Node.txt", "two")
        with self.assertRaisesRegex(ValueError, "duplicate"): self.read()

    def test_cli_returns_json_and_does_not_import_hom(self):
        response = subprocess.run([sys.executable, "-I", "-S", "-B", "-X", "utf8", str(WORKER)],
            input=json.dumps({"hfs": str(self.hfs), "version": "21.0.440", "ref": "hom/hou/Node"}),
            capture_output=True, text=True, encoding="utf-8", check=True)
        self.assertEqual(json.loads(response.stdout)["result"]["text"], self.text)
        self.assertEqual(response.stderr, "")
        self.assertNotIn("hou", sys.modules)


if __name__ == "__main__": unittest.main()
