import os
import hmac
from typing import Tuple, Optional

def authenticate(request) -> Tuple[bool, Optional[Tuple[str, int]]]:
    """
    Checks for a valid Bearer token in the request header.

    This helper function encapsulates all authentication logic.

    Args:
        request (flask.Request): The incoming request object.

    Returns:
        A tuple containing a boolean and an optional error response.
        - (True, None) if authentication is successful.
        - (False, (error_message, status_code)) if authentication fails.
    """
    # Get the secret token from environment variables for security.
    expected_token = os.environ.get('AUTH_TOKEN')

    # 1. Check for server-side configuration issues.
    if not expected_token:
        print("CRITICAL: AUTH_TOKEN environment variable not set.\n")
        error = ("Internal Server Error: Server is not configured for authentication. \n", 500)
        return False, error

    # 2. Check for the presence and format of the Authorization header.
    auth_header = request.headers.get('Authorization')
    if not auth_header or not auth_header.startswith('Bearer '):
        error = ("Unauthorized: Missing or invalid Authorization header.\n", 401)
        return False, error

    # 3. Extract the token from the header.
    try:
        provided_token = auth_header.split('Bearer ')[1]
    except IndexError:
        error = ("Unauthorized: Malformed Authorization header.\n", 401)
        return False, error

    # 4. Securely compare the provided token against the expected one.
    if not hmac.compare_digest(provided_token, expected_token):
        error = ("Forbidden: Invalid token.\n", 403)
        return False, error

    # If all checks pass, authentication is successful.
    return True, None


def mise(request):
    """
    A cloud function that requires authentication.

    It calls a helper function to perform the auth check before
    proceeding with its main logic.

    Args:
        request (flask.Request): The request object.
            <http://flask.pocoo.org/docs/1.0/api/#flask.Request>

    Returns:
        The response text or a tuple of the response text and an HTTP
        status code.
    """
    # Call the authentication function first.
    is_authenticated, error_response = authenticate(request)

    # If authentication fails, immediately return the error response.
    if not is_authenticated:
        return error_response

    # --- Authentication successful ---
    # You can now proceed with the core logic of your function.
    return "Hello, Chef!"