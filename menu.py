from dataclasses import dataclass
from enum import Enum
from typing import Self

DEVICE_COLLECTION = "devices"
CONFIG_COLLECTION = "config"

@dataclass
class Config:
    gain: float
    ingredient: str
    load_cell_id: int
    location: str
    offset: float
    phidget_id: int
    @classmethod
    def from_dict(cls, data: dict) -> Self:
        try:
            config = Config(
                gain=data["gain"],
                ingredient=data["ingredient"],
                load_cell_id=data["loadCellId"],
                location=data["location"],
                offset=data["offset"],
                phidget_id=data["phidgetId"]
            )
            return config
        except Exception as e:
            raise DeserializationError(f"Failed to create Config from Document: {data}") from e

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
class DeserializationError(Exception):
    pass


'''
| "GET" ->
    try
        let path = context.Request.Path.Value[1..].Split("-", StringSplitOptions.RemoveEmptyEntries)
        let model = path[0]
        let number = path[1] |> int
        let query =
            firestoreDb
                .Collection(collectionName)
                .WhereEqualTo("model", model)
                .WhereEqualTo("number", number)
        let! snapshot = query.GetSnapshotAsync()
        if snapshot.Count > 1 then
            context.Response.StatusCode <- 500
            return! context.Response.WriteAsync("Multiple devices with this serial number exist!")
        else if snapshot.Count > 0 then
            let document = snapshot.Documents[0]
            // Get the config field and extract only the ID, handling both old and new formats.
            let configValue = document.GetValue<string> "config"
            let configId = getConfigId configValue
            
            let! configDoc = firestoreDb.Collection("config").Document(configId).GetSnapshotAsync()
            return! context.Response.WriteAsJsonAsync (configDoc.ToDictionary())
        else
            let msg = $"No document found with serial number {model}-{number} in collection '{collectionName}'."
            logger.LogWarning msg
            context.Response.StatusCode <- 404
            return! context.Response.WriteAsJsonAsync({| error = msg |})
    with ex ->
        logger.LogError(ex, "An error occurred while querying Firestore; device likely does not exist")
        context.Response.StatusCode <- 404
        return! context.Response.WriteAsync($"{ex}")



'''