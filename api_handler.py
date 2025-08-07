import flask
from http import HTTPStatus

from mypy.typeops import false_only
from pydantic import ValidationError
from menu import (
    CONFIG_COLLECTION,
    Config,
    path_to_device,
    DeserializationError,
    FirestoreError,
    Model,
    DEVICE_COLLECTION,
    FirestoreDeviceDocument,
    Device,
)
from google.cloud import firestore


@firestore.transactional
def _get_transaction(transaction, db: firestore.Client, device: Device) -> Config:
    device_query = (
        db.collection(DEVICE_COLLECTION)
        .where(filter=firestore.FieldFilter("model", "==", device.model.value))
        .where(filter=firestore.FieldFilter("serialNumber", "==", device.serial_number))
    )
    docs_stream = device_query.stream(transaction=transaction)
    documents = list(docs_stream)
    if len(documents) > 1:
        raise FirestoreError(
            f"Multiple devices with this serial number exist: {device.model.value}-{device.serial_number}"
        )
    if not documents:
        raise FirestoreError(
            f"No document found with serial number {device.model.value}-{device.serial_number} in collection '{DEVICE_COLLECTION}'."
        )

    device_document = FirestoreDeviceDocument.model_validate(documents[0].to_dict())
    config_doc_ref_str = device_document.to_config_ref()
    config_doc_ref = db.collection(CONFIG_COLLECTION).document(config_doc_ref_str)

    # Use transaction.get() for the second read
    config_snapshot = config_doc_ref.get(transaction=transaction)
    if not config_snapshot.exists:
        raise FirestoreError(f"Config document with ID {config_doc_ref_str} not found.")

    return Config.model_validate(config_snapshot.to_dict())


def get(request: flask.Request, db: firestore.Client) -> flask.Response:
    """
    Handles GET requests to fetch device configuration.
    """
    try:
        device = path_to_device(request.path)
        transaction = db.transaction()
        config = _get_transaction(transaction, db, device)
        print("CONFIG: ", config)
        # Use the new custom serializer for the client response
        response = flask.jsonify(config.to_client_dict())
        response.status_code = HTTPStatus.OK
        return response
    except (ValueError, DeserializationError) as e:
        response = flask.jsonify({"error": f"Bad Request: {e}"})
        response.status_code = HTTPStatus.BAD_REQUEST
        return response
    except FirestoreError as e:
        response = flask.jsonify({"error": str(e)})
        response.status_code = HTTPStatus.NOT_FOUND
        return response
    except Exception as e:
        print(f"CRITICAL: An unexpected error occurred in get(): {e}")
        response = flask.jsonify({"error": f"An internal server error occurred: {e}"})
        response.status_code = HTTPStatus.INTERNAL_SERVER_ERROR
        return response


@firestore.transactional
def _put_transaction(
    transaction, db: firestore.Client, device: Device, new_config: Config
):
    device_query = (
        db.collection(DEVICE_COLLECTION)
        .where(filter=firestore.FieldFilter("model", "==", device.model.value))
        .where(filter=firestore.FieldFilter("serialNumber", "==", device.serial_number))
    )
    docs_stream = device_query.stream(transaction=transaction)
    documents = list(docs_stream)

    if len(documents) > 1:
        raise FirestoreError(
            f"Multiple devices with this serial number exist: {device.model.value}-{device.serial_number}"
        )
    if not documents:
        raise FirestoreError(
            f"No document found with serial number {device.model.value}-{device.serial_number} in collection '{DEVICE_COLLECTION}'."
        )

    device_document = FirestoreDeviceDocument.model_validate(documents[0].to_dict())
    config_doc_ref = db.collection(CONFIG_COLLECTION).document(
        device_document.to_config_ref()
    )

    # Use transaction.set() for writes
    transaction.set(config_doc_ref, new_config.model_dump(by_alias=True))


def put(request: flask.Request, db: firestore.Client) -> flask.Response:
    """
    Handles PUT requests to update a device's config.
    """
    try:
        device = path_to_device(request.path)
        new_config = Config.model_validate(request.get_json())

        transaction = db.transaction()
        _put_transaction(transaction, db, device, new_config)

        response = flask.jsonify(
            {
                "message": f"Config for {device.model.value}-{device.serial_number} updated successfully."
            }
        )
        response.status_code = HTTPStatus.OK
        return response

    except (ValueError, ValidationError, DeserializationError) as e:
        response = flask.jsonify({"error": f"Bad Request: {e}"})
        response.status_code = HTTPStatus.BAD_REQUEST
        return response
    except FirestoreError as e:
        response = flask.jsonify({"error": str(e)})
        response.status_code = HTTPStatus.NOT_FOUND
        return response
    except Exception as e:
        print(f"CRITICAL: An unexpected error occurred in put(): {e}")
        response = flask.jsonify({"error": f"An internal server error occurred: {e}"})
        response.status_code = HTTPStatus.INTERNAL_SERVER_ERROR
        return response


@firestore.transactional
def _post_transaction(
    transaction, db: firestore.Client, model: Model, new_config: Config
) -> Device:
    """
    Creates a new config and a new device document within a transaction,
    preventing race conditions.
    """
    serial_number = f"{new_config.phidget_id}-{new_config.load_cell_id}"

    most_recent_device_query = (
        db.collection(DEVICE_COLLECTION)
        .where(filter=firestore.FieldFilter("serialNumber", "==", serial_number))
    )
    most_recent_device_stream = most_recent_device_query.stream(transaction=transaction)
    most_recent_device = list(most_recent_device_stream)

    if len(most_recent_device) > 0:
        serial_number_is_set = False
    else:
        serial_number_is_set = True
    index = 0
    while not serial_number_is_set:
        new_serial_number = f"{serial_number}-{index}"
        most_recent_device_query = db.collection(DEVICE_COLLECTION).where(
            filter=firestore.FieldFilter("serialNumber", "==", new_serial_number)
        )
        most_recent_device_stream = most_recent_device_query.stream(
            transaction=transaction
        )
        most_recent_device = list(most_recent_device_stream)
        if len(most_recent_device) > 0:
            index += 1
        else:
            serial_number_is_set = True
            serial_number = new_serial_number



    # 2. Create new config document
    new_config = Config.model_validate(new_config)
    new_config_doc_ref = db.collection(CONFIG_COLLECTION).document()
    transaction.set(new_config_doc_ref, new_config.model_dump(by_alias=True))

    # 3. Create new device document
    new_device_doc = FirestoreDeviceDocument.model_construct(
        model=model, serial_number=serial_number, config=new_config_doc_ref.id
    )
    new_device_doc_ref = db.collection(DEVICE_COLLECTION).document()
    transaction.set(new_device_doc_ref, new_device_doc.model_dump(by_alias=True))

    return new_device_doc.to_device()


def post(request: flask.Request, db: firestore.Client) -> flask.Response:
    try:
        model_str = request.path.split("/")[-1]
        model = Model[model_str]
        new_config_data = Config.model_validate(request.get_json())

        transaction = db.transaction()
        new_device = _post_transaction(transaction, db, model, new_config_data)

        return flask.make_response(new_device.model_dump(), HTTPStatus.CREATED)
    except (ValidationError, DeserializationError) as e:
        response = flask.jsonify({"error": f"Bad Request: Invalid JSON body. {e}"})
        response.status_code = HTTPStatus.BAD_REQUEST
        return response
    except KeyError:
        model_str = request.path.split("/")[-1]
        response = flask.jsonify(
            {"error": f"Bad Request: Invalid model '{model_str}' in path."}
        )
        response.status_code = HTTPStatus.BAD_REQUEST
        return response
    except Exception as e:
        print(f"CRITICAL: An unexpected error occurred in post(): {e}")
        response = flask.jsonify({"error": f"An internal server error occurred: {e}"})
        response.status_code = HTTPStatus.INTERNAL_SERVER_ERROR
        return response
