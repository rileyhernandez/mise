from pydantic import BaseModel, model_validator
from typing import Any, Self


# ... (keep DeserializationError)

class Config(BaseModel):
    # Field definitions are the same
    gain: float
    ingredient: str
    load_cell_id: int
    location: str
    offset: float
    phidget_id: int

    # This is a special Pydantic decorator that runs before validation
    @model_validator(mode='before')
    @classmethod
    def _normalize_keys(cls, data: Any) -> Any:
        """Allow creating a Config from either camelCase or snake_case keys."""
        if not isinstance(data, dict):
            return data  # Pass through non-dict data

        # If a camelCase key exists, move its value to a snake_case key
        if 'loadCellId' in data:
            data['load_cell_id'] = data.pop('loadCellId')
        if 'phidgetId' in data:
            data['phidget_id'] = data.pop('phidgetId')

        return data

    # You can still have a from_dict for a consistent API
    @classmethod
    def from_dict(cls, data: dict) -> Self:
        try:
            # .model_validate() triggers the whole process:
            # 1. Runs our _normalize_keys validator
            # 2. Validates data types (e.g., ensures 'gain' is a float)
            # 3. Creates the Config instance
            return cls.model_validate(data)
        except Exception as e:  # Pydantic raises a detailed ValidationError
            raise DeserializationError(f"Failed to create Config from document") from e
