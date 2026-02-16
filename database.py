from database import create_tables, get_connection

create_tables()                 # ensures tables exist
conn = get_connection()         # gets a persistent connection
cursor = conn.cursor()v
