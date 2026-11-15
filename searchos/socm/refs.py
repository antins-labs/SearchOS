"""SOCM 行与单元格的结构化引用及唯一字典编码。"""

from __future__ import annotations

import json

from pydantic import BaseModel, ConfigDict, Field, field_validator

STATE_FORMAT_VERSION = 2


def row_key(values: list[str]) -> str:
    if not isinstance(values, list) or not values or any(
        not isinstance(value, str) or not value.strip() for value in values
    ):
        raise ValueError("A row key requires every primary-key value as a non-empty string")
    return json.dumps(values, ensure_ascii=False, separators=(",", ":"))


def row_values(key: str) -> list[str]:
    values = json.loads(key)
    if row_key(values) != key:
        raise ValueError("Non-canonical row key")
    return values


def cell_key(table_id: str, entity: str, attribute: str) -> str:
    if not table_id or not attribute:
        raise ValueError("A cell reference requires table_id and attribute")
    return json.dumps([table_id, row_values(entity), attribute], ensure_ascii=False, separators=(",", ":"))


def cell_parts(key: str) -> tuple[str, str, str]:
    parts = json.loads(key)
    if not isinstance(parts, list) or len(parts) != 3:
        raise ValueError("Invalid cell key")
    table_id, values, attribute = parts
    if not isinstance(table_id, str) or not isinstance(attribute, str):
        raise ValueError("Invalid cell reference")
    entity = row_key(values)
    if cell_key(table_id, entity, attribute) != key:
        raise ValueError("Non-canonical cell key")
    return table_id, entity, attribute


class RowRef(BaseModel):
    """key 的顺序与表的 primary_key 一致。"""

    model_config = ConfigDict(extra="forbid", strict=True)
    table_id: str = Field(description="ID of the table containing the row.")
    key: list[str] = Field(description="Every primary-key value as a non-empty string, in primary_key order.")

    @field_validator("table_id")
    @classmethod
    def nonempty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("table_id must be non-empty")
        return value

    @field_validator("key")
    @classmethod
    def complete_key(cls, value: list[str]) -> list[str]:
        row_key(value)
        return value

    def row_key(self) -> str:
        return row_key(self.key)

    @property
    def entity(self) -> str:
        return self.row_key()


class CellRef(RowRef):
    attribute: str = Field(description="Exact name of the referenced column.")

    @field_validator("attribute")
    @classmethod
    def nonempty_attribute(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("attribute must be non-empty")
        return value

    def cell_key(self) -> str:
        return cell_key(self.table_id, self.row_key(), self.attribute)


def row_ref(table_id: str, entity: str) -> dict:
    return RowRef(table_id=table_id, key=row_values(entity)).model_dump()


def cell_ref(key: str) -> dict:
    table_id, entity, attribute = cell_parts(key)
    return CellRef(table_id=table_id, key=row_values(entity), attribute=attribute).model_dump()
