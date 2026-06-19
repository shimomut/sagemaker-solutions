"""Example Python script for `make run-python-script`.

Prints a few facts about the node it runs on. Requires python3 on the node.
"""
import platform
import sys

print(f"Hostname: {platform.node()}")
print(f"Python:   {sys.version.split()[0]}")
print(f"Machine:  {platform.machine()}")
print(f"System:   {platform.system()} {platform.release()}")
