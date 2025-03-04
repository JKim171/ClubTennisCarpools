import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
import googlemaps as gmaps
from dotenv import load_dotenv
import os

load_dotenv()
api_key = os.getenv('API_KEY')
service_account_credentials_path = os.getenv('SERVICE_ACCOUNT_CREDENTIALS_PATH')
# Define the scope
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]

# Authenticate with JSON key file
creds = ServiceAccountCredentials.from_json_keyfile_name(service_account_credentials_path, scope)
client = gspread.authorize(creds)

# Open the Google Sheet
spreadsheet = client.open("Club Tennis Carpools")  # Use the name of the sheet
practiceWorksheet = spreadsheet.worksheet("Form Responses 3")
playerWorksheet = spreadsheet.worksheet("PLAYER INFO")

# Read data for lookup table
data = playerWorksheet.get('A:I')
lookupdf = pd.DataFrame(data[1:], columns=data[0])
lookupdf = lookupdf.apply(lambda x: x.str.upper() if x.dtype == "object" else x)

# Read all data into a list
data = practiceWorksheet.get('A:C')

# Convert to Pandas DataFrame
practicedf = pd.DataFrame(data[1:], columns=data[0])
# Rename columns
practicedf = practicedf.rename(columns={"Name (first and last no abbreviations)": "Name", "Do you need a ride?": "IsGoing"})
practicedf = practicedf.apply(lambda x: x.str.upper() if x.dtype == "object" else x)

drivers = {}
passengers = {}

# Loop through form results and sort into drivers and passengers
driveridx = 0
passengeridx = 0
for index, row in practicedf.iterrows():
    tempRow = lookupdf.loc[row['Name'] == lookupdf['Name']]
    if tempRow.empty:
        print(str(row['Name']) + " was not found in the lookup table")
    if row['IsGoing'] == "NO (I HAVE A CAR AND CAN DRIVE OTHERS)":
        drivers[row['Name']] = [list(tempRow['Address'])[0], list(tempRow['Phone Number'])[0], 4, driveridx, []]
        driveridx += 1
    elif row['IsGoing'] == "YES":
        passengers[row['Name']] = [list(tempRow['Address'])[0], list(tempRow['Phone Number'])[0], passengeridx, int(list(tempRow['Num Months in Club'])[0])]
        passengeridx += 1
    # If we added participation tracking add some code here
passengers = dict(sorted(passengers.items(), key=lambda item: item[1][3], reverse=True))
# Fix the indexes for the passengers
passengeridx = 0
for key, value in passengers.items():
    passengers[key][2] = passengeridx
    passengeridx += 1
print(drivers)
print(passengers)

# Create 2D adjacency matrix passengers as rows, drivers as cols
adjMatrix = [[0 for i in range(len(drivers))] for j in range(len(passengers))]

# Calculate distances between points and fill in matrix
gmaps = gmaps.Client(key=api_key)

for row, passKey in enumerate(passengers):
    for col, driverKey in enumerate(drivers):
        driverAddress = drivers[driverKey][0]
        driverIndex = drivers[driverKey][3]
        passAddress = passengers[passKey][0]
        passIndex = passengers[passKey][2]
        adjMatrix[row][col] = float(gmaps.distance_matrix(driverAddress, passAddress, units="imperial")["rows"][0]["elements"][0]["distance"]["text"][:-3])

print(adjMatrix)

# Calculate and draft closest drivers to passengers
for passenger in range(len(passengers)):
    curIndex = None
    curShortest = float('inf')
    tempDriver = None

    # Find the nearest available driver with less than 4 passengers
    for driver in range(len(drivers)):
        if adjMatrix[passenger][driver] < curShortest:
            for key, arr in drivers.items():
                if driver == arr[3] and len(arr[4]) < 4:  # Check if driver has room
                    curShortest = adjMatrix[passenger][driver]
                    curIndex = driver
                    tempDriver = key

    # Find the corresponding passenger key
    tempPassenger = None
    for key, arr in passengers.items():
        if passenger == arr[2]:
            tempPassenger = key
            break  # Stop searching once found

    # If a valid driver and passenger are found, assign them
    if not tempDriver:
        print("DRIVERS ARE FULL")
        break
    if tempDriver and tempPassenger:
        drivers[tempDriver][4].append(tempPassenger)

for key, value in drivers.items():
    print(key + str(value[4]))