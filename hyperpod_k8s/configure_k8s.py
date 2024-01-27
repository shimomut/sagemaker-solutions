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


def disable_swap():

    subprocess.run( [ *sudo_command, "swapoff", "-a" ] )


def install_cri_dockerd():
    
    # https://github.com/Mirantis/cri-dockerd
    
    # https://github.com/Mirantis/cri-dockerd/releases/download/v0.3.9/cri-dockerd_0.3.9.3-0.ubuntu-focal_amd64.deb

    # sudo apt install -y ./cri-dockerd_0.3.9.3-0.ubuntu-focal_amd64.deb

    pass


def init_master():

    pass

    # https://kubernetes.io/docs/reference/setup-tools/kubeadm/kubeadm-init/

    # sudo kubeadm init --apiserver-advertise-address=10.1.13.99 --pod-network-cidr=10.1.0.0/17 --cri-socket unix:///var/run/cri-dockerd.sock

    # FIXME : should I use "--token" so that I can pre-generate the token and use it across instances? 

    #mkdir -p $HOME/.kube
    #sudo cp -i /etc/kubernetes/admin.conf $HOME/.kube/config
    #sudo chown $(id -u):$(id -g) $HOME/.kube/config


def init_worker():

    pass

    # https://kubernetes.io/docs/reference/setup-tools/kubeadm/kubeadm-join/

    # sudo kubeadm join 10.1.13.99:6443 --token h30cuw.bhh0btd05z04gcf3 --discovery-token-ca-cert-hash sha256:5df3a09f5e5c591375e0cd909d5b468f99e7d65d64119f57823779ecb44cd367 --cri-socket unix:///var/run/cri-dockerd.sock


def main():

    print("Starting Kubernetes configuration steps")

    install_docker()
    install_kubernetes()
    disable_swap()

    print("---")
    print("Finished Kubernetes configuration steps")


if __name__ == "__main__":
    main()
