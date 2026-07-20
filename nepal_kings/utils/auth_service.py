# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
from utils import http_compat as requests
from config import settings


def _server_error(response, fallback):
    """Return a safe server-provided error instead of a generic HTTP failure."""
    try:
        payload = response.json()
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}

    result = {
        'success': False,
        'message': payload.get('message') or fallback,
    }
    for key in ('reason', 'retryable', 'request_id'):
        if key in payload:
            result[key] = payload[key]

    try:
        retry_after = response.headers.get('Retry-After')
    except Exception:
        retry_after = None
    if retry_after:
        result['retry_after'] = retry_after
    return result


def send_heartbeat(username=None):
    """Ping the server to mark this user as online.

    The token is sent automatically via http_compat's Authorization header;
    the username parameter is kept for backward compatibility but ignored.
    """
    try:
        requests.post(f'{settings.SERVER_URL}/auth/heartbeat', timeout=3)
    except Exception:
        pass

def fetch_rankings():
    """Fetch the leaderboard data for all players."""
    try:
        response = requests.get(f'{settings.SERVER_URL}/auth/get_rankings', timeout=5)
        response.raise_for_status()
        return response.json().get('rankings', [])
    except Exception:
        return None


def fetch_kingdom_rankings():
    """Fetch the kingdom leaderboard data for all players."""
    try:
        response = requests.get(f'{settings.SERVER_URL}/kingdom/rankings', timeout=5)
        response.raise_for_status()
        return response.json().get('rankings', [])
    except Exception:
        return None

def login(username, password):
    try:
        response = requests.post(f'{settings.SERVER_URL}/auth/login', data={'username': username, 'password': password}, timeout=10)

        # Check if the response indicates a failure due to wrong credentials (401 Unauthorized)
        if response.status_code == 401:
            return {'success': False, 'message': 'Login failed. Username or password incorrect'}

        if response.status_code == 503:
            return _server_error(
                response,
                'Nepal Kings is temporarily unavailable. Please try again later.',
            )

        # If the status code is not 200, raise an exception for other kinds of errors
        response.raise_for_status()

        # Parse the response data
        response_data = response.json()

        # Check for success in the server's response
        if response_data.get('success'):
            return response_data
        else:
            return {'success': False, 'message': 'Login failed. Please try again.'}

    except requests.HTTPError as e:
        # Catch specific HTTP errors like 500, 404, or others, and provide a more user-friendly message
        print(f"HTTP error occurred: {str(e)}")
        return {'success': False, 'message': 'Login failed. Please check your internet connection or try again later.'}

    except requests.RequestException as e:
        # Catch general network errors or other issues
        print(f"Network error occurred: {str(e)}")
        return {'success': False, 'message': 'Login failed. Please check your internet connection or try again later.'}


def register(username, password, email=None, legal_confirmed=False):
    try:
        data = {
            'username': username,
            'password': password,
            'age_confirmed': 'true' if legal_confirmed else 'false',
            'terms_accepted': 'true' if legal_confirmed else 'false',
            'privacy_accepted': 'true' if legal_confirmed else 'false',
        }
        if email:
            data['email'] = email
        response = requests.post(f'{settings.SERVER_URL}/auth/register', data=data, timeout=10)

        # Check for username conflicts (409 Conflict)
        if response.status_code == 409:
            return {'success': False, 'message': 'Registration failed. Username already exists.'}

        if response.status_code == 503:
            return _server_error(
                response,
                'Registration is temporarily unavailable. Please try again later.',
            )

        # Handle validation errors (400) — read the server's message
        if response.status_code == 400:
            try:
                msg = response.json().get('message', 'Registration failed.')
            except Exception:
                msg = 'Registration failed.'
            return {'success': False, 'message': msg}

        # If the status code is not 200, raise an exception for other kinds of errors
        response.raise_for_status()

        # Parse the response data
        response_data = response.json()

        # Check for success in the server's response
        if response_data.get('success'):
            return response_data
        else:
            return {'success': False, 'message': 'Registration failed. Please try again.'}

    except requests.HTTPError as e:
        # Catch specific HTTP errors like 500, 404, or others, and provide a more user-friendly message
        print(f"HTTP error occurred: {str(e)}")
        return {'success': False, 'message': 'Registration failed. Please check your internet connection or try again later.'}

    except requests.RequestException as e:
        # Catch general network errors or other issues
        print(f"Network error occurred: {str(e)}")
        return {'success': False, 'message': 'Registration failed. Please check your internet connection or try again later.'}


def set_notifications(enabled):
    """Toggle gameplay notification emails for the logged-in user.

    Returns the server's notify_emails_enabled value, or None on failure.
    """
    try:
        response = requests.post(
            f'{settings.SERVER_URL}/auth/set_notifications',
            data={'enabled': 'true' if enabled else 'false'},
            timeout=5,
        )
        data = response.json()
        if data.get('success'):
            return bool(data.get('notify_emails_enabled'))
    except Exception:
        pass
    return None
