"""Request-local public verb dispatch and the data-only query input contract.

No HOM or scene access. Outside an admitted request the facade retains its
trusted Python-shell behavior; this is not an arbitrary Python sandbox.
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
import math


_DISPATCH = ContextVar('dsh_houdini_verb_dispatch', default=None)


@contextmanager
def request_dispatch(dispatch):
    token = _DISPATCH.set(dispatch)
    try:
        yield
    finally:
        _DISPATCH.reset(token)


def implementation(function):
    return getattr(function, '__dsh_verb_implementation__', function)


def public_verb(name, function):
    """A stable facade callable: aliases use whichever request is current."""
    function = implementation(function)

    @wraps(function)
    def invoke(*args, **kwargs):
        dispatch = _DISPATCH.get()
        if dispatch is None:
            return function(*args, **kwargs)
        return dispatch(name, args, kwargs)

    invoke.__dsh_verb_implementation__ = function
    return invoke


def validate_structured_queries(queries):
    """Validate every row before admission; return detached JSON-shaped data.

    A verb name is deliberately not resolved here. Unknown/read-disallowed
    names are per-row rejections at execution, rather than partial admission
    of a malformed batch. No values are evaluated as Python or expressions.
    """
    if type(queries) is not list or not 1 <= len(queries) <= 16:
        raise ValueError('queries must be a list containing 1..16 query objects')
    active = set()
    remaining = 16384

    def json_value(value, depth=0):
        nonlocal remaining
        remaining -= 1
        if remaining < 0 or depth > 32:
            raise ValueError('query arguments exceed the supported JSON size or nesting limit')
        if value is None or type(value) in (str, bool, int):
            return value
        if type(value) is float and math.isfinite(value):
            return value
        if type(value) not in (list, dict):
            raise ValueError('query arguments must contain only finite JSON values')
        identity = id(value)
        if identity in active:
            raise ValueError('query arguments cannot contain recursive containers')
        active.add(identity)
        try:
            if type(value) is list:
                return [json_value(item, depth + 1) for item in value]
            if any(type(key) is not str for key in value):
                raise ValueError('query object keys must be strings')
            return {key: json_value(item, depth + 1) for key, item in value.items()}
        finally:
            active.remove(identity)

    normalized = []
    for index, row in enumerate(queries):
        if type(row) is not dict or set(row) - {'verb', 'id', 'args', 'kwargs'}:
            raise ValueError(f'queries[{index}] accepts only verb, id, args and kwargs')
        if type(row.get('verb')) is not str or not row['verb']:
            raise ValueError(f'queries[{index}].verb must be a nonempty string')
        if 'id' in row and type(row['id']) is not str:
            raise ValueError(f'queries[{index}].id must be a string')
        args, kwargs = row.get('args', []), row.get('kwargs', {})
        if type(args) is not list or type(kwargs) is not dict:
            raise ValueError(f'queries[{index}].args must be a list and kwargs must be an object')
        normalized.append({'verb': row['verb'], **({'id': row['id']} if 'id' in row else {}),
                           'args': json_value(args), 'kwargs': json_value(kwargs)})
    return normalized
