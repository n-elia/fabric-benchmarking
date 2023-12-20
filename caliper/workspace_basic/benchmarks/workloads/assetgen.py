# assetID,'blue','20','penguin','500'

""" This is a script to generate a .csv file containing N data entries for the asset-transfer-basic chaincode.
    The script will generate a .csv file containing N entries, each entry will have the following format:
    assetID, color, size, owner, appraisedValue
    The script will generate a random assetID, color, size, owner and appraisedValue for each entry.
"""

import csv
import random
import string
import sys

# Check if the number of arguments is correct
if len(sys.argv) != 3:
    print("Usage: python3 assetgen.py <number_of_entries> <output_file>")
    sys.exit(1)

# Get the number of entries to generate
try:
    N = int(sys.argv[1])
except ValueError:
    print("Error: <number_of_entries> must be an integer")
    sys.exit(1)

# Get the output file
output_file = sys.argv[2]

# Generate the entries
entries = []
for i in range(N):
    assetID = ''.join(random.choices(string.ascii_uppercase + string.digits, k=10))
    color = random.choice(["red", "blue", "green", "yellow", "black", "white"])
    size = random.choice([1, 2, 3, 4, 5])
    owner = ''.join(random.choices(string.ascii_uppercase + string.digits, k=10))
    appraisedValue = str(random.randint(0, 1000))
    entries.append([assetID, color, size, owner, appraisedValue])

# Write the entries to the output file
with open(output_file, 'w', newline='') as csvfile:
    writer = csv.writer(csvfile, delimiter=',')
    writer.writerow(["id", "color", "size", "owner", "appraisedValue"])
    for entry in entries:
        writer.writerow(entry)

print("Done")
