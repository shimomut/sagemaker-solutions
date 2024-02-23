import subprocess

# replace this variable with the output from sinfo command
nodes="ip-10-2-35-66,ip-10-2-59-17"

command=["sudo", "systemctl", "restart", "slurmd"]

result = subprocess.run(["scontrol", "show", "hostnames", nodes], capture_output=True)

for node in result.stdout.decode("utf-8").strip().splitlines():
    print(node)
    subprocess.run( ["ssh", node] + command )

