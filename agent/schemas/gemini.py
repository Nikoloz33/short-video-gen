"""Gemini-friendly JSON schemas: Gemini's `response_schema` handles `$ref`/`$defs` poorly, so refs are
inlined and unsupported keywords dropped. Models used for LLM output avoid dict maps and tuples."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

# Keywords Vertex's OpenAPI-subset schema accepts. Everything else is dropped.
_ALLOWED = {
    "type",
    "format",
    "description",
    "nullable",
    "enum",
    "properties",
    "required",
    "items",
    "minItems",
    "maxItems",
    "minimum",
    "maximum",
    "minLength",
    "maxLength",
    "pattern",
    "anyOf",
    "propertyOrdering",
    "title",
}


def _inline(node: Any, defs: dict[str, Any], depth: int = 0) -> Any:
    if depth > 40:
        raise ValueError("schema nesting too deep (recursive model?)")
    if isinstance(node, dict):
        if "$ref" in node:
            name = node["$ref"].rsplit("/", 1)[-1]
            merged = {**defs[name], **{k: v for k, v in node.items() if k != "$ref"}}
            return _inline(merged, defs, depth + 1)
        out: dict[str, Any] = {}
        for k, v in node.items():
            if k in ("$defs", "definitions"):
                continue
            if k == "const":
                out["enum"] = [v]
                continue
            if k == "oneOf":  # discriminated unions: Gemini supports anyOf, not oneOf
                out["anyOf"] = _inline(v, defs, depth + 1)
                continue
            if k == "exclusiveMinimum":
                out["minimum"] = v
                continue
            if k == "exclusiveMaximum":
                out["maximum"] = v
                continue
            if k == "properties":
                out[k] = {p: _inline(s, defs, depth + 1) for p, s in v.items()}
                continue
            if k not in _ALLOWED:
                continue
            out[k] = _inline(v, defs, depth + 1)
        return _simplify_nullable(out)
    if isinstance(node, list):
        return [_inline(v, defs, depth + 1) for v in node]
    return node


def _simplify_nullable(node: dict[str, Any]) -> dict[str, Any]:
    """`anyOf: [X, {type: null}]` -> X with `nullable: true` (clearer for the model)."""
    any_of = node.get("anyOf")
    if isinstance(any_of, list) and len(any_of) == 2:
        non_null = [s for s in any_of if s.get("type") != "null"]
        if len(non_null) == 1:
            rest = {k: v for k, v in node.items() if k != "anyOf"}
            return {**non_null[0], **rest, "nullable": True}
    return node


def gemini_schema(model: type[BaseModel]) -> dict[str, Any]:
    """Flattened JSON schema for `model`, suitable for `response_schema`."""
    raw = model.model_json_schema(mode="validation")
    defs = raw.get("$defs", {})
    flat: dict[str, Any] = _inline(raw, defs)
    return flat
