import os
api_key = os.environ.get('API_KEY')
database = os.environ.get('DATABASE_NAME', 'default.db')

print(f"Using database: {database} and api key: {api_key}")

print({api_key})