import requests
from datetime import datetime
from supabase import create_client, Client

# Configuration
AMBEE_API_KEY = 'da8e070dab0b6b57cf082e152f1945c6be580654f6c44a289ec42964a702df0f'
SUPABASE_URL = 'https://qnljdbqnskhvkjorvurb.supabase.co'
SUPABASE_KEY = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InFubGpkYnFuc2todmtqb3J2dXJiIiwicm9sZSI6ImFub24iLCJpYXQiOjE3MzgyODk0OTIsImV4cCI6MjA1Mzg2NTQ5Mn0.Joj6eu946k1959uNAENOZ4nDo1nQtgTZ-_cpqBp6hGY'
TABLE_NAME = 'incidents'

# Initialize Supabase client
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Fetch disaster data from Ambee
def fetch_disaster_data():
    headers = {
        'x-api-key': AMBEE_API_KEY
    }
    response = requests.get('https://api.ambeedata.com/disasters/latest/by-country-code?countryCode=USA', headers=headers)
    response.raise_for_status()
    data = response.json()
    print("Raw API response:", data)  # Debug print
    return data

# Map incident type
def map_incident_type(type_abbr):
    type_mapping = {
        'SW': 'storm',
        'FL': 'flood',
        'WF': 'fire',
    }
    return type_mapping.get(type_abbr, type_abbr)

# Map Ambee data to Supabase schema
def map_data_to_schema(data):
    incidents = []
    for event in data.get('result', []):
        print("Processing event:", event)  # Debug print
        event_name = event.get('event_name', 'Unknown Event')
        location = ' '.join(event_name.split()[-2:]) if event_name != 'Unknown Event' else 'Unknown Location'
        
        incident = {
            'title': event_name,
            'location': location,
            'type': map_incident_type(event.get('event_type', 'unknown')),
            'severity': 1,
            'latitude': event.get('lat'),
            'longitude': event.get('lng'),
            'timestamp': datetime.strptime(event.get('date'), '%Y-%m-%d %H:%M:%S').isoformat()
        }
        incidents.append(incident)
    print("Mapped incidents:", incidents)  # Debug print
    return incidents

# Insert data into Supabase
def insert_into_supabase(incidents):
    for incident in incidents:
        print("Inserting incident:", incident)  # Debug print
        result = supabase.table(TABLE_NAME).insert(incident).execute()
        print("Insert result:", result)  # Debug print

def main():
    data = fetch_disaster_data()
    incidents = map_data_to_schema(data)
    insert_into_supabase(incidents)
    print(f"Inserted {len(incidents)} incidents into Supabase.")

if __name__ == '__main__':
    main()