import unittest
from unittest.mock import MagicMock, patch, ANY
import flask
from http import HTTPStatus
from pydantic import ValidationError

# Import the functions and classes to be tested
from api_handler import get, put, post
from menu import (
    CONFIG_COLLECTION,
    DEVICE_COLLECTION,
    Config,
    Device,
    FirestoreError,
    Model,
)


class TestGetHandler(unittest.TestCase):
    """Tests for the GET request handler."""

    def setUp(self):
        """Set up a mock Flask app context and a mock Firestore client."""
        self.app = flask.Flask(__name__)
        self.mock_db = MagicMock()
        self.mock_transaction = MagicMock()
        self.mock_db.transaction.return_value = self.mock_transaction

    def test_get_success(self):
        """Test successful retrieval of a device's configuration."""
        # --- Setup Mocks ---
        # Mock the device document returned from the initial query
        mock_device_snapshot = MagicMock()
        mock_device_snapshot.to_dict.return_value = {
            "model": "IchibuV1",
            "number": 1,
            "config": "config123",
        }

        # Mock the config document that is fetched by reference
        mock_config_snapshot = MagicMock()
        mock_config_snapshot.exists = True
        mock_config_snapshot.to_dict.return_value = {
            "gain": 1.0,
            "ingredient": "salt",
            "loadCellId": 1,
            "location": "pantry",
            "offset": 0.0,
            "phidgetId": 123,
            "heartbeatPeriod": 30.0,
            "phidgetSamplePeriod": 0.1,
            "maxNoise": 0.5,
            "bufferLength": 10,
        }

        # Configure the mock DB client's chained calls
        mock_device_query = (
            self.mock_db.collection.return_value.where.return_value.where.return_value
        )
        mock_device_query.stream.return_value = [mock_device_snapshot]

        mock_config_ref = self.mock_db.collection.return_value.document.return_value
        mock_config_ref.get.return_value = mock_config_snapshot

        # --- Test Execution ---
        with self.app.test_request_context(path="/IchibuV1/1"):
            response = get(flask.request, self.mock_db)

        # --- Assertions ---
        self.assertEqual(response.status_code, HTTPStatus.OK)

        # Verify the response body is correctly serialized for the client
        expected_json = {
            "buffer_length": 10,
            "gain": 1.0,
            "heartbeat_period": {"secs": 30, "nanos": 0},
            "ingredient": "salt",
            "load_cell_id": 1,
            "location": "pantry",
            "max_noise": 0.5,
            "offset": 0.0,
            "phidget_id": 123,
            "phidget_sample_period": {"secs": 0, "nanos": 100000000},
        }
        self.assertEqual(response.get_json(), expected_json)

        # Verify transactionality
        mock_device_query.stream.assert_called_with(transaction=self.mock_transaction)
        mock_config_ref.get.assert_called_with(transaction=self.mock_transaction)

    def test_get_device_not_found(self):
        """Test GET request for a device that does not exist."""
        # Setup: The device query returns no documents
        mock_device_query = (
            self.mock_db.collection.return_value.where.return_value.where.return_value
        )
        mock_device_query.stream.return_value = []

        with self.app.test_request_context(path="/IchibuV1/99"):
            response = get(flask.request, self.mock_db)

        self.assertEqual(response.status_code, HTTPStatus.NOT_FOUND)
        self.assertIn("No document found", response.get_json()["error"])

    def test_get_multiple_devices_found(self):
        """Test GET request where a serial number matches multiple devices (data integrity issue)."""
        # Setup: The device query returns more than one document
        mock_device_query = (
            self.mock_db.collection.return_value.where.return_value.where.return_value
        )
        mock_device_query.stream.return_value = [MagicMock(), MagicMock()]

        with self.app.test_request_context(path="/IchibuV1/1"):
            response = get(flask.request, self.mock_db)

        self.assertEqual(response.status_code, HTTPStatus.NOT_FOUND)
        self.assertIn(
            "Multiple devices with this serial number exist",
            response.get_json()["error"],
        )

    def test_get_config_not_found(self):
        """Test GET request where the device document points to a non-existent config."""
        # Setup: Device exists, but its config document does not
        mock_device_snapshot = MagicMock()
        mock_device_snapshot.to_dict.return_value = {
            "model": "IchibuV1",
            "number": 1,
            "config": "config123",
        }

        mock_config_snapshot = MagicMock()
        mock_config_snapshot.exists = False  # The config document is missing

        mock_device_query = (
            self.mock_db.collection.return_value.where.return_value.where.return_value
        )
        mock_device_query.stream.return_value = [mock_device_snapshot]

        mock_config_ref = self.mock_db.collection.return_value.document.return_value
        mock_config_ref.get.return_value = mock_config_snapshot

        with self.app.test_request_context(path="/IchibuV1/1"):
            response = get(flask.request, self.mock_db)

        self.assertEqual(response.status_code, HTTPStatus.NOT_FOUND)
        self.assertIn(
            "Config document with ID config123 not found", response.get_json()["error"]
        )

    def test_get_bad_path(self):
        """Test GET request with a malformed path."""
        with self.app.test_request_context(path="/invalid_path"):
            response = get(flask.request, self.mock_db)

        self.assertEqual(response.status_code, HTTPStatus.BAD_REQUEST)
        self.assertIn("Invalid path format", response.get_json()["error"])


