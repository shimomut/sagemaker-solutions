import uuid
import time
import subprocess

mem = str(uuid.uuid4()) * 1024 * 1024

subprocess.run( [ "python3", "memory_full.py" ] )
subprocess.run( [ "python3", "memory_full.py" ] )
subprocess.run( [ "python3", "memory_full.py" ] )
subprocess.run( [ "python3", "memory_full.py" ] )
subprocess.run( [ "python3", "memory_full.py" ] )
subprocess.run( [ "python3", "memory_full.py" ] )
subprocess.run( [ "python3", "memory_full.py" ] )
subprocess.run( [ "python3", "memory_full.py" ] )

while True:
    sleep(1)
