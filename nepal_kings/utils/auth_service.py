# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
from utils import http_compat as requests
from config import settings

def send_heartbeat(username):
    """Ping the server to mark this user as online."""
    try:
        requests.post(f'{settings.SERVER_URL}/auth/heartbeat',
                      data={'username': username}, timeout=3)
    except Exception:
        pass

def fetch_rankings():
    """Fetch the leaderboard data for all players."""
    try:
        response = requests.get(f'{settings.SERVER_URL}/auth/get_rankings', timeout=5)
        response.raise_for_status()
        return response.json().get('rankings', [])
    except Exception:
        return []

def login(username, password):
    try:
        response = requests.post(f'{settings.SERVER_URL}/auth/login', data={'username': username, 'password': password}, timeout=10)

        # Check if the response indicates a failure due to wrong credentials (401 Unauthorized)
        if response.status_code == 401:
            return {'success': False, 'message': 'Login failed. Username or password incorrect'}

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


def register(username, password):
    try:
        response = requests.post(f'{settings.SERVER_URL}/auth/register', data={'username': username, 'password': password}, timeout=10)

        # Check for username conflicts (409 Conflict)
        if response.status_code == 409:
            return {'success': False, 'message': 'Registration failed. Username already exists.'}

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
