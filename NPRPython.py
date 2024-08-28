import os
import csv
import time
import pyodbc
import socket
from flask import Flask, request
import xml.etree.ElementTree as ET
from dotenv import load_dotenv
from apscheduler.schedulers.background import BackgroundScheduler

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)

# Define the IP camera server address and port from environment variables
SERVER_ADDRESS = os.getenv('SERVER_ADDRESS', '127.0.0.1')
SERVER_PORT = int(os.getenv('NPR_SERVER_PORT', 3065))

# Define the database configuration
sql_config = {
    'server': os.getenv('DB_SERVER'),
    'database': os.getenv('DB_DATABASE'),
    'username': os.getenv('DB_USER'),
    'password': os.getenv('DB_PASSWORD'),
    'driver': '{ODBC Driver 17 for SQL Server}'
}

# Define the file path for CSV storage
CSV_FILE_PATH = "data_backup.csv"

# Define the tags to capture
tags_to_capture = ['mac', 'sn', 'deviceName', 'plateNumber', 'targetType']

# Map to track the last 5 plate numbers for each `sn`
sn_plate_history = {}

def get_db_connection():
    connection_str = (
        f"DRIVER={sql_config['driver']};"
        f"SERVER={sql_config['server']};"
        f"DATABASE={sql_config['database']};"
        f"UID={sql_config['username']};"
        f"PWD={sql_config['password']}"
    )
    return pyodbc.connect(connection_str)

@app.route('/', methods=['POST'])
def handle_post():
    if request.method == 'POST':
        # Read XML data from request
        xml_data = request.data.decode('utf-8')
        root = ET.fromstring(xml_data)

        # Variables to store extracted values
        mac, sn, deviceName, plateNumber, targetType = None, None, None, None, None

        # Parse XML
        for elem in root.iter():
            if elem.tag in tags_to_capture:
                if elem.tag == 'plateNumber':
                    plateNumber = elem.text.strip() if elem.text else None
                elif elem.tag == 'targetType':
                    targetType = elem.text.strip() if elem.text else None
                else:
                    locals()[elem.tag] = elem.text.strip() if elem.text else None

        log_and_insert_into_database(mac, sn, deviceName, plateNumber, targetType)

        return 'Data processed', 200
    else:
        return 'Method Not Allowed', 405

def log_and_insert_into_database(mac, sn, deviceName, plateNumber, targetType):
    # Check for network availability
    network_available = check_network_status()

    # Save data to CSV regardless of network status
    save_to_csv(mac, sn, deviceName, plateNumber, targetType, flag=not network_available)

    if network_available and plateNumber and validate_plate_number(plateNumber):
        # Check the history of the plate numbers for the same `sn`
        plate_history = sn_plate_history.get(sn, [])

        # If plateNumber is in the last 5 entries for this `sn`, skip insertion
        if plateNumber in plate_history:
            print(f'plateNumber {plateNumber} already inserted for sn {sn} in the last 5 entries, skipping database insert.')
            return

        # Also check if the plateNumber exists in the last 5 entries of other `sn`
        for other_sn, other_plate_history in sn_plate_history.items():
            if other_sn != sn and plateNumber in other_plate_history:
                print(f'plateNumber {plateNumber} exists in the last 5 entries for a different sn, skipping database insert.')
                return

        # If the checks pass, insert into the database
        insert_into_database(mac, sn, deviceName, plateNumber, targetType)

        # Update the history for this `sn`
        plate_history.append(plateNumber)
        if len(plate_history) > 5:
            plate_history.pop(0)  # Keep only the last 5 entries
        sn_plate_history[sn] = plate_history
    else:
        print('plateNumber is either invalid or skipped due to the conditions.')

def check_network_status():
    try:
        # Attempt to resolve a hostname, Google DNS as a simple example
        socket.gethostbyname('8.8.8.8')
        return True
    except socket.error:
        return False

def save_to_csv(mac, sn, deviceName, plateNumber, targetType, flag):
    # Save data to a CSV file with a 'flag' column to indicate network status
    with open(CSV_FILE_PATH, 'a', newline='') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow([mac, sn, deviceName, plateNumber, targetType, flag])

def insert_into_database(mac, sn, deviceName, plateNumber, targetType):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Define the query to insert data into the table
        query = '''
        INSERT INTO dbo.NPRData (mac, sn, deviceName, plateNumber, targetType)
        VALUES (?, ?, ?, ?, ?)
        '''

        # Execute the query
        cursor.execute(query, (mac, sn, deviceName, plateNumber, targetType))
        conn.commit()
        cursor.close()
        conn.close()

        print('Data inserted successfully')
    except pyodbc.Error as e:
        print(f"Database insertion error: {e}")

def retry_flagged_data():
    # Check network status before retrying
    if check_network_status():
        # Read the CSV file and retry inserting flagged data
        new_rows = []
        with open(CSV_FILE_PATH, 'r', newline='') as csvfile:
            reader = csv.reader(csvfile)
            for row in reader:
                mac, sn, deviceName, plateNumber, targetType, flag = row
                if flag == 'True':  # Retry only flagged entries
                    insert_into_database(mac, sn, deviceName, plateNumber, targetType)
                else:
                    new_rows.append(row)  # Keep unflagged entries

        # Write back unflagged entries to the CSV file
        with open(CSV_FILE_PATH, 'w', newline='') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerows(new_rows)

def clear_csv_file():
    # Clear the CSV file content at 3 AM
    with open(CSV_FILE_PATH, 'w', newline='') as csvfile:
        pass  # Simply opening in write mode clears the file

# Schedule clearing the CSV file at 3 AM every day
scheduler = BackgroundScheduler()
scheduler.add_job(clear_csv_file, 'cron', hour=3, minute=0)
scheduler.start()

if __name__ == '__main__':
    app.run(host=SERVER_ADDRESS, port=SERVER_PORT, debug=True)

    # Retry flagged data every 10 minutes
    while True:
        retry_flagged_data()
        time.sleep(600)  # Wait for 10 minutes before retrying again
