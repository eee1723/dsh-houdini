"""Offline replay adapter; shared observation logic lives on the Houdini side."""
from pathlib import Path
import sys
import hou
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'houdini/python3.11libs'))
from dsh_delivery import DeliveryAudit as _CoreAudit

class DeliveryAudit(_CoreAudit):
    def __init__(self, contract):
        if hou.isUIAvailable():
            raise RuntimeError('offline prototype only; use disposable hython')
        super().__init__(contract,restricted=False)
