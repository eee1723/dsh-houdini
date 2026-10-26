"""Notify an already-loaded Bridge and preserve the next native save script."""
from dsh_workbench_entry import after_save
import hou
after_save(globals(), hou.findFile('scripts/afterscenesave.py'))
