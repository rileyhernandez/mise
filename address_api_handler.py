from http import HTTPStatus

import flask
from google.cloud import firestore
from pydantic import BaseModel, ValidationError

from menu import (
    DEVICE_COLLECTION,
    DeserializationError,
    Device,
    FirestoreError,
    path_to_device,
)


class AddressPayload(BaseModel):
    address: str


def get_address(request: flask.Request, db: firestore.Client) -> flask.Response:
    try:
        path = request.path.removeprefix("/address")
        device = path_to_device(path)
        transaction = db.transaction()
        address = _get_address_transaction(transaction, db, device)
        return flask.jsonify({"address": address})
    except (ValueError, DeserializationError) as e:
        response = flask.jsonify({"error": f"Bad Request: {e}"})
        response.status_code = HTTPStatus.BAD_REQUEST
        return response
    except FirestoreError as e:
        response = flask.jsonify({"error": str(e)})
        response.status_code = HTTPStatus.NOT_FOUND
        return response
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
        .where(filter=firestore.FieldFilter("serialNumber", "==", device.serial_number))
        .limit(1)
    )
    # Pass the transaction to the stream for transactional reads
    document_stream = address_query.stream(transaction=transaction)
    documents = list(document_stream)

    if len(documents) > 1:
        # This case should ideally not happen with limit(1), but it's good practice
        # to handle it as a server-side data integrity issue.
        raise FirestoreError(
            f"Multiple devices with this serial number exist: {device.model.value}-{device.serial_number}"
        )
    elif not documents:
        raise FirestoreError(
            f"No document found with serial number {device.model.value}-{device.serial_number} in collection '{DEVICE_COLLECTION}'."
        )

    document_snapshot = documents[0].to_dict()
    if "address" in document_snapshot and document_snapshot.get("address"):
        return document_snapshot.get("address")
    else:
        raise FirestoreError(
            f"Device has no configured address: {device.model.value}-{device.serial_number}"
        )


def put_address(request: flask.Request, db: firestore.Client) -> flask.Response:
    try:
        path = request.path.removeprefix("/address")
        device = path_to_device(path)

        # Validate incoming JSON
        try:
            payload = AddressPayload.model_validate(request.get_json())
            address = payload.address
        except (
            ValidationError,
            AttributeError,
        ):  # AttributeError for request.get_json() being None
            raise DeserializationError(
                "Invalid JSON body. Expected '{\"address\": \"...\"}'."
            )

        transaction = db.transaction()
        _put_address_transaction(transaction, db, device, address)

        return flask.make_response("Successfully updated address.", HTTPStatus.OK)
    except (ValueError, DeserializationError) as e:
        response = flask.jsonify({"error": f"Bad Request: {e}"})
        response.status_code = HTTPStatus.BAD_REQUEST
        return response
    except FirestoreError as e:
        response = flask.jsonify({"error": str(e)})
        response.status_code = HTTPStatus.NOT_FOUND
        return response
    except Exception as e:
        print(f"CRITICAL: An unexpected error occurred in put_address(): {e}")
        response = flask.jsonify({"error": f"An internal server error occurred: {e}"})
        response.status_code = HTTPStatus.INTERNAL_SERVER_ERROR
        return response


@firestore.transactional
def _put_address_transaction(
    transaction, db: firestore.Client, device: Device, new_address: str
):
    device_query = (
        db.collection(DEVICE_COLLECTION)
        .where(filter=firestore.FieldFilter("model", "==", device.model.value))
        .where(filter=firestore.FieldFilter("serialNumber", "==", device.serial_number))
        .limit(1)
    )
    docs_stream = device_query.stream(transaction=transaction)
    documents = list(docs_stream)
    if len(documents) > 1:
        raise FirestoreError(
            f"Multiple devices with this serial number exist: {device.model.value}-{device.serial_number}"
        )
    elif not documents:
        raise FirestoreError(
            f"No document found with serial number {device.model.value}-{device.serial_number} in collection '{DEVICE_COLLECTION}'."
        )
    else:
        document_ref = documents[0].reference
        transaction.update(document_ref, {"address": new_address})
