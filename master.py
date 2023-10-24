from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
from flask_pymongo import MongoClient
from pymongo.errors import OperationFailure
import subprocess
import time
import os
import requests
import asyncio
from datetime import datetime
import os
from dotenv import load_dotenv
from database import Database
from datetime import datetime
from portWatcher import clean_for_email, start_port_watcher
from webSocket import websocket, sendPutTracepoint,  sendRemoveTracepoint


# Load environment variables from the .env file
load_dotenv()

app = Flask(__name__)
CORS(app)

# Replace <YOUR_USERNAME> and <YOUR_PASSWORD> with your MongoDB Atlas credentials
username = os.getenv("DB_USERNAME")
password = os.getenv("DB_PASSWORD")
cluster_name = os.getenv("DB_CLUSTER")
dbname = os.getenv("DB_NAME")
start_port = int(os.getenv("START_PORT"))
end_port = int(os.getenv("END_PORT"))
kill_child_process_in_seconds = int(os.getenv("KILL_CHILD_PROCESS_IN_SECONDS"))
sleep_watcher_for_seconds = int(os.getenv("SLEEP_WATCHER_FOR_SECONDS"))

# Escape the username and password using urllib.parse.quote_plus
mongo_uri = f"mongodb+srv://{username}:{password}@{cluster_name}/{dbname}?retryWrites=true&w=majority"

app.config["MONGO_URI"] = mongo_uri
try:
    # Connect to MongoDB using the configured URI
    mongo_client = MongoClient(mongo_uri)
    db = mongo_client["CtrlB-Playground"]  # Get the default database
    collection = db[dbname]  # Use the "entries" collection for storing entries
    print(f"Connected to MongoDB Atlas successfully at cluster: {cluster_name}/{dbname}")
except OperationFailure as e:
    print("Failed to connect to MongoDB Atlas:")
    print(f"Error message: {e.details['errmsg']}")
    print(f"Error code: {e.details['code']}")
    print(f"Error code name: {e.details['codeName']}")

# Flag to signal the port_watcher thread to stop
stop_port_watcher = False
database = Database()
LAST_ACTIVE_PORT = None

tracepoint_events_by_port = {}  # {port: [live_message1, live_message2, ...]}

def add_email_in_persistent_db(email):
    # Check if the email exists in the collection
    existing_entry = collection.find_one({'email': email})
    current_timestamp = datetime.now()
    
    if existing_entry:
        # Email exists, update the entry
        new_times = existing_entry['times'] + 1
        
        collection.update_one(
            {'email': email},
            {'$set': {'times': new_times, 'latest_timestamp': current_timestamp}}
        )
        print(f"Updated entry for email: {email}")
    else:
        # Email doesn't exist, create a new entry
        new_entry = {
            'email': email,
            'times': 1,
            'latest_timestamp': current_timestamp  # Set the default timestamp value
        }
        collection.insert_one(new_entry)
        print(f"Created new entry for email: {email}")

# def get_public_ip():
#     response = requests.get("https://api64.ipify.org?format=json")
#     data = response.json()
#     ip_address = data["ip"]
#     # return "localhost"
#     return ip_address

def get_free_port(email):
    """Find and return an available free port."""
    global database
    while True:
        database.increment_last_active_port(start_port, end_port)
        print(email)
        port = database.get_last_active_port()
        if not database.check_port_in_use(port):
            return port

def start_new_target_app(free_port, email):
    """Start a new instance of target_app."""
    if free_port is None:
        return None, None
    # Set the timestamp in the DB dictionary when a new app is started
    timestamp = time.time()
    command = ["node", "Server/server.js", str(free_port)]
    process = subprocess.Popen(command, cwd="target_app")
    return process.pid, timestamp

def check_server_availability(port):
    """Check if the target_app server is responsive."""
    if port is None:
        return False
    try:
        response = requests.get(f"http://localhost:{port}/ping")
        return response.status_code == 200
    except requests.exceptions.RequestException:
        return False

@app.route('/tracepoint', methods=['POST'])
def receive_request():
    data = request.get_json()
    port = int(data.get('port'))
    lineNumber = data.get('lineNumber')+1
    print(f"Received request from port {port} for line number {lineNumber}")
    # Code to handle the received request 
    asyncio.run(sendPutTracepoint(lineNumber, port))
    response_data = {'message': 'Request received successfully!'}
    return jsonify(response_data), 200

@app.route('/removetracepoint', methods=['POST'])
def remove_tracepoint():
    data = request.get_json()
    port = data.get('port')
    lineNumber = data.get('lineNumber')+1
    print(f"Received request to remove tracepoint from port {port} for line number {lineNumber}")

     # Get the email associated with the port
    email = database.get_email_for_port(port)
    if email is not None:
        # Call the function to send the RemoveTracepoint request
        asyncio.run(sendRemoveTracepoint(email, lineNumber))
        response_data = {'message': f'RemoveTracepoint request sent for line number {lineNumber}'}
        return jsonify(response_data), 200
    else:
        response_data = {'message': 'Invalid port'}
        return jsonify(response_data), 400


@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        # Handle the submitted email address
        email = request.form.get("email")
        if database.check_email_in_db(email):
            clean_for_email(email, force=True)
        # Spin a new server here
        free_port = get_free_port(email)
        database.set_port_for_email(email, free_port)
        if free_port:
            pid, timestamp = start_new_target_app(free_port, email)
        if pid:
            database.set_pid_for_email(email, pid)
            database.set_timestamp_for_email(email, timestamp)
            add_email_in_persistent_db(email)
        else:
            database.delete_email(email)
            return "No free ports available at the moment. Please try again later.", 500
        print(f"New target_app started on port {free_port} with process id {pid}")
        port = database.get_port_for_email(email)
        return render_template("sandbox_under_construction.html", email = email)
    else:
        # If the request is a GET, we render the HTML form asking for the email.
        return render_template("index.html")
    
@app.route("/sandbox", methods=["GET", "POST"])
def sandbox():
    email = request.args.get("email")
    port = database.get_port_for_email(email)
    if os.getenv("ENV")=="DEV":
        target_app_server_url = f"{os.getenv('TARGET_APP_BASE_ADDRESS')}:{port}"
    if os.getenv("ENV")=="PROD":
        target_app_server_url = f"{os.getenv('TARGET_APP_BASE_ADDRESS')}/{port}"
    if port and check_server_availability(port):
        return render_template("tic-tac-toe.html", port=port, target_app_server_url=target_app_server_url)
    else:
        return f"This sandbox has been deleted. Please visit the homepage again.", 500
    
if __name__ == "__main__":
    # Start the port watcher as a separate thread
    start_port_watcher(database,kill_child_process_in_seconds)
    websocket(database)
    try:
        app.run(debug=False, port=5001, host="0.0.0.0")
    except KeyboardInterrupt:
        # Set the stop_port_watcher flag to signal the port_watcher thread to stop
        stop_port_watcher=True