import flask
import pytest
from unittest.mock import MagicMock, patch
from http import HTTPStatus

from api_handler import get, put, post, _post_transaction
from address_api_handler import get_address, put_address, _get_address_transaction
from menu import (
    CONFIG_COLLECTION,
    DEVICE_COLLECTION,
    Config,
    Device,
    FirestoreError,
    Model,
)

# --- Fixtures ---


@pytest.fixture
def mock_db():
    """Fixture for a mocked Firestore client."""
    return MagicMock()


@pytest.fixture
def app_context():
    """Fixture to create a Flask application context for tests that need it."""
    app = flask.Flask(__name__)
    with app.app_context():
        yield


@pytest.fixture
def sample_device():
    """A sample Device object for testing."""
    return Device(model=Model.IchibuV1, serial_number="test-serial-123")


@pytest.fixture
def sample_config_data():
    """A sample config data dictionary, as received from a client."""
    return {
        "gain": 1.0,
        "ingredient": "coffee",
        "loadCellId": 12345,
        "location": "counter",
        "offset": 0.5,
        "phidgetId": 67890,
        "heartbeatPeriod": {"secs": 30, "nanos": 0},
        "phidgetSamplePeriod": {"secs": 1, "nanos": 0},
        "maxNoise": 0.01,
        "bufferLength": 10,
    }


@pytest.fixture
def sample_config(sample_config_data):
    """A sample Config Pydantic object."""
    return Config.model_validate(sample_config_data)


# --- Helper Functions ---


def create_mock_request(path, method="GET", json_data=None):
    """Helper to create a mock Flask request."""
    req = MagicMock(spec=flask.Request)
    req.path = path
    req.method = method
    req.get_json.return_value = json_data
    return req


def create_mock_firestore_doc(data, doc_id="some-doc-id"):
    """Helper to create a mock Firestore document snapshot."""
    doc = MagicMock()
    doc.to_dict.return_value = data
    doc.id = doc_id
    doc.exists = True
    doc.reference = MagicMock()
    return doc


# --- Tests for api_handler.py ---


