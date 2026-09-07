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
    return {k: card[k] for k in ('id', 'source', 'node_types', 'tested_versions', 'decisions') if k in card}


def operation_parameters(card, parameters):
    """Critical runtime templates stay visible even with an unrelated filter."""
    by_name = {p['name']: p for p in parameters}
    names = card.get('critical_parameters', [])
    return ([by_name[n] for n in names if n in by_name],
            [n for n in names if n not in by_name])


def decision_advisories(card, values):
    """Presence-only advice. No intent inference, VEX parsing, cook or writes.

    Explicit empty groups/open ends/native types remain legal. Specifying a
    field (including an expression) is not evidence of correct geometry.
    """
    return [{'id': d['id'], 'alternatives': [list(option) for option in d['any_of']],
             'missing': [[name for name in option if name not in values] for option in d['any_of']],
             'guidance': d['guidance']}
            for d in card.get('decisions', [])
            if not any(all(name in values for name in option) for option in d['any_of'])]
