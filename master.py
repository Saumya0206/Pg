from flask import Flask, render_template, request, redirect, jsonify
from flask_cors import CORS
from flask_pymongo import PyMongo, MongoClient
from pymongo.errors import OperationFailure
from urllib.parse import quote_plus
import subprocess
import time
import os
import threading
import requests
import websockets
import asyncio
import json
from datetime import datetime
import pytz
import secrets
import string

app = Flask(__name__)
CORS(app)

# Replace <YOUR_USERNAME> and <YOUR_PASSWORD> with your MongoDB Atlas credentials
username = "soumya"
password = "OQCgHTKKCTloVys4"
cluster_name = "cluster0.yojnkbb.mongodb.net"
dbname = "test"
# Escape the username and password using urllib.parse.quote_plus
escaped_username = quote_plus(username)
escaped_password = quote_plus(password)
mongo_uri = f"mongodb+srv://{username}:{password}@{cluster_name}/{dbname}?retryWrites=true&w=majority"

app.config["MONGO_URI"] = mongo_uri
try:
    # Connect to MongoDB using the configured URI
    mongo_client = MongoClient(mongo_uri)
    db = mongo_client["DB"]  # Get the default database
    collection = db["CtrlB-Playground"]  # Use the "entries" collection for storing entries
    print("Connected to MongoDB Atlas successfully!")
except OperationFailure as e:
    print("Failed to connect to MongoDB Atlas:")
    print(f"Error message: {e.details['errmsg']}")
    print(f"Error code: {e.details['code']}")
    print(f"Error code name: {e.details['codeName']}")

# Flag to signal the port_watcher thread to stop
stop_port_watcher = False
DB = {}
# DB = {
#   email:   {
#       "port": port,
#       "pid": pid,
#       "timestamp": timestamp,
#       "websocket": websocket,
#       }
#   }
PORTS_TO_EMAIL_MAP = {}
# {port:email}

def add_entry(email):
    entry = {
        "email": email,
    }
    collection.insert_one(entry)

def get_entry(email):
    return collection.find_one({"email": email})

def delete_entry(email):
    collection.delete_one({"email": email})

def get_email_for_port(port):
    email = ""
    print("map here", PORTS_TO_EMAIL_MAP)
    if port in PORTS_TO_EMAIL_MAP:
        email = PORTS_TO_EMAIL_MAP[port]
    else:
        print(f"Something wrong! port: {port} not recognized")
    return email
    
def get_public_ip():
    response = requests.get("https://api64.ipify.org?format=json")
    data = response.json()
    ip_address = data["ip"]
    # return "ec2-43-204-221-58.ap-south-1.compute.amazonaws.com"
    # return "localhost"
    return ip_address

def get_free_port(email):
    """Find and return an available free port."""
    global PORTS_TO_EMAIL_MAP
    for port in range(9000, 10000):
        if port not in PORTS_TO_EMAIL_MAP:
            PORTS_TO_EMAIL_MAP[port] = email
            return port
    return None

def start_new_target_app(free_port, email):
    """Start a new instance of target_app."""
    if free_port is None:
        return None, None
    # Set the timestamp in the DB dictionary when a new app is started
    timestamp = time.time()
    command = ["node", "Server/server.js", str(free_port)]
    process = subprocess.Popen(command, cwd="target_app")
    print("Sleeping for 2 seconds...")
    time.sleep(2)
    return process.pid, timestamp

def cleanup_stale_ports():
    """Clean up ports for entries older than an hour in the DB."""
    now = time.time()
    for email, info in list(DB.items()):
        port, pid, timestamp = info["port"], info["pid"], info.get("timestamp", 0)
        if now - timestamp > 60:  # Check if the port was used for more than an hour
            print(f"Cleaning up port {port} for email {email}")
            try:
                os.kill(pid, 9)  # Send SIGKILL signal to terminate the process
                print(f"Process with PID {pid} killed")
            except Exception as e:
                print(f"Failed to kill process with PID {pid}: {e}")
            del DB[email]  # Remove the entry from the dictionary
            del PORTS_TO_EMAIL_MAP[port] # Free up the port in the PORTS_TO_EMAIL_MAP

def port_watcher(DB):
    """Periodically check and clean up stale ports."""
    global stop_port_watcher
    while not stop_port_watcher:
        print("Running port watcher...")
        if not DB:  # Check if DB is empty
            print("DB is empty")
        else:
            print(f"length = {len(DB.items())}")
        cleanup_stale_ports()
        time.sleep(60)  # Check every 60 seconds

def check_server_availability(port):
    """Check if the target_app server is responsive."""
    try:
        response = requests.get(f"http://localhost:{port}/ping")
        return response.status_code == 200
    except requests.exceptions.RequestException:
        return False


CODE_TO_DEBUG = "https://api.github.com/repos/abc/aaa/contents/Server/Routes/api.js"
LINENO_TO_TRACEPOINTID_MAP = {}
REQUESTID_TO_LINENO_MAP = {}


def get_time():
    current_time = datetime.now(pytz.utc)
    timezone = pytz.timezone("Europe/London")  # Replace "Your_Timezone" with the desired timezone
    localized_time = current_time.astimezone(timezone)
    return localized_time.strftime("%Y-%m-%d %H:%M:%S %Z%z")

def generate_random_string(length):
    characters = string.ascii_letters + string.digits
    random_string = ''.join(secrets.choice(characters) for _ in range(length))
    return random_string

async def websocket_handler(websocket, path):
    global DB
    global REQUESTID_TO_LINENO_MAP
    assert path == "/ws/app"
    async for message in websocket:
        message_json = json.loads(message)
        print("Received:", message_json)
        if message_json["name"]=="FilterTracePointsRequest":
            # When the agent starts it sends this request
            # So we can save the websocket for this port and email
            port = int(message_json["applicationFilter"]["name"])
            email = get_email_for_port(port)
            # TODO MUTEX!!!!
            if email in DB:
                DB[email]["websocket"] = websocket
            else:
                print(f"Something wrong! email: {email} for port: {port} not recognized")



        if(message_json["name"] in ["TracePointSnapshotEvent"] ):
            live_message = {}
            live_message["timestamp"] = get_time()
            live_message["fileName"] = message_json["fileName"][:message_json["fileName"].index("?")]
            live_message["methodName"] = message_json["methodName"]
            live_message["lineNo"] = message_json["lineNo"]
            # live_message["traceId"] = message_json["traceId"]
            # live_message["spanId"] = message_json["spanId"]
            if len(message_json["frames"])>0 and "variables" in message_json["frames"][0]:
                live_message["variables"] = message_json["frames"][0]["variables"]
        # if(message_json["name"] == "PutTracePointResponse"):
        #     if(message_json["erroneous"]==False):
        #         lineno = REQUESTID_TO_LINENO_MAP[message_json["requestId"]]
        #         del REQUESTID_TO_LINENO_MAP[message_json["requestId"]]
        # if(message_json["name"] == "RemoveTracePointResponse"):
        #     if(message_json["erroneous"]==False):
        #         lineno = REQUESTID_TO_LINENO_MAP[message_json["requestId"]]
        #         del REQUESTID_TO_LINENO_MAP[message_json["requestId"]]

# start a WebSocket server on a thread
def run_websocket_server():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    start_server = websockets.serve(websocket_handler, 'localhost', 8094)
    print("WebSocket server running...")
    loop.run_until_complete(start_server)
    loop.run_forever()



async def _serialize_and_send(client_websocket, message_json):
    message_serialized = json.dumps(message_json)

    await client_websocket.send(message_serialized)

async def sendPutTracepoint(line_no, port):
    global LINENO_TO_TRACEPOINTID_MAP
    global REQUESTID_TO_LINENO_MAP
    email = get_email_for_port(port)
    if email not in DB or DB[email]["websocket"] is None:
        print(f"Unrecognized email: {email}")
        return
    client_websocket = DB[email]["websocket"]
    tracePointId = generate_random_string(7)
    requestId = generate_random_string(7)
    message_json = {
        "name":"PutTracePointRequest",
        "type":"Request",
        "id":requestId,
        "client":"simulated_client_api",
        "tracePointId":tracePointId,
        "fileName":f"{CODE_TO_DEBUG}?ref=REF",
        "lineNo":line_no,
        "enableTracing":True,
        "conditionExpression":None,
    }
    await _serialize_and_send(client_websocket, message_json)
    LINENO_TO_TRACEPOINTID_MAP[line_no] = tracePointId
    REQUESTID_TO_LINENO_MAP[requestId] = line_no

async def sendRemoveTracepoint(line_no):
    global REQUESTID_TO_LINENO_MAP
    tracePointId = LINENO_TO_TRACEPOINTID_MAP[line_no]
    requestId = generate_random_string(7)
    message_json = {
        "name":"RemoveTracePointRequest",
        "type":"Request",
        "id":requestId,
        "client":"simulated_client_api",
        "tracePointId":tracePointId,
        "fileName":f"{CODE_TO_DEBUG}?ref=REF",
        "lineNo":line_no,
        "enableTracing":True,
        "conditionExpression":None,
    }
    await _serialize_and_send(message_json)
    REQUESTID_TO_LINENO_MAP[requestId] = line_no


@app.route('/tracepoint', methods=['POST'])
def receive_request():
    data = request.get_json()
    port = int(data.get('port'))
    lineNumber = data.get('lineNumber')
    print(f"Received request from port {port} for line number {lineNumber}")
    # Code to handle the received request 
    asyncio.run(sendPutTracepoint(lineNumber, port))
    response_data = {'message': 'Request received successfully!'}
    return jsonify(response_data), 200

# @app.route('/removetracepoint', methods=['POST'])
# def remove_tracepoint():
#     data = request.get_json()
#     port = data.get('port')
#     lineNumber = data.get('lineNumber')
#     print(f"Received request to remove tracepoint from port {port} for line number {lineNumber}")

#     # Call the function to send the RemoveTracepoint request
#     asyncio.run(sendRemoveTracepoint(port, lineNumber))

#     response_data = {'message': 'Request received successfully!'}
#     return jsonify(response_data), 200


@app.route("/", methods=["GET", "POST"])
def index():
    global DB
    if request.method == "POST":
        # Handle the submitted email address
        email = request.form.get("email")
        print("here is DB",DB)
        if email not in DB:
            # Spin a new server here
            free_port = get_free_port(email)
            DB[email] = {
                "port": free_port,
            }
            if free_port:
                pid, timestamp = start_new_target_app(free_port, email)
            if pid:
                DB[email]["pid"] = pid
                DB[email]["timestamp"] = timestamp
                add_entry(email)
            else:
                del DB[email]
                return "No free ports available at the moment. Please try again later.", 500
            print(f"New target_app started on port {free_port} with process id {pid}")
        else:
            # If the email already exists, update the "timestamp"
            DB[email]["timestamp"] = time.time()
            print(f"Timestamp updated for email {email}")
        port = DB[email]["port"]
        if not DB:  # Check if DB is empty
            print("DB is empty index")
        else:
            print(f"length index = {len(DB.items())}")
        # Check if the target_app server is responsive
        if check_server_availability(port):
            return render_template("tic-tac-toe.html", port=port, server_url=f"http://{get_public_ip()}")
        else:
            # If the server is not responsive, redirect to index.html
            print("error")
            return f"Failed to get data from localhost:{port}", 500
    else:
        # If the request is a GET, we render the HTML form asking for the email.
        return render_template("index.html")
    
if __name__ == "__main__":
    # Start the port watcher as a separate thread
    watcher_thread = threading.Thread(target=port_watcher, args=(DB,), daemon=True)
    watcher_thread.start()
    websocket_thread = threading.Thread(target=run_websocket_server)
    websocket_thread.start()
    try:
        app.run(debug=False, port=5001, host="0.0.0.0")
    except KeyboardInterrupt:
        # Set the stop_port_watcher flag to signal the port_watcher thread to stop
        stop_port_watcher=True
        # watcher_thread.join()  