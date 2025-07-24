from enum import Enum
from google.cloud import firestore
from pydantic import BaseModel, Field

DEVICE_COLLECTION = "devices"
CONFIG_COLLECTION = "config"


class Config(BaseModel):
    gain: float
    ingredient: str
    load_cell_id: int = Field(alias="loadCellId")
    location: str
    offset: float
    phidget_id: int = Field(alias="phidgetId")

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
