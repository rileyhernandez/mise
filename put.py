# /home/riley/projects/mise/put.py

import flask
from http import HTTPStatus
from google.cloud import firestore
# Import the specific errors we want to handle
from pydantic import ValidationError
from menu import (
    CONFIG_COLLECTION,
    Config,
    path_to_device,
    query_for_device,
    FirestoreError,
    DeserializationError, # Keep for other models like Device
)

def put(request: flask.Request, db: firestore.Client) -> tuple[flask.Response, HTTPStatus]:
    """
    Handles PUT requests to update a device's config.
    """
    try:
        # 1. Find the device from the URL path
        device = path_to_device(request.path)
        device_document = query_for_device(device, db)

        # 2. Validate the incoming JSON and create a Config object
        #    Pydantic's model_validate raises a helpful ValidationError on failure.
        new_config = Config.model_validate(request.get_json())

        # 3. Get the ID of the config document to update
        config_doc_ref = device_document.to_config()

        # 4. Convert the Pydantic model back to a camelCase dictionary and save to Firestore
        #    .model_dump(by_alias=True) is the key! It uses the aliases from your model.
        db.collection(CONFIG_COLLECTION).document(config_doc_ref).set(
            new_config.model_dump(by_alias=True)
        )

        # Return a success response
        return flask.jsonify({"message": f"Config for {device.model.value}-{device.number} updated successfully."}), HTTPStatus.OK

    # --- Robust Error Handling ---
    except (ValueError, ValidationError, DeserializationError) as e:
        # Catches bad path format (ValueError) or invalid JSON body (ValidationError)
        return flask.jsonify({"error": f"Bad Request: {e}"}), HTTPStatus.BAD_REQUEST
    except FirestoreError as e:
        # Catches device not found from query_for_device
        return flask.jsonify({"error": str(e)}), HTTPStatus.NOT_FOUND
    except Exception as e:
        # A catch-all for any other unexpected server errors
        print(f"CRITICAL: An unexpected error occurred in put(): {e}")
        return flask.jsonify({"error": "An internal server error occurred"}), HTTPStatus.INTERNAL_SERVER_ERROR