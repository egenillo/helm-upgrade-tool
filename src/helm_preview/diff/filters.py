"""Noise filtering and normalization for YAML resource bodies."""

from __future__ import annotations

import copy
import fnmatch
import re

from helm_preview.config import NOISE_PATHS, UNORDERED_LIST_SORT_KEYS


def strip_noise(body: dict, extra_ignores: list[str] | None = None) -> dict:
    """Deep-copy body and remove all paths matching NOISE_PATHS + extra_ignores.

    Supports glob patterns on leaf keys (e.g. annotations.prefix/*).
    Dot-paths use backslash-escaped dots for literal dots in keys.
    """
    result = copy.deepcopy(body)
    all_paths = NOISE_PATHS | set(extra_ignores or [])
    for path in all_paths:
        _remove_path(result, path)
    return result


def _split_dot_path(path: str) -> list[str]:
    """Split a dot-path respecting escaped dots.

    e.g. 'metadata.annotations.meta\\.helm\\.sh/*' ->
         ['metadata', 'annotations', 'meta.helm.sh/*']
    """
    # Split on dots not preceded by backslash
    parts = re.split(r'(?<!\\)\.', path)
    # Unescape literal dots
    return [p.replace('\\.', '.') for p in parts]


def _remove_path(obj: dict, path: str) -> None:
    """Remove a dot-path from a nested dict. Supports glob on the last segment."""
    parts = _split_dot_path(path)
    _remove_path_parts(obj, parts)


def _is_glob(segment: str) -> bool:
    return "*" in segment or "?" in segment or "[" in segment


def _remove_path_parts(obj: object, parts: list[str]) -> None:
    """Recursively walk into obj following parts, removing the leaf.

    Any segment may be a glob (dict keys) or '*' / an index (list items).
    """
    if not parts:
        return

    key, remaining = parts[0], parts[1:]

    if isinstance(obj, list):
        if key == "*":
            targets = obj
        elif key.isdigit() and int(key) < len(obj):
            targets = [obj[int(key)]]
        else:
            return
        if remaining:
            for item in targets:
                _remove_path_parts(item, remaining)
        return

    if not isinstance(obj, dict):
        return

    matches = [k for k in obj if fnmatch.fnmatchcase(str(k), key)] if _is_glob(key) else (
        [key] if key in obj else []
    )
    for k in matches:
        if remaining:
            _remove_path_parts(obj[k], remaining)
        else:
            del obj[k]


def normalize_body(body: dict) -> dict:
    """Sort dict keys recursively. Normalize known unordered lists."""
    result = copy.deepcopy(body)
    result = _sort_keys_recursive(result)
    result = _sort_known_lists(result)
    return result


def _sort_keys_recursive(obj: object) -> object:
    """Sort dict keys recursively, return new structure."""
    if isinstance(obj, dict):
        return {k: _sort_keys_recursive(v) for k, v in sorted(obj.items())}
    if isinstance(obj, list):
        return [_sort_keys_recursive(item) for item in obj]
    return obj


def _sort_known_lists(body: dict) -> dict:
    """Sort known unordered lists by their sort key."""
    for path_pattern, sort_key in UNORDERED_LIST_SORT_KEYS.items():
        _sort_list_at_path(body, path_pattern.split("."), sort_key)
    return body


def _sort_list_at_path(obj: object, parts: list[str], sort_key: str) -> None:
    """Walk the path pattern (with * wildcards for list indices) and sort the target list."""
    if not parts:
        return

    if isinstance(obj, dict):
        key = parts[0]
        remaining = parts[1:]
        if key in obj:
            if not remaining:
                # We've reached the target - sort if it's a list
                if isinstance(obj[key], list):
                    try:
                        obj[key] = sorted(
                            obj[key],
                            key=lambda item: item.get(sort_key, "") if isinstance(item, dict) else "",
                        )
                    except (TypeError, AttributeError):
                        pass
            else:
                _sort_list_at_path(obj[key], remaining, sort_key)
    elif isinstance(obj, list):
        # * wildcard matches each list element
        if parts[0] == "*":
            for item in obj:
                _sort_list_at_path(item, parts[1:], sort_key)
