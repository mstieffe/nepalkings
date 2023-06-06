from flask import Flask, request, jsonify

app = Flask(__name__)

users = {}  # Dictionary to store user credentials

@app.route('/register', methods=['POST'])
def register():
    username = request.form.get('username')
    password = request.form.get('password')

    if username in users:
        return jsonify({'success': False, 'message': 'Username already exists'})

    users[username] = password
    return jsonify({'success': True, 'message': 'Registration successful'})

@app.route('/login', methods=['POST'])
def login():
    username = request.form.get('username')
    password = request.form.get('password')

    if username not in users or users[username] != password:
        return jsonify({'success': False, 'message': 'Invalid username or password'})

    return jsonify({'success': True, 'message': 'Login successful'})

if __name__ == '__main__':
    app.run(host='localhost', port=5000)