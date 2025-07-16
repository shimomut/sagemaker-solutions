import time
import socket
import urllib.request

i = 0
while True:
    ipaddr = socket.gethostbyname(socket.gethostname())

    print(f"{ipaddr}: Hello from Python script! - {i}")

    time.sleep(10)
    i += 1
