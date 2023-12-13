import uuid
import time
import random
import subprocess

mem = str(uuid.uuid4()) * random.randint(1,1024 * 1024)
print(f"Allocated {len(mem)} bytes")

if 1:
    subprocess.run( [ "python3", "memory_full.py" ] )
    subprocess.run( [ "python3", "memory_full.py" ] )
    subprocess.run( [ "python3", "memory_full.py" ] )
    subprocess.run( [ "python3", "memory_full.py" ] )
    subprocess.run( [ "python3", "memory_full.py" ] )
    subprocess.run( [ "python3", "memory_full.py" ] )
    subprocess.run( [ "python3", "memory_full.py" ] )
    subprocess.run( [ "python3", "memory_full.py" ] )

while True:
    time.sleep(1)
