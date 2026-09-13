"""OpenAPI specifications for Rain Bird Cloud APIs."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import yaml

OPENAPI_DIR = Path(__file__).parent


def _resolve_file_ref(base_dir: Path, ref_str: str) -> tuple[Path, str]:
    """Split a $ref string into file path and json pointer fragment."""
    parts = ref_str.split("#", 1)
    file_path = base_dir / parts[0]
    fragment = parts[1] if len(parts) > 1 else ""
    return file_path.resolve(), fragment


def _get_by_pointer(data: Any, pointer: str) -> Any:
    """Retrieve sub-element from dict/list using JSON pointer syntax."""
    if not pointer or pointer == "/":
        return data
    tokens = pointer.strip("/").split("/")
    curr = data
    for token in tokens:
        token = token.replace("~1", "/").replace("~0", "~")
        if isinstance(curr, dict):
            curr = curr[token]
        elif isinstance(curr, list):
            curr = curr[int(token)]
        else:
            raise KeyError(f"Cannot traverse into {type(curr)} with token {token}")
    return curr


def _bundle_refs(
    node: Any,
    current_file: Path,
    cache: dict[Path, Any] | None = None,
    seen: set[tuple[str, str]] | None = None,
) -> Any:
    """Recursively resolve and inline external file $ref references."""
    if cache is None:
        cache = {}
    if seen is None:
        seen = set()

    if isinstance(node, dict):
        if "$ref" in node and isinstance(node["$ref"], str):
            ref_val: str = node["$ref"]
            if ref_val.startswith("#"):
                target_file = current_file
                fragment = ref_val[1:]
            else:
                target_file, fragment = _resolve_file_ref(current_file.parent, ref_val)

            seen_key = (str(target_file), fragment)
            if seen_key in seen:
                return node
            seen.add(seen_key)

            if target_file not in cache:
                with target_file.open("r", encoding="utf-8") as f:
                    cache[target_file] = yaml.safe_load(f)

            target_data = cache[target_file]
            target_sub = _get_by_pointer(target_data, fragment) if fragment else target_data
            resolved = copy.deepcopy(target_sub)
            return _bundle_refs(resolved, target_file, cache, seen)

        return {k: _bundle_refs(v, current_file, cache, seen) for k, v in node.items()}

    if isinstance(node, list):
        return [_bundle_refs(item, current_file, cache, seen) for item in node]

    return node


def load_openapi_spec(api: str = "rb2", bundle: bool = True) -> dict[str, Any]:
    """Load OpenAPI specification for Rain Bird cloud API.

    Args:
        api: Subdirectory API name, e.g. "rb2" (Communication Device Cloud API) or "legacy" (Legacy Communication Service).
        bundle: Whether to inline and resolve external file $ref links.

    Returns:
        Dictionary representation of the OpenAPI document.
    """
    root_file = OPENAPI_DIR / api / "openapi.yaml"
    if not root_file.is_file():
        raise FileNotFoundError(f"OpenAPI spec root not found at {root_file}")

    with root_file.open("r", encoding="utf-8") as f:
        spec = yaml.safe_load(f)

    if bundle:
        spec = _bundle_refs(spec, root_file)

    return spec


def get_openapi_yaml(api: str = "rb2", bundle: bool = True) -> str:
    """Return OpenAPI specification formatted as YAML string."""
    spec = load_openapi_spec(api=api, bundle=bundle)
    return yaml.dump(spec, sort_keys=False)
