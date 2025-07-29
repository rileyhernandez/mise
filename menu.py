from datetime import timedelta
from enum import Enum
from google.cloud import firestore
from pydantic import BaseModel, Field, field_serializer, field_validator
from typing import Any

DEVICE_COLLECTION = "devices"
CONFIG_COLLECTION = "config"


class Config(BaseModel):
    gain: float
    ingredient: str
    load_cell_id: int = Field(alias="loadCellId")
    location: str
    offset: float
    phidget_id: int = Field(alias="phidgetId")
    heartbeat_period: timedelta = Field(alias="heartbeatPeriod")
    phidget_sample_period: timedelta = Field(alias="phidgetSamplePeriod")
    max_noise: float = Field(alias="maxNoise")
    buffer_length: int = Field(alias="bufferLength")

    @field_validator("heartbeat_period", "phidget_sample_period", mode="before")
    @classmethod
    def _parse_duration(cls, v: Any) -> Any:
        """
        Handles deserialization from Rust's Duration format `{"secs": u64, "nanos": u32}`
        into a Python timedelta object.
        """
        if isinstance(v, dict) and "secs" in v and "nanos" in v:
            # Note: timedelta stores microseconds, not nanoseconds.
            return timedelta(seconds=v["secs"], microseconds=v["nanos"] // 1000)
        # Let Pydantic handle other formats (e.g., a float from Firestore)
        return v

    @field_serializer("heartbeat_period", "phidget_sample_period")
    def _serialize_duration(self, td: timedelta) -> float:
        """
        Serializes the timedelta object to a float representing total seconds,
        which is an ideal format for storing in Firestore.
        """
        return td.total_seconds()

    def to_client_dict(self) -> dict[str, Any]:
        """
        Serializes the model to a dictionary suitable for the Rust client.
        - Uses snake_case field names (no aliases).
        - Serializes timedelta fields to the `{"secs": ..., "nanos": ...}` format.
        """
        # Get a base dictionary with snake_case keys.
        # The default @field_serializer will run, but we'll overwrite its output.
        data = self.model_dump(by_alias=False)

        # Manually re-serialize timedelta fields into the client's desired format.
        for field_name in ["heartbeat_period", "phidget_sample_period"]:
            td_value: timedelta = getattr(self, field_name)

            if td_value:
                seconds = int(td_value.total_seconds())
                # Calculate nanoseconds from the fractional part of total_seconds()
                nanoseconds = int((td_value.total_seconds() - seconds) * 1_000_000_000)
                data[field_name] = {"secs": seconds, "nanos": nanoseconds}

        return data

    class Config:
        populate_by_name = True


class Model(str, Enum):
    IchibuV1 = "IchibuV1"
    IchibuV2 = "IchibuV2"
    LibraV0 = "LibraV0"


class Device(BaseModel):
    model: Model
    number: int


class FirestoreDeviceDocument(BaseModel):
    model: Model
    number: int
    config: str

    def to_device(self) -> Device:
        return Device.model_validate(self.model_dump())

    def to_config_ref(self) -> str:
        return self.config


class DeserializationError(Exception):
    pass


def path_to_device(path: str) -> Device:
    """
    Parses a URL path like '/<model>/<number>' into a Device object.

    Raises:
        ValueError: If the path format is incorrect or parts are invalid.
    """
    path_parts = path.strip("/").split("/")
    if len(path_parts) != 2:
        raise ValueError(
            f"Invalid path format. Expected '/<model>/<number>', but got '{path}'"
        )
    model_str, number_str = path_parts

    try:
        model = Model(model_str)
    except ValueError:
        raise ValueError(f"Invalid model '{model_str}' in path.")

    try:
        number = int(number_str)
    except ValueError:
        raise ValueError(
            f"Invalid device number '{number_str}'. It must be an integer."
        )

    return Device(model=model, number=number)


def query_for_device(device: Device, db: firestore.Client) -> FirestoreDeviceDocument:
    docs_stream = (
        db.collection(DEVICE_COLLECTION)
        .where(filter=firestore.FieldFilter("model", "==", device.model.value))
        .where(filter=firestore.FieldFilter("number", "==", device.number))
        .stream()
    )
    documents = list(docs_stream)
    if len(documents) > 1:
        msg = f"Multiple devices with this serial number exist: {device.model.value}-{device.number}"
        raise (FirestoreError(msg))
    elif len(documents) == 0:
        msg = f"No document found with serial number {device.model.value}-{device.number} in collection '{DEVICE_COLLECTION}'."
        raise (FirestoreError(msg))
    else:
        return FirestoreDeviceDocument.model_validate(documents[0].to_dict())


class FirestoreError(Exception):
    pass
