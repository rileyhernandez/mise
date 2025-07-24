import flask
from http import HTTPStatus

from menu import CONFIG_COLLECTION, Config, path_to_device, query_for_device
from google.cloud import firestore


def get(request: flask.Request, db: firestore.Client) -> (flask.Response, HTTPStatus):
    """
    Handles GET requests to fetch device configuration.
    """
    try:
        device = path_to_device(request.path)
        device_document = query_for_device(device, db)
        config_doc_ref = device_document.to_config()
        config = Config.from_dict(db.collection(CONFIG_COLLECTION).document(config_doc_ref).get().to_dict())
        print("CONFIG: ", config)
        return flask.jsonify(config.model_dump(by_alias=False)), HTTPStatus.OK
    except Exception as e:
        print(f"CRITICAL: An unexpected error occurred in get(): {e}")
        return flask.jsonify({"error": "An internal server error occurred."}), HTTPStatus.INTERNAL_SERVER_ERROR

