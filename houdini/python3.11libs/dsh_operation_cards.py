"""One packaged source for small, version-sensitive node operation notes."""
import json
from copy import deepcopy
from pathlib import Path
from functools import lru_cache

@lru_cache(maxsize=1)
def _cards():
    return json.loads((Path(__file__).resolve().parent.parent / 'node-operation-contracts.json').read_text(encoding='utf8'))

def operation_card(type_name):
    card = _cards()['cards'].get(type_name.split('::')[0])
    if not card or ('node_types' in card and type_name not in card['node_types']):
        return None
    return deepcopy(card)


def operation_metadata(card):
    """No cached HOM state: tested versions describe evidence, not live defaults."""
    return {k: card[k] for k in ('id', 'source', 'node_types', 'tested_versions', 'decisions',
                                 'always_advisories') if k in card}


def operation_parameters(card, parameters):
    """Critical runtime templates stay visible even with an unrelated filter."""
    by_name = {p['name']: p for p in parameters}
    names = card.get('critical_parameters', [])
    return ([by_name[n] for n in names if n in by_name],
            [n for n in names if n not in by_name])
