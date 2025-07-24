from dataclasses import dataclass
from enum import Enum
from typing import Self, Any
from google.cloud import firestore
from pydantic import BaseModel, model_validator, Field

DEVICE_COLLECTION = "devices"
CONFIG_COLLECTION = "config"


class Config(BaseModel):
    gain: float
    ingredient: str
    # Use an alias to map the Python attribute to the source data's key
    load_cell_id: int = Field(alias='loadCellId')
    location: str
    offset: float
    phidget_id: int = Field(alias='phidgetId')

    # This configuration tells Pydantic to allow creating the model
    # using either the Python name ('load_cell_id') or the alias ('loadCellId').
    # This replaces your custom _normalize_keys validator.
    class Config:
        populate_by_name = True

    # You can still have a from_dict for a consistent API
    @classmethod
    def from_dict(cls, data: dict) -> Self:
        try:
            # .model_validate() triggers the whole process:
            # 1. Runs our _normalize_keys validator
            # 2. Validates data types (e.g., ensures 'gain' is a float)
            # 3. Creates the Config instance
            return cls.model_validate(data)
        except Exception as e: # Pydantic raises a detailed ValidationError
            raise DeserializationError(f"Failed to create Config from document") from e
class Model(Enum):
    IchibuV1 = "IchibuV1"
    IchibuV2 = "IchibuV2"
    LibraV0 = "LibraV0"

@dataclass
class Device:
    model: Model
    number: int
    @classmethod
    def from_dict(cls, data: dict) -> Self:
        try:
            device = Device(model=Model(data["model"]), number=data["number"])
            return device
        except Exception as e:
            raise DeserializationError(f"Failed to create Device from Document: {data}") from e
@dataclass
class FirestoreDeviceDocument:
    model: Model
    number: int
    config: str
    @classmethod
    def from_dict(cls, data: dict) -> Self:
        try:
            device_doc = FirestoreDeviceDocument(model=Model(data["model"]), number=data["number"], config=data["config"])
            return device_doc
        except Exception as e:
            raise DeserializationError(f"Failed to create Device Document from Document: {data}") from e
    def to_device(self) -> Device:
        return Device(model=self.model, number=self.number)
    def to_config(self) -> str:
        return self.config

class DeserializationError(Exception):
    pass

def path_to_device(path: str) -> Device:
    """
    Parses a URL path like '/<model>/<number>' into a Device object.

    Raises:
        ValueError: If the path format is incorrect or parts are invalid.
    """
    path_parts = path.strip('/').split('/')
    if len(path_parts) != 2:
        raise ValueError(f"Invalid path format. Expected '/<model>/<number>', but got '{path}'")
    model_str, number_str = path_parts

    try:
        model = Model(model_str)
    except ValueError:
        raise ValueError(f"Invalid model '{model_str}' in path.")

    try:
        number = int(number_str)
    except ValueError:
        raise ValueError(f"Invalid device number '{number_str}'. It must be an integer.")

    return Device(model=model, number=number)

def query_for_device(device: Device, db: firestore.Client) -> FirestoreDeviceDocument:
    docs_stream = db.collection(DEVICE_COLLECTION) \
        .where(filter=firestore.FieldFilter("model", "==", device.model.value)) \
        .where(filter=firestore.FieldFilter("number", "==", device.number)) \
        .stream()
    documents = list(docs_stream)
    if len(documents) > 1:
        msg = f"Multiple devices with this serial number exist: {device.model.value}-{device.number}"
        raise(FirestoreError(msg))
    elif len(documents) == 0:
        msg = f"No document found with serial number {device.model.value}-{device.number} in collection '{DEVICE_COLLECTION}'."
        raise(FirestoreError(msg))
    else:
        return FirestoreDeviceDocument.from_dict(documents[0].to_dict())

class FirestoreError(Exception):
    pass

"""
| "PUT" ->
                    try
                        // Find the device based on the path (e.g., /caldo-1)
                        let path = context.Request.Path.Value[1..].Split("-", StringSplitOptions.RemoveEmptyEntries)
                        let model = path[0]
                        let number = path[1] |> int
                        let query =
                            firestoreDb
                                .Collection(collectionName)
                                .WhereEqualTo("model", model)
                                .WhereEqualTo("number", number)
                        let! snapshot = query.GetSnapshotAsync()

                        // Handle cases where the device is not found or is ambiguous
                        if snapshot.Count > 1 then
                            context.Response.StatusCode <- 500
                            return! context.Response.WriteAsync("Multiple devices with this serial number exist!")
                        else if snapshot.Count = 0 then
                            let msg = $"No document found with serial number {model}-{number} in collection '{collectionName}'."
                            logger.LogWarning msg
                            context.Response.StatusCode <- 404
                            return! context.Response.WriteAsJsonAsync({| error = msg |})
                        else
                            // Device found, so we can proceed with the update.
                            let deviceDoc = snapshot.Documents[0]
                            let configValue = deviceDoc.GetValue<string> "config"
                            let configId = getConfigId configValue

                            if String.IsNullOrWhiteSpace(configId) then
                                let msg = $"Device {model}-{number} has an invalid or missing config reference."
                                logger.LogError msg
                                context.Response.StatusCode <- 500
                                return! context.Response.WriteAsJsonAsync({| error = msg |})

                            use reader = new System.IO.StreamReader(context.Request.Body)
                            let! bodyAsString = reader.ReadToEndAsync()

                            if String.IsNullOrWhiteSpace(bodyAsString) then
                                context.Response.StatusCode <- 400 // Bad Request
                                return! context.Response.WriteAsync("Request body is empty.")
                            else
                                // This uses Newtonsoft.Json. The Google.Cloud.Firestore.NewtonsoftJson package
                                // provides converters that allow Firestore to handle the resulting object.
                                let newConfigData = JsonConvert.DeserializeObject<Dictionary<string, obj>>(bodyAsString)

                                // Replace the existing config document with the new data.
                                let configDocRef = firestoreDb.Collection("config").Document(configId)
                                let! _ = configDocRef.SetAsync(newConfigData)

                                logger.LogInformation $"Successfully updated config '{configId}' for device '{model}-{number}'."
                                
                                // Return a success response.
                                context.Response.StatusCode <- 200
                                return! context.Response.WriteAsJsonAsync({| message = $"Config for {model}-{number} updated successfully." |})

                    with ex ->
                        logger.LogError(ex, "An error occurred while updating Firestore Document")
                        context.Response.StatusCode <- 500
                        return! context.Response.WriteAsync($"Could not update device: {ex.Message}")
"""