import os
import subprocess
import tempfile
import re
import argparse


# ---------------------------------
# Configurations you need to modify

# If this script is executed by root already, this variable can be empty
sudo_command = ["sudo","-E"]
#sudo_command = []

docker_users = [
    "ubuntu"
]

# ---

# This step may not be needed when using containerd as the container runtime
def install_docker():

    print("---")
    print("Installing Docker")
    subprocess.run( [ "bash", "./utils/install_docker.sh" ], check=True )

    print("---")
    print("Add ubuntu user to docker group")
    for user in docker_users:
        subprocess.run( [ *sudo_command, "gpasswd", "-a", user, "docker" ], check=True )
    subprocess.run( [ "newgrp", "docker" ], check=True )


def configure_cri_containerd():

    # configure /etc/containerd/config.toml 
    """
    [plugins."io.containerd.grpc.v1.cri".containerd.runtimes.runc]
      [plugins."io.containerd.grpc.v1.cri".containerd.runtimes.runc.options]
        SystemdCgroup = true
    """

    # sudo systemctl restart containerd
    

def install_kubernetes():

    print("---")
    print("Installing Kubernetes")
    subprocess.run( [ "bash", "./utils/install_kubernetes.sh" ], check=True )

    subprocess.run( [ *sudo_command, "systemctl", "enable", "kubelet" ], check=True )
    subprocess.run( [ *sudo_command, "systemctl", "start", "kubelet" ], check=True )


# Swap is disabled by default on HyperPod, we should be able to remove this step.
def disable_swap():

    subprocess.run( [ *sudo_command, "swapoff", "-a" ], check=True )


def init_master_node():

    pass

    # https://kubernetes.io/docs/reference/setup-tools/kubeadm/kubeadm-init/

    # sudo kubeadm init --apiserver-advertise-address=10.1.13.99 --pod-network-cidr=10.1.0.0/17

    # capture output from kubeadm init command
    #    kubeadm join 10.1.13.99:6443 --token k20a86.1zq19kucigr2g9y7 \
    #            --discovery-token-ca-cert-hash sha256:13818de7009f31f4d899f2d3c4f81aad68ff53b3895955f4d83c52bc5b9c7a14 

    #mkdir -p $HOME/.kube
    #sudo cp -i /etc/kubernetes/admin.conf $HOME/.kube/config
    #sudo chown $(id -u):$(id -g) $HOME/.kube/config


def init_worker_node():

    pass

    # https://kubernetes.io/docs/reference/setup-tools/kubeadm/kubeadm-join/

    # Run the kubeadm join command captured in init_master_node().
    # sudo kubeadm join 10.1.13.99:6443 --token k20a86.1zq19kucigr2g9y7 --discovery-token-ca-cert-hash sha256:13818de7009f31f4d899f2d3c4f81aad68ff53b3895955f4d83c52bc5b9c7a14


# This is needed only on master node
def install_cni_flannel():
    pass

    # wget https://github.com/flannel-io/flannel/releases/latest/download/kube-flannel.yml

    # modify CIDR
    """
    net-conf.json: |
        {
        "Network": "10.1.0.0/17",
    """

    # kubectl apply -f ./kube-flannel.yml


def configure_k8s( is_master_node ):

    print("Starting Kubernetes configuration steps")

    # common
    #install_docker()
    configure_cri_containerd()
    install_kubernetes()
    disable_swap()

    if is_master_node:
        # master node
        init_master_node()
        install_cni_flannel()
    else:
        # workder node
        init_worker_node()

    print("---")
    print("Finished Kubernetes configuration steps")


if __name__ == "__main__":

    argparser = argparse.ArgumentParser(description="Lifecycle configuration script to initialize Kubernetes on SageMaker HyperPod")
    argparser.add_argument('--master-node', action="store_true", help='Initialize master node')
    args = argparser.parse_args()

    configure_k8s( is_master_node=args.master_node )
