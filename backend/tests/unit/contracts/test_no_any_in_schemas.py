"""Walk every Pydantic model in :mod:`aef.contracts` for ``Any`` leaks.

ADR-0010 forbids ``Dict[str, Any]`` (and bare ``Any``) on public surfaces.
This test enumerates every model exported from :mod:`aef.contracts`,
walks its JSON schema, and fails if any field's type is ``Any`` or
permits arbitrary additional properties via ``additionalProperties: True``.

Closed-string-set fields (``dict[str, str]``, ``frozenset[Literal[...]]``)
are accepted because their constraint is enforced by Pydantic at runtime.
"""

from __future__ import annotations

import inspect
from typing import Any, cast

from pydantic import BaseModel

import aef.contracts as contracts


def _iter_contract_models() -> list[type[BaseModel]]:
    out: list[type[BaseModel]] = []
    for name in contracts.__all__:
        obj = getattr(contracts, name, None)
        if inspect.isclass(obj) and issubclass(obj, BaseModel):
            out.append(obj)
    return out


def _walk_schema(node: object, path: str, violations: list[str]) -> None:
    if not isinstance(node, dict):
        return
    schema: dict[str, Any] = node  # type: ignore[assignment]

    # The JSON Schema 2020-12 spec allows several "type"-shaped keys.
    # We are mainly looking for fields whose schema is `{}` (i.e. Any)
    # or that explicitly allow `additionalProperties` of arbitrary type.
    type_value: Any = schema.get("type")
    if type_value == "object":
        additional: Any = schema.get("additionalProperties")
        if additional is True:
            violations.append(f"{path} → additionalProperties: True (Any leak)")
        if isinstance(additional, dict) and not additional:
            violations.append(
                f"{path} → additionalProperties: {{}} (Any leak)",
            )

    any_of: Any = schema.get("anyOf")
    if isinstance(any_of, list):
        items_list = cast("list[Any]", any_of)
        for i, sub in enumerate(items_list):
            _walk_schema(sub, f"{path}.anyOf[{i}]", violations)
    if "items" in schema:
        _walk_schema(schema["items"], f"{path}.items", violations)
    properties: Any = schema.get("properties")
    if isinstance(properties, dict):
        prop_map = cast("dict[str, Any]", properties)
        for prop_name, prop_schema in prop_map.items():
            _walk_schema(prop_schema, f"{path}.{prop_name}", violations)
    defs: Any = schema.get("$defs")
    if isinstance(defs, dict):
        defs_map = cast("dict[str, Any]", defs)
        for def_name, def_schema in defs_map.items():
            _walk_schema(def_schema, f"{path}.$defs.{def_name}", violations)

    # An empty schema `{}` (no `type`, no constraints) means "any value".
    # Tolerated only when the parent already constrained the value.
    if not schema and not path.endswith(".items") and "$ref" not in schema:
        violations.append(f"{path} → empty schema (Any leak)")


def test_no_any_in_public_contract_schemas() -> None:
    violations: list[str] = []
    for model in _iter_contract_models():
        schema: dict[str, Any] = model.model_json_schema()
        _walk_schema(schema, model.__name__, violations)

    assert not violations, "Found `Any` / unconstrained fields on public contracts:\n" + "\n".join(
        violations
    )


def test_every_contract_model_forbids_extra_fields() -> None:
    """Every public model uses ``extra='forbid'``.

    This protects against silent payload drift (a client adding a field
    that older code happily ignores) and matches the strict-typing
    posture of ADR-0010.
    """
    violations: list[str] = []
    for model in _iter_contract_models():
        if model.model_config.get("extra") != "forbid":
            violations.append(model.__name__)
    assert not violations, (
        "Models missing extra='forbid' (set ConfigDict in the model):\n" + "\n".join(violations)
    )
