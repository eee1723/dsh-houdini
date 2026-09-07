"""One packaged source for small, version-sensitive node operation notes."""
import json
from pathlib import Path
from functools import lru_cache

@lru_cache(maxsize=1)
def _cards():
    return json.loads((Path(__file__).resolve().parent.parent / 'node-operation-contracts.json').read_text(encoding='utf8'))

def operation_card(type_name):
    card = _cards()['cards'].get(type_name.split('::')[0])
    return dict(card) if card else None