class TestApiHandler:
    @patch("api_handler.path_to_device")
    @patch("api_handler._get_transaction")
    def test_get_success(
        self, mock_get_transaction, mock_path_to_device, mock_db, app_context, sample_device, sample_config
    ):
        # Arrange
        mock_path_to_device.return_value = sample_device
        mock_get_transaction.return_value = sample_config
        request = create_mock_request(path=f"/{sample_device.model.value}/{sample_device.serial_number}")

        # Act
        response = get(request, mock_db)

        # Assert
        mock_path_to_device.assert_called_once_with(request.path)
        mock_db.transaction.assert_called_once()
        mock_get_transaction.assert_called_once_with(mock_db.transaction(), mock_db, sample_device)
        assert response.status_code == HTTPStatus.OK
        assert response.json == sample_config.to_client_dict()

    @patch("api_handler.path_to_device")
    @patch("api_handler._get_transaction", side_effect=FirestoreError("Device not found"))
    def test_get_device_not_found(self, mock_get_transaction, mock_path_to_device, mock_db, app_context, sample_device):
        # Arrange
        mock_path_to_device.return_value = sample_device
        request = create_mock_request(path=f"/{sample_device.model.value}/{sample_device.serial_number}")

        # Act
        response = get(request, mock_db)

        # Assert
        assert response.status_code == HTTPStatus.NOT_FOUND
        assert "Device not found" in response.json["error"]

    @patch("api_handler.path_to_device", side_effect=ValueError("Invalid path"))
    def test_get_invalid_path(self, mock_path_to_device, mock_db, app_context):
        # Arrange
        request = create_mock_request(path="/invalid/path/format")

        # Act
        response = get(request, mock_db)

        # Assert
        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert "Invalid path" in response.json["error"]

    @patch("api_handler.path_to_device")
    @patch("api_handler._put_transaction")
    def test_put_success(
        self, mock_put_transaction, mock_path_to_device, mock_db, app_context, sample_device, sample_config_data
    ):
        # Arrange
        mock_path_to_device.return_value = sample_device
        request = create_mock_request(
            path=f"/{sample_device.model.value}/{sample_device.serial_number}",
            method="PUT",
            json_data=sample_config_data,
        )

        # Act
        response = put(request, mock_db)

        # Assert
        mock_path_to_device.assert_called_once_with(request.path)
        mock_db.transaction.assert_called_once()
        # The config object is created inside put(), so we check it was called with a Config instance
        mock_put_transaction.assert_called_once()
        call_args = mock_put_transaction.call_args[0]
        assert isinstance(call_args[3], Config)
        assert response.status_code == HTTPStatus.OK
        assert "updated successfully" in response.json["message"]

    @patch("api_handler.path_to_device")
    def test_put_invalid_json(self, mock_path_to_device, mock_db, app_context, sample_device):
        # Arrange
        mock_path_to_device.return_value = sample_device
        request = create_mock_request(
            path=f"/{sample_device.model.value}/{sample_device.serial_number}",
            method="PUT",
            json_data={"invalid": "data"},
        )

        # Act
        response = put(request, mock_db)

        # Assert
        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert "Bad Request" in response.json["error"]

    @patch("api_handler._post_transaction")
    def test_post_success(self, mock_post_transaction, mock_db, app_context, sample_config_data, sample_device):
        # Arrange
        mock_post_transaction.return_value = sample_device
        request = create_mock_request(path=f"/{Model.IchibuV1.value}", method="POST", json_data=sample_config_data)

        # Act
        response = post(request, mock_db)

        # Assert
        mock_db.transaction.assert_called_once()
        mock_post_transaction.assert_called_once()
        assert response.status_code == HTTPStatus.CREATED
        assert response.json == sample_device.model_dump()

    def test_post_transaction_no_collision(self, mock_db, sample_config):
        # Arrange
        transaction = MagicMock()
        model = Model.IchibuV1
        base_serial = f"{sample_config.phidget_id}-{sample_config.load_cell_id}"

        mock_device_collection = MagicMock()
        mock_config_collection = MagicMock()
        mock_db.collection.side_effect = lambda name: {
            DEVICE_COLLECTION: mock_device_collection,
            CONFIG_COLLECTION: mock_config_collection,
        }[name]

        mock_query = MagicMock()
        mock_device_collection.where.return_value = mock_query
        mock_query.stream.return_value = []  # No collision

        mock_config_doc_ref = MagicMock()
        mock_config_doc_ref.id = "new-config-id"
        mock_config_collection.document.return_value = mock_config_doc_ref
        mock_device_collection.document.return_value = MagicMock()

        # Act
        new_device = _post_transaction(transaction, mock_db, model, sample_config)

        # Assert
        mock_device_collection.where.assert_called_once()
        assert mock_device_collection.where.call_args[1]["filter"].value == base_serial
        assert new_device.serial_number == base_serial

    def test_post_transaction_serial_collision(self, mock_db, sample_config):
        # Arrange
        transaction = MagicMock()
        model = Model.IchibuV1
        base_serial = f"{sample_config.phidget_id}-{sample_config.load_cell_id}"

        mock_device_collection = MagicMock()
        mock_config_collection = MagicMock()
        mock_db.collection.side_effect = lambda name: {
            DEVICE_COLLECTION: mock_device_collection,
            CONFIG_COLLECTION: mock_config_collection,
        }[name]

        mock_query = MagicMock()
        mock_device_collection.where.return_value = mock_query
        mock_query.stream.side_effect = [[create_mock_firestore_doc({})], []]  # Collision, then no collision

        mock_config_doc_ref = MagicMock()
        mock_config_doc_ref.id = "new-config-id"
        mock_config_collection.document.return_value = mock_config_doc_ref
        mock_device_collection.document.return_value = MagicMock()

        # Act
        new_device = _post_transaction(transaction, mock_db, model, sample_config)

        # Assert
        assert len(mock_device_collection.where.call_args_list) == 2
        assert mock_device_collection.where.call_args_list[0][1]["filter"].value == base_serial
        assert mock_device_collection.where.call_args_list[1][1]["filter"].value == f"{base_serial}-0"
        assert new_device.serial_number == f"{base_serial}-0"


