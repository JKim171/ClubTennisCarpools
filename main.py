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
sorted_passengers = dict(sorted(passengers.items(), key=lambda item: item[1][3], reverse=True))

num_drivers = len(drivers)
num_riders = num_drivers * 4

# Remove riders that can't fit
kept_passengers = sorted_passengers[:num_riders]
removed_passengers = sorted_passengers[num_riders:]

passengers = dict(kept_passengers)
bus_riders = []

# Makes array of people riding the bus
for tuple in removed_passengers:
    bus_riders.append(tuple[0])
# Fix the indexes for the passengers
passengeridx = 0
for key, value in passengers.items():
    passengers[key][2] = passengeridx
    passengeridx += 1
print("Drivers:", drivers)
print("Passengers:", passengers)

# Create 2D adjacency matrix passengers as rows and cols
riders_matrix = [[0 for i in range(len(passengers))] for j in range(len(passengers))]

# Calculate distances between points and fill in matrix
gmaps = gmaps.Client(key=api_key)

for row, passKey1 in enumerate(passengers):
    for col, passKey2 in enumerate(passengers):
        # driverAddress = drivers[driverKey][0]
        # driverIndex = drivers[driverKey][3]
        passAddress1 = passengers[passKey1][0]
        pass_index_1 = passengers[passKey1][2]
        passAddress2 = passengers[passKey2][0]
        pass_index_2 = passengers[passKey2][2]
        if pass_index_1 == pass_index_2:
            riders_matrix[row][col] = (10000, pass_index_1)
            continue
        riders_matrix[row][col] = (float(gmaps.distance_matrix(passAddress1, passAddress2, units="imperial")["rows"][0]["elements"][0]["distance"]["text"][:-3]), col)

# Sort each column in each row and append row number at end to keep track of original row index
for i in range(num_riders):
    riders_matrix[i].sort()
    riders_matrix[i].append(i)

# Sort matrix by row with lowest distance
riders_matrix.sort()
        
print("adjMatrix:", riders_matrix)

group_assigned = {} # key: passenger index, val: group index
people_in_group = {} # key: group index, val: num people in group (4 means full)
num_groups_assigned = 0

for i in range(num_riders):
    # ignore when first rider has been assigned a group
    pass_index_1 = riders_matrix[-1]
    if pass_index_1 in group_assigned:
        continue
    curr_index = -1
    for j in range(num_riders):
        pass_index_2 = riders_matrix[i][j][1]
        # ignore when both passengers are the same or when second rider is in full group
        if pass_index_1 != pass_index_2 and (pass_index_2 not in group_assigned or len(people_in_group[group_assigned[pass_index_2]]) < 4):
            curr_index = pass_index_2
            break
    # Rare edge case where last group only gets assigned one person
    if curr_index == -1:
        group_assigned[pass_index_1] = num_groups_assigned + 1
        num_groups_assigned += 1
        people_in_group[num_groups_assigned] = [pass_index_1]
    else:
        # Case where second rider is already assigned a group
        if curr_index in group_assigned:
            group = group_assigned[curr_index]
            group_assigned[pass_index_1] = group
            people_in_group[group].append(pass_index_1)
        # Case where neither rider is assigned a group yet
        else:
            group = num_groups_assigned + 1
            num_groups_assigned += 1
            group_assigned[pass_index_1] = group
            group_assigned[curr_index] = group
            people_in_group[group] = [pass_index_1, pass_index_2]

# Create matrix that stores distance between each driver and rider
drivers_matrix = [[0 for _ in range(len(passengers))] for __ in range(len(drivers))]

# Find distandce between each driver and passenger
for row, driverKey in enumerate(drivers):
    for col, passKey in enumerate(passengers):
        driverAddress = drivers[driverKey][0]
        driverIndex = drivers[driverKey][3]
        passAddress = passengers[passKey][0]
        passIndex = passengers[passKey][2]
        drivers_matrix[row][col] = (float(gmaps.distance_matrix(driverAddress, passAddress, units="imperial")["rows"][0]["elements"][0]["distance"]["text"][:-3]), col)

# Sort each row by minimum distance
for i in range(num_drivers):
    drivers_matrix[i].sort()
    drivers_matrix[i].append(i)

# Sort entire matrix by row with minimum distance
drivers_matrix.sort()

assigned_driver = set() # keeps track of whos in a car
cars = [] # keeps track of final car assignments

# Assign drivers to groups
for row in range(num_drivers):
    driver_index = drivers_matrix[-1]
    cars.append([driver_index])
    for col in range(num_riders):
        rider_index = drivers_matrix[row][col][1]
        if rider_index not in assigned_driver:
            break
    group_num = group_assigned[rider_index]
    for person in people_in_group[group_num]:
        cars[row].append(person)
        assigned_driver.add(person)

# Print out each car
for i in range(num_drivers):
    print("Car", i + 1)
    for j in range(len(cars[i])):
        # Print the actual name of each person in each car
        print()

# # Calculate and draft closest drivers to passengers
# for passenger in range(len(passengers)):
#     curIndex = None
#     curShortest = float('inf')
#     tempDriver = None

#     # Find the nearest available driver with less than 4 passengers
#     for driver in range(len(drivers)):
#         if riders_matrix[passenger][driver] < curShortest:
#             for key, arr in drivers.items():
#                 if driver == arr[3] and len(arr[4]) < 4:  # Check if driver has room
#                     curShortest = riders_matrix[passenger][driver]
#                     curIndex = driver
#                     tempDriver = key

#     # Find the corresponding passenger key
#     tempPassenger = None
#     for key, arr in passengers.items():
#         if passenger == arr[2]:
#             tempPassenger = key
#             break  # Stop searching once found

#     # If a valid driver and passenger are found, assign them
#     if not tempDriver:
#         print("DRIVERS ARE FULL")
#         break
#     if tempDriver and tempPassenger:
#         drivers[tempDriver][4].append(tempPassenger)

for key, value in drivers.items():
    print(key + str(value[4]))