class TestPutHandler(unittest.TestCase):
    """Tests for the PUT request handler."""

    def setUp(self):
        self.app = flask.Flask(__name__)
        self.mock_db = MagicMock()
        self.mock_transaction = MagicMock()
        self.mock_db.transaction.return_value = self.mock_transaction

        # Common setup for a valid device and config reference
        mock_device_snapshot = MagicMock()
        mock_device_snapshot.to_dict.return_value = {
            "model": "IchibuV1",
            "number": 1,
            "config": "config123",
        }

        mock_device_query = (
            self.mock_db.collection.return_value.where.return_value.where.return_value
        )
        mock_device_query.stream.return_value = [mock_device_snapshot]

        self.mock_config_ref = (
            self.mock_db.collection.return_value.document.return_value
        )

    def test_put_success(self):
        """Test successful update of a device's configuration."""
        request_json = {
            "gain": 2.0,
            "ingredient": "sugar",
            "loadCellId": 2,
            "location": "shelf",
            "offset": 0.1,
            "phidgetId": 456,
            "heartbeatPeriod": {"secs": 60, "nanos": 0},
            "phidgetSamplePeriod": {"secs": 0, "nanos": 200000000},
            "maxNoise": 0.6,
            "bufferLength": 20,
        }

        with self.app.test_request_context(
            path="/IchibuV1/1", method="PUT", json=request_json
        ):
            response = put(flask.request, self.mock_db)

        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertIn("updated successfully", response.get_json()["message"])

        # Verify the data sent to Firestore is correctly serialized (e.g., timedelta -> float)
        expected_firestore_data = {
            "gain": 2.0,
            "ingredient": "sugar",
            "loadCellId": 2,
            "location": "shelf",
            "offset": 0.1,
            "phidgetId": 456,
            "heartbeatPeriod": 60.0,
            "phidgetSamplePeriod": 0.2,
            "maxNoise": 0.6,
            "bufferLength": 20,
        }
        self.mock_transaction.set.assert_called_once_with(
            self.mock_config_ref, expected_firestore_data
        )

    def test_put_invalid_json_body(self):
        """Test PUT request with a malformed or incomplete JSON body."""
        request_json = {"gain": 2.0}  # Missing required fields

        with self.app.test_request_context(
            path="/IchibuV1/1", method="PUT", json=request_json
        ):
            response = put(flask.request, self.mock_db)

        self.assertEqual(response.status_code, HTTPStatus.BAD_REQUEST)
        self.assertIn("Bad Request", response.get_json()["error"])

    def test_put_device_not_found(self):
        """Test PUT request for a device that does not exist."""
        # Override setup: device query returns no results
        self.mock_db.collection.return_value.where.return_value.where.return_value.stream.return_value = (
            []
        )

        # A valid JSON body is required to get past the initial Pydantic validation
        # and actually test the Firestore "not found" logic.
        valid_request_json = {
            "gain": 2.0,
            "ingredient": "sugar",
            "loadCellId": 2,
            "location": "shelf",
            "offset": 0.1,
            "phidgetId": 456,
            "heartbeatPeriod": {"secs": 60, "nanos": 0},
            "phidgetSamplePeriod": {"secs": 0, "nanos": 200000000},
            "maxNoise": 0.6,
            "bufferLength": 20,
        }

        # The original test sent `json={}`, which caused a ValidationError (400)
        # before the database was ever queried.
        with self.app.test_request_context(
            path="/IchibuV1/99", method="PUT", json=valid_request_json
        ):
            response = put(flask.request, self.mock_db)

        self.assertEqual(response.status_code, HTTPStatus.NOT_FOUND)
        self.assertIn("No document found", response.get_json()["error"])


