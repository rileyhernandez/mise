import flask
from http import HTTPStatus
from pydantic import ValidationError
from menu import (
    CONFIG_COLLECTION,
    Config,
    path_to_device,
    query_for_device,
    DeserializationError,
    FirestoreError,
    Model,
    DEVICE_COLLECTION,
    FirestoreDeviceDocument,
)
from google.cloud import firestore


def get(request: flask.Request, db: firestore.Client) -> flask.Response:
    """
    Handles GET requests to fetch device configuration.
    """
    try:
        device = path_to_device(request.path)
        device_document = query_for_device(device, db)
        config_doc_ref = device_document.to_config_ref()
        config = Config.model_validate(
            db.collection(CONFIG_COLLECTION).document(config_doc_ref).get().to_dict()
        )
        print("CONFIG: ", config)
        response = flask.jsonify(config.model_dump(by_alias=False))
        response.status_code = HTTPStatus.OK
        return response
    except Exception as e:
        print(f"CRITICAL: An unexpected error occurred in get(): {e}")
        response = flask.jsonify({"error": f"An internal server error occurred: {e}"})
        response.status_code = HTTPStatus.INTERNAL_SERVER_ERROR
        return response


def put(request: flask.Request, db: firestore.Client) -> flask.Response:
    """
    Handles PUT requests to update a device's config.
    """
    try:
        device = path_to_device(request.path)
        device_document = query_for_device(device, db)
        new_config = Config.model_validate(request.get_json())
        config_doc_ref = device_document.to_config_ref()
        db.collection(CONFIG_COLLECTION).document(config_doc_ref).set(
            new_config.model_dump(by_alias=True)
        )
        response = flask.jsonify(
            {
                "message": f"Config for {device.model.value}-{device.number} updated successfully."
            }
        )
        response.status_code = HTTPStatus.OK
        return response

    except (ValueError, ValidationError, DeserializationError) as e:
        # Catches bad path format (ValueError) or invalid JSON body (ValidationError)
        response = flask.jsonify({"error": f"Bad Request: {e}"})
        response.status_code = HTTPStatus.BAD_REQUEST
        return response
    except FirestoreError as e:
        # Catches device not found from query_for_device
        response = flask.jsonify({"error": str(e)})
        response.status_code = HTTPStatus.NOT_FOUND
        return response
    except Exception as e:
        # A catch-all for any other unexpected server errors
        print(f"CRITICAL: An unexpected error occurred in put(): {e}")
        response = flask.jsonify({"error": f"An internal server error occurred: {e}"})
        response.status_code = HTTPStatus.INTERNAL_SERVER_ERROR
        return response


def post(request: flask.Request, db: firestore.Client) -> flask.Response:
    try:
        model = Model[(request.path.split("/")[-1])]
        most_recent_device_query = (
            db.collection(DEVICE_COLLECTION)
            .where(filter=firestore.FieldFilter("model", "==", model.value))
            .order_by("number", direction=firestore.Query.DESCENDING)
            .limit(1)
            .stream()
        )
        most_recent_device = list(most_recent_device_query)
        if len(most_recent_device) == 1:
            new_device_number = most_recent_device[0].get("number") + 1
            new_config = Config.model_validate(request.get_json())
            _timestamp, new_config_doc_ref = db.collection(CONFIG_COLLECTION).add(
                new_config.model_dump(by_alias=True)
            )
            new_device_doc = FirestoreDeviceDocument.model_construct(
                model=model, number=new_device_number, config=new_config_doc_ref.id
            )
            db.collection(DEVICE_COLLECTION).add(new_device_doc.model_dump())
            return flask.make_response(
                new_device_doc.to_device().model_dump(), HTTPStatus.OK
            )
        else:
            return flask.make_response(
                f"No existing devices of the model: {model.value}",
                HTTPStatus.BAD_REQUEST,
            )
    except Exception as e:
        # A catch-all for any other unexpected server errors
        print(f"CRITICAL: An unexpected error occurred in post(): {e}")
        response = flask.jsonify({"error": f"An internal server error occurred: {e}"})
        response.status_code = HTTPStatus.INTERNAL_SERVER_ERROR
        return response