# --- Tests for address_api_handler.py ---


class TestAddressApiHandler:
    @patch("address_api_handler.path_to_device")
    @patch("address_api_handler._get_address_transaction")
    def test_get_address_success(self, mock_get_address, mock_path_to_device, mock_db, app_context, sample_device):
        # Arrange
        mock_path_to_device.return_value = sample_device
        expected_address = "192.168.1.100"
        mock_get_address.return_value = expected_address
        request = create_mock_request(path=f"/address/{sample_device.model.value}/{sample_device.serial_number}")

        # Act
        response = get_address(request, mock_db)

        # Assert
        mock_path_to_device.assert_called_once_with(f"/{sample_device.model.value}/{sample_device.serial_number}")
        mock_db.transaction.assert_called_once()
        mock_get_address.assert_called_once_with(mock_db.transaction(), mock_db, sample_device)
        assert response.status_code == HTTPStatus.OK
        assert response.json == {"address": expected_address}

    @patch("address_api_handler.path_to_device")
    @patch("address_api_handler._get_address_transaction", side_effect=FirestoreError("Device not found"))
    def test_get_address_not_found(self, mock_get_address, mock_path_to_device, mock_db, app_context, sample_device):
        # Arrange
        mock_path_to_device.return_value = sample_device
        request = create_mock_request(path=f"/address/{sample_device.model.value}/{sample_device.serial_number}")

        # Act
        response = get_address(request, mock_db)

        # Assert
        assert response.status_code == HTTPStatus.NOT_FOUND
        assert "Device not found" in response.json["error"]

    def test_get_address_transaction_no_address_field(self, mock_db, sample_device):
        # Arrange
        transaction = MagicMock()
        mock_doc = create_mock_firestore_doc({"some_other_field": "value"})  # No 'address' field
        mock_query = MagicMock()
        mock_query.stream.return_value = [mock_doc]
        mock_db.collection.return_value.where.return_value.where.return_value.limit.return_value = mock_query

        # Act & Assert
        with pytest.raises(FirestoreError, match="Device has no configured address"):
            _get_address_transaction(transaction, mock_db, sample_device)
        mock_query.stream.assert_called_once_with(transaction=transaction)

    @patch("address_api_handler.path_to_device")
    @patch("address_api_handler._put_address_transaction")
    def test_put_address_success(self, mock_put_address, mock_path_to_device, mock_db, app_context, sample_device):
        # Arrange
        mock_path_to_device.return_value = sample_device
        new_address = "192.168.1.200"
        request = create_mock_request(
            path=f"/address/{sample_device.model.value}/{sample_device.serial_number}",
            method="PUT",
            json_data={"address": new_address},
        )

        # Act
        response = put_address(request, mock_db)

        # Assert
        mock_path_to_device.assert_called_once_with(f"/{sample_device.model.value}/{sample_device.serial_number}")
        mock_db.transaction.assert_called_once()
        mock_put_address.assert_called_once_with(mock_db.transaction(), mock_db, sample_device, new_address)
        assert response.status_code == HTTPStatus.OK
        assert response.get_data(as_text=True) == "Successfully updated address."

    @patch("address_api_handler.path_to_device")
    def test_put_address_invalid_json(self, mock_path_to_device, mock_db, app_context, sample_device):
        # Arrange
        mock_path_to_device.return_value = sample_device
        request = create_mock_request(
            path=f"/address/{sample_device.model.value}/{sample_device.serial_number}",
            method="PUT",
            json_data={"wrong_key": "value"},
        )

        # Act
        response = put_address(request, mock_db)

        # Assert
        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert "Invalid JSON body" in response.json["error"]