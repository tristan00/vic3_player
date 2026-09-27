import json
from pathlib import Path

import numpy as np

from .common import timed

SLOT = 0xffffff


class Visibility:
    @timed
    def __init__(self, path=Path(__file__).parent / 'visibility.json'):
        data = json.loads(Path(path).read_text(encoding='utf-8'))
        self.tables = data['tables']
        self.verdicts = data['metrics']

    def _verdict(self, name, scope):
        key = scope + '|' + name
        if key not in self.verdicts:
            raise RuntimeError('no visibility verdict for metric ' + key)
        return self.verdicts[key]

    def metrics(self, names, scope):
        return [name for name in names if self._verdict(name, scope) in ('ANY', 'DERIVED')]

    def player_metrics(self, names, scope):
        return [name for name in names if self._verdict(name, scope) == 'OWN']

    def _owner(self, name, snapshot, player, cache, pending=()):
        if name in cache:
            return cache[name]
        if name in pending:
            raise RuntimeError('cyclic owner chain: ' + ' -> '.join((*pending, name)))
        spec = self.tables[name]
        kind, *rest = spec['owner']
        rows = snapshot[name]
        if kind == 'all':
            owner = np.full(len(rows['id']), -1, dtype=np.int64)
        elif kind == 'self':
            owner = rows['id'].astype(np.int64) & SLOT
        elif kind == 'column':
            owner = rows[rest[0]].astype(np.int64) & SLOT
        elif kind == 'involved':
            column, table = rest
            involved = snapshot[table]
            entries = [int(key) & SLOT for key, value in zip(involved['id'], involved['value']) if int(value) & SLOT == player]
            owner = np.where(np.isin(rows['id'].astype(np.int64) & SLOT, entries), player, rows[column].astype(np.int64) & SLOT)
        elif kind == 'via':
            parent = rest[0]
            if parent not in snapshot:
                raise RuntimeError(f'{name} is owned via {parent}, which the snapshot does not contain')
            source = self._owner(parent, snapshot, player, cache, (*pending, name))
            if source is None:
                owner = None
            else:
                lookup = dict(zip((snapshot[parent]['id'].astype(np.int64) & SLOT).tolist(), source.tolist()))
                owner = np.array([lookup.get(int(key) & SLOT, -2) for key in rows['id']], dtype=np.int64)
        elif kind == 'through':
            parent, column = rest
            source = self._owner(parent, snapshot, player, cache, (*pending, name))
            if source is None:
                owner = None
            else:
                lookup = dict(zip((snapshot[parent]['id'].astype(np.int64) & SLOT).tolist(), source.tolist()))
                owner = np.array([lookup.get(int(key) & SLOT, -2) for key in rows[column]], dtype=np.int64)
        else:
            owner = None
        cache[name] = owner
        return owner

    def _keep(self, name, snapshot, player, cache):
        spec = self.tables[name]
        if spec['owner'][0] == 'either':
            rows = snapshot[name]
            first, second = spec['owner'][1:]
            return ((rows[first].astype(np.int64) & SLOT) == player) | ((rows[second].astype(np.int64) & SLOT) == player)
        owner = self._owner(name, snapshot, player, cache)
        if owner is None:
            raise RuntimeError(f'{name} has no resolvable owner')
        return np.full(len(owner), True) if spec['owner'][0] == 'all' else owner == player

    @timed
    def apply(self, snapshot, player):
        unknown = sorted(set(snapshot) - set(self.tables))
        if unknown:
            raise RuntimeError('no visibility verdict for ' + ', '.join(unknown))
        cache = {}
        result = {}
        for name, rows in snapshot.items():
            spec = self.tables[name]
            disposition = spec['disposition']
            if disposition == 'drop':
                continue
            drop = set(spec.get('drop', ()))
            private = set(spec.get('private', ()))
            if disposition == 'public':
                result[name] = {c: v for c, v in rows.items() if c not in drop}
                continue
            keep = self._keep(name, snapshot, player, cache)
            if disposition == 'player':
                result[name] = {c: v[keep] for c, v in rows.items() if c not in drop}
                continue
            result[name] = {c: v for c, v in rows.items() if c not in drop | private}
            result[name + '_private'] = {c: v[keep] for c, v in rows.items()
                                         if c == 'id' or c in private}
        return result