class TestPostHandler(unittest.TestCase):
    """Tests for the POST request handler."""

    def setUp(self):
        self.app = flask.Flask(__name__)
        self.mock_db = MagicMock()
        self.mock_transaction = MagicMock()
        self.mock_db.transaction.return_value = self.mock_transaction

        self.new_config_data = {
            "gain": 1.0,
            "ingredient": "flour",
            "loadCellId": 1,
            "location": "bin",
            "offset": 0.0,
            "phidgetId": 789,
            "heartbeatPeriod": {"secs": 15, "nanos": 0},
            "phidgetSamplePeriod": {"secs": 0, "nanos": 50000000},
            "maxNoise": 0.2,
            "bufferLength": 5,
        }

    def test_post_success_first_device(self):
        """Test creating the very first device of a given model."""
        # Setup: Query for latest device returns nothing
        mock_latest_device_query = (
            self.mock_db.collection.return_value.where.return_value.order_by.return_value.limit.return_value
        )
        mock_latest_device_query.stream.return_value = []

        # Setup: Mock document creation
        mock_new_config_ref = MagicMock()
        mock_new_config_ref.id = "newConfigId"
        mock_new_device_ref = MagicMock()

        # Make collection('...').document() return the correct mock ref
        def document_side_effect():
            if self.mock_db.collection.call_args[0][0] == CONFIG_COLLECTION:
                return mock_new_config_ref
            return mock_new_device_ref

        self.mock_db.collection.return_value.document.side_effect = document_side_effect

        with self.app.test_request_context(
            path="/IchibuV1", method="POST", json=self.new_config_data
        ):
            response = post(flask.request, self.mock_db)

        self.assertEqual(response.status_code, HTTPStatus.CREATED)
        # The new device should be number 1
        self.assertEqual(response.get_json(), {"model": "IchibuV1", "number": 1})

        # Verify new device doc was created with correct data
        expected_device_doc = {
            "model": "IchibuV1",
            "number": 1,
            "config": "newConfigId",
        }
        self.mock_transaction.set.assert_any_call(
            mock_new_device_ref, expected_device_doc
        )

    def test_post_success_subsequent_device(self):
        """Test creating a new device when others of the same model already exist."""
        # Setup: Query for latest device returns device number 5
        mock_latest_device = MagicMock()
        mock_latest_device.get.return_value = 5

        mock_latest_device_query = (
            self.mock_db.collection.return_value.where.return_value.order_by.return_value.limit.return_value
        )
        mock_latest_device_query.stream.return_value = [mock_latest_device]

        with self.app.test_request_context(
            path="/IchibuV1", method="POST", json=self.new_config_data
        ):
            response = post(flask.request, self.mock_db)

        self.assertEqual(response.status_code, HTTPStatus.CREATED)
        # The new device should be number 6 (5 + 1)
        self.assertEqual(response.get_json(), {"model": "IchibuV1", "number": 6})
        mock_latest_device.get.assert_called_with("number")

    def test_post_invalid_model_in_path(self):
        """Test POST request with an invalid model name in the URL."""
        with self.app.test_request_context(
            path="/NotAModel", method="POST", json=self.new_config_data
        ):
            response = post(flask.request, self.mock_db)

        self.assertEqual(response.status_code, HTTPStatus.BAD_REQUEST)
        self.assertIn("Invalid model 'NotAModel' in path", response.get_json()["error"])

    def test_post_invalid_json_body(self):
        """Test POST request with an invalid JSON body."""
        invalid_json = {"gain": 1.0}  # Missing fields

        with self.app.test_request_context(
            path="/IchibuV1", method="POST", json=invalid_json
        ):
            response = post(flask.request, self.mock_db)

        self.assertEqual(response.status_code, HTTPStatus.BAD_REQUEST)
        self.assertIn("Invalid JSON body", response.get_json()["error"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
