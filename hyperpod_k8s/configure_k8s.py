import os
import subprocess
import tempfile
import re

# ---------------------------------
# Configurations you need to modify

# If this script is executed by root already, this variable can be empty
sudo_command = ["sudo","-E"]
#sudo_command = []

docker_users = [
    "ubuntu"
]

# ---

def install_docker():

    print("---")
    print("Installing Docker")
    subprocess.run( [ "bash", "./utils/install_docker.sh" ] )

    print("---")
    print("Add ubuntu user to docker group")
    for user in docker_users:
        subprocess.run( [ *sudo_command, "gpasswd", "-a", user, "docker" ] )
    subprocess.run( [ "newgrp", "docker" ] )


def install_kubernetes():

    print("---")
    print("Installing Kubernetes")
    subprocess.run( [ "bash", "./utils/install_kubernetes.sh" ] )

    subprocess.run( [ *sudo_command, "systemctl", "enable", "kubelet" ] )
    subprocess.run( [ *sudo_command, "systemctl", "start", "kubelet" ] )



def main():

    print("Starting Kubernetes configuration steps")

    install_docker()
    install_kubernetes()

    print("---")
    print("Finished Kubernetes configuration steps")


if __name__ == "__main__":
    main()
