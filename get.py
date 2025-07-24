import flask
from http import HTTPStatus

from menu import DEVICE_COLLECTION, CONFIG_COLLECTION, Config
from menu import Device, Model
from google.cloud import firestore


def get(request: flask.Request, db: firestore.Client) -> (flask.Response, HTTPStatus):
    """
    Handles GET requests to fetch device configuration.
    """
    try:
        device = path_to_device(request.path)
        print(f"DEBUG: Looking for device: {device}")
        docs_stream = db.collection(DEVICE_COLLECTION) \
            .where(filter=firestore.FieldFilter("model", "==", device.model.value)) \
            .where(filter=firestore.FieldFilter("number", "==", device.number)) \
            .stream()
        documents = list(docs_stream)
        if len(documents) > 1:
            msg = f"Multiple devices with this serial number exist: {device.model.value}-{device.number}"
            print(f"ERROR: {msg}")
            return flask.jsonify({"error": msg}), HTTPStatus.INTERNAL_SERVER_ERROR
        elif len(documents) == 0:
            msg = f"No document found with serial number {device.model.value}-{device.number} in collection '{DEVICE_COLLECTION}'."
            print(f"ERROR: {msg}")
            return flask.jsonify({"error": msg}), HTTPStatus.NOT_FOUND
        else:
            config_doc_ref = documents[0].get("config")
            Device.from_dict(documents[0].to_dict())
            config = Config.from_dict(db.collection(CONFIG_COLLECTION).document(config_doc_ref).get().to_dict())
            print("CONFIG: ", config)
            return flask.jsonify(config), HTTPStatus.OK
    except ValueError as e:
        return flask.Response(str(e), HTTPStatus.BAD_REQUEST)
    except Exception as e:
        print(f"CRITICAL: An unexpected error occurred in get(): {e}")
        return flask.jsonify({"error": "An internal server error occurred."}), HTTPStatus.INTERNAL_SERVER_ERROR


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
        # This is the key change: convert the string to a Model enum member
        model = Model(model_str)
    except ValueError:
        # This gives a helpful error if the model name isn't in the enum
        raise ValueError(f"Invalid model '{model_str}' in path.")

    try:
        number = int(number_str)
    except ValueError:
        raise ValueError(f"Invalid device number '{number_str}'. It must be an integer.")

    return Device(model=model, number=number)
