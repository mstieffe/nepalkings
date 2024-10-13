import requests
from config import settings

def login(username, password):
    try:
        response = requests.post(f'{settings.SERVER_URL}/auth/login', data={'username': username, 'password': password})

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
        response = requests.post(f'{settings.SERVER_URL}/auth/register', data={'username': username, 'password': password})

        # Check for username conflicts (409 Conflict)
        if response.status_code == 409:
            return {'success': False, 'message': 'Registration failed. Username already exists.'}

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
