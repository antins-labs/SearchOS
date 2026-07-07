"""Base model with camelCase alias support."""

from pydantic import BaseModel, ConfigDict


class CamelModel(BaseModel):
    """Base model: snake_case in Python, camelCase in JSON."""

    model_config = ConfigDict(
        populate_by_name=True,
    )
