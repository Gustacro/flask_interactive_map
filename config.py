
import urllib.parse

password = '@F5f2335s@'
encoded_password = urllib.parse.quote_plus(password)
# print(encoded_password)
# Output: %40Secret123%21

# config.py

LOCAL_DATABASE = {
    'NAME': 'osm_data_interactive_map',
    'USER': 'postgres',
    'PASSWORD': 'encoded_password', # Use the encoded password here
    'HOST': 'localhost',
    'PORT': 5432,
}