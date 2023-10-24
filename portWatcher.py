import threading
import time
import os
# from master import Database

stop_port_watcher = False
database = None  # You will assign the 'database' object from master.py
kill_child_process_in_seconds=None
"""
Cleans the state for this email if the time has expired.
If force is set as True, forcefully kill without thinking about timestamp.

* kills process
* cleans DB
* cleans PORTS_TO_EMAIL_MAP
"""
def clean_for_email(email, force=False):
    global database  # Reference the 'database' object from master.py
    now = time.time()
    info = database.get_data_for_email(email)
    if not info:
        return
    try:
        port, pid, timestamp = info["port"], info["pid"], info.get("timestamp", 0)
        if force or (now - timestamp > kill_child_process_in_seconds):
            print(f"Cleaning up port {port} for email {email}")
            try:
                os.kill(pid, 9)
                print(f"Process with PID {pid} killed")
            except Exception as e:
                print(f"Failed to kill process with PID {pid}: {e}")
                print("here")
            database.delete_email(email)
    except:
        pass

def cleanup_stale_ports():
    global database  # Reference the 'database' object from master.py
    for email in database.get_all_emails():
        clean_for_email(email)

def port_watcher():
    global database
    global stop_port_watcher
    while not stop_port_watcher:
        cleanup_stale_ports()
        time.sleep(30)

def start_port_watcher(database_obj,kill_child_process_in_secs):
    global database
    global kill_child_process_in_seconds
    database = database_obj
    kill_child_process_in_seconds=kill_child_process_in_secs
    watcher_thread = threading.Thread(target=port_watcher, daemon=True)
    watcher_thread.start()