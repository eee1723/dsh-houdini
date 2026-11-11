"""Verified saved-item mappings for Network Boxes and Sticky Notes.

H21/H22 editor items have no userData. Parent metadata carries only tokens;
the trusted external checkpoint and a fresh-load native identity prove lineage.
Each domain still owns its own live mutation registry.
"""
from __future__ import annotations

import json
import re
import uuid

import hou


class EditorCheckpoints:
    def __init__(self, kind, marker, collection, service):
        self.kind, self.marker, self.collection, self.service = kind, marker, collection, service

    def key(self, item):
        return (self.kind, int(item.parent().sessionId()), int(item.sessionId()))

    def tokens(self, parent):
        try:
            value = json.loads(parent.userData(self.marker) or '{}')
        except (ValueError, TypeError):
            return {}
        return {name: token for name, token in value.items()
                if isinstance(name, str) and isinstance(token, str) and re.fullmatch('[0-9a-f]{32}', token)} if isinstance(value, dict) else {}

    def _present(self, item):
        candidate = item.parent().item(item.name())
        return candidate == item and int(candidate.sessionId()) == int(item.sessionId())

    def _definition_owned(self, parent):
        return parent.isLockedHDA() or (parent.isInsideLockedHDA() and not parent.isEditableInsideLockedHDA())

    def capture(self, parents):
        """Observe saved token locations exactly once when the HIP has loaded."""
        baseline = {}
        for parent in parents:
            if not parent.isNetwork():
                continue
            tokens = self.tokens(parent)
            if not tokens:
                continue
            for item in getattr(parent, self.collection)():
                token = tokens.get(item.name())
                if token:
                    baseline[self.key(item)] = {'native_object': item, 'marker_name': item.name(),
                        'signature': (token, parent.type().category().name(), parent.type().name())}
        return baseline

    def mapping(self, rows, baseline, owner=None):
        origins = {}
        for key, observed in baseline.items():
            origins.setdefault(observed['signature'], []).append((key, observed))
        mapping, missing = [], []
        for row in rows:
            if owner is not None and row['owner']['session'] != owner:
                continue
            signature = (row['item_id'], row['parent_category'], row['parent_type'])
            candidates = origins.get(signature, [])
            item = None
            if len(candidates) == 1:
                key, observed = candidates[0]
                candidate = observed['native_object']
                try:
                    parent = candidate.parent()
                    if (self.key(candidate) == key
                            and self.tokens(parent).get(observed['marker_name']) == row['item_id']
                            and parent.type().category().name() == row['parent_category']
                            and parent.type().name() == row['parent_type'] and not self._definition_owned(parent)
                            and self._present(candidate)):
                        item = candidate
                except hou.Error:
                    pass
            if item is None:
                missing.append({'path': row['path'], 'reason': 'original_' + self.kind + '_missing_or_changed'})
            else:
                mapping.append((item, row))
        return mapping, missing

    def prepare(self, rows, baseline, registry, executor):
        """Rotate only independently known originals, preserving inactive authors."""
        inherited = {self.key(item): (item, row) for item, row in self.mapping(rows, baseline)[0]}
        known = dict(inherited)
        for key, entry in registry.items():
            item = entry['native_object']
            try:
                if self.key(item) == key and self._present(item):
                    known[key] = (item, inherited.get(key, (None, None))[1])
            except hou.Error:
                continue
        groups = {}
        for key, (item, prior) in known.items():
            parent = item.parent()
            if self.service(item) or self._definition_owned(parent):
                continue
            entry = registry.get(key)
            if entry is not None and entry['native_object'] != item:
                entry = None
            owner = {k: v for k, v in entry.items() if k != 'native_object'} if entry else prior['owner']
            source = prior.get('source_executor', executor) if prior and prior['owner'] == owner else executor
            row = {'item_id': uuid.uuid4().hex, 'name': item.name(), 'path': item.path(),
                   'parent_path': parent.path(), 'parent_category': parent.type().category().name(),
                   'parent_type': parent.type().name(), 'owner': dict(owner), 'source_executor': source}
            groups.setdefault(key[1], (parent, []))[1].append((item, row))
        saved, observed = [], {}
        for parent, entries in groups.values():
            try:
                parent.setUserData(self.marker, json.dumps({row['name']: row['item_id'] for _, row in entries}, separators=(',', ':')))
            except hou.Error:
                continue  # Definition-owned items remain unverified after reopening.
            for item, row in entries:
                saved.append(row)
                observed[self.key(item)] = {'native_object': item, 'marker_name': row['name'],
                    'signature': (row['item_id'], row['parent_category'], row['parent_type'])}
        return saved, observed

    def restore(self, mapping, session, registry):
        """Revalidate prepared native objects before committing domain ownership."""
        checked = []
        for item, row in mapping:
            try:
                parent = item.parent()
                entry = registry.get(self.key(item))
                owner = {k: v for k, v in entry.items() if k != 'native_object'} if entry else None
                if (row['owner']['session'] != session
                        or self.tokens(parent).get(row['name']) != row['item_id']
                        or parent.type().category().name() != row['parent_category']
                        or parent.type().name() != row['parent_type'] or self.service(item) or self._definition_owned(parent)
                        or (entry is not None and entry['native_object'] != item)
                        or (owner is not None and owner != row['owner']) or not self._present(item)):
                    raise RuntimeError('Checkpoint ' + self.kind + ' changed before ownership activation')
                checked.append((self.key(item), {**row['owner'], 'native_object': item}))
            except hou.Error as error:
                raise RuntimeError('Checkpoint ' + self.kind + ' changed before ownership activation') from error
        registry.update(checked)
