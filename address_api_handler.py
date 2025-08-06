from http import HTTPStatus

import flask
from google.cloud import firestore

from menu import path_to_device, DEVICE_COLLECTION, Device, FirestoreDeviceDocument


def get_address(request: flask.Request, db: firestore.Client) -> flask.Response:
    try:
        path = request.path.removeprefix("/address")
        device = path_to_device(path)
        transaction = db.transaction()
        address = _get_address_transaction(transaction, db, device)
        return flask.jsonify({"address": address})

    except Exception as e:
        print(f"CRITICAL: An unexpected error occurred in get_address(): {e}")
        response = flask.jsonify({"error": f"An internal server error occurred: {e}"})
        response.status_code = HTTPStatus.INTERNAL_SERVER_ERROR
        return response
@firestore.transactional
def _get_address_transaction(transaction, db: firestore.Client, device: Device) -> str:
    address_query = (
        db.collection(DEVICE_COLLECTION)
        .where(filter=firestore.FieldFilter("model", "==", device.model.value))
        .where(filter=firestore.FieldFilter("number", "==", device.number))
        .limit(1)
    )
    document = list(address_query.stream())
    if len(document) > 1:
        raise Exception(
            f"Multiple devices with this serial number exist: {device.model.value}-{device.number}"
        )
    elif len(document) < 1:
        raise Exception(
            f"No document found with serial number {device.model.value}-{device.number} in collection '{DEVICE_COLLECTION}'."
        )
    else:
        document_snapshot = document[0].to_dict()
        if "address" in document_snapshot:
            address = document_snapshot.get("address")
            return address
        else:
            raise Exception(
                f"Device has no configured address: {device.model.value}-{device.number}"
            )


def put_address(request: flask.Request, db: firestore.Client) -> flask.Response:
    try:
        path = request.path.removeprefix("/address")
        device = path_to_device(path)
        address = request.get_json().get("address")
        transaction = db.transaction()
        _put_address_transaction(transaction, db, device, address)

        return flask.make_response("Successfully updated address.", HTTPStatus.OK)
    except Exception as e:
        print(f"CRITICAL: An unexpected error occurred in get_address(): {e}")
        response = flask.jsonify({"error": f"An internal server error occurred: {e}"})
        response.status_code = HTTPStatus.INTERNAL_SERVER_ERROR
        return response
@firestore.transactional
def _put_address_transaction(transaction, db: firestore.Client, device: Device, new_address: str):
    device_query = (
        db.collection(DEVICE_COLLECTION)
        .where(filter=firestore.FieldFilter("model", "==", device.model.value))
        .where(filter=firestore.FieldFilter("number", "==", device.number))
        .limit(1)
    )
    docs_stream = device_query.stream(transaction=transaction)
    documents = list(docs_stream)
    if len(documents) > 1:
        raise Exception(
            f"Multiple devices with this serial number exist: {device.model.value}-{device.number}"
        )
    elif len(documents) < 1:
        raise Exception(
            f"No document found with serial number {device.model.value}-{device.number} in collection '{DEVICE_COLLECTION}'."
        )
    else:
        document_ref = documents[0].reference
        transaction.update(document_ref, {"address": new_address})
