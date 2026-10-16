from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'houdini/python3.11libs'))
from dsh_workbench import ensure

config = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
desktop = ensure(config)
Path(sys.argv[2]).write_text(json.dumps({'pid': desktop['record']['pid']}), encoding='utf-8')
