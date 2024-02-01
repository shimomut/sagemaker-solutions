import sys
import os
import time
import subprocess
import tempfile
import re
import json
import argparse

import boto3


# TODO:
# - logging when using capture_output
# - eliminate configuration fields as much as possible
# - use FSx to store join information instead of SecretsManager


# ---------------------------------
# Configurations you need to modify

# If this script is executed by root already, this variable can be empty
sudo_command = ["sudo","-E"]
#sudo_command = []

# FIXME : can we get CIDR automatically? (from the output from ip addr command)
network_cidr = "10.1.0.0/17"

secret_name = "hyperpod-2"
region_name = "us-west-2"


# ---------------------------------
# Templates for configuration files

containerd_config = f"""
[plugins."io.containerd.grpc.v1.cri".containerd.runtimes.runc]
  [plugins."io.containerd.grpc.v1.cri".containerd.runtimes.runc.options]
    SystemdCgroup = true
"""


# ---

def install_python_packages():

    print("---")
    print("Installing Python packages")
    subprocess.run( [ "pip3", "install", "boto3" ], check=True )


def configure_bridged_traffic():

    print("---")
    print("Configuring bridged traffic")
    subprocess.run( [ "bash", "./utils/configure_bridged_traffic.sh" ], check=True )


def configure_cri_containerd():

    print("---")
    print("Configuring containerd config file")

    dst_filename = "/etc/containerd/config.toml"
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_filename = os.path.join(tmp_dir, os.path.basename(dst_filename))

        d = containerd_config.strip()
        print(d)

        with open(tmp_filename,"w") as fd:
            fd.write(d)

        subprocess.run( [ *sudo_command, "chmod", "644", tmp_filename ] )
        subprocess.run( [ *sudo_command, "chown", "root:root", tmp_filename ] )
        subprocess.run( [ *sudo_command, "cp", tmp_filename, dst_filename ] )

    print("---")
    print("Restarting containerd")

    subprocess.run( [ *sudo_command, "systemctl", "restart", "containerd" ], check=True )
    

def install_kubernetes():

    print("---")
    print("Installing Kubernetes")
    subprocess.run( [ "bash", "./utils/install_kubernetes.sh" ], check=True )

    subprocess.run( [ *sudo_command, "systemctl", "enable", "kubelet" ], check=True )
    subprocess.run( [ *sudo_command, "systemctl", "start", "kubelet" ], check=True )


def get_ip_addr():
    
    p = subprocess.run( [ "ip", "addr", "show", "dev", "ens6" ], check=True, capture_output=True )
    for line in p.stdout.decode("utf-8").splitlines():
        re_result = re.match(r"\s+inet ([0-9.]+)/[0-9]+ brd [0-9.]+ scope global dynamic ens6", line)
        if re_result:
            return re_result.group(1)
    else:
        raise ValueError("Cannot find IP address")


def put_join_info_from_master_node(join_info):

    session = boto3.session.Session()
    secretsmanager_client = session.client(
        service_name="secretsmanager",
        region_name=region_name,
    )

    secretsmanager_client.create_secret(
        Name=secret_name,
        SecretString=json.dumps(join_info)
    )


def get_join_info_from_master_node():

    session = boto3.session.Session()
    secretsmanager_client = session.client(
        service_name="secretsmanager",
        region_name=region_name
    )

    response = secretsmanager_client.get_secret_value(
        SecretId=secret_name
    )

    return json.loads(response["SecretString"])


def init_master_node():

    # https://kubernetes.io/docs/reference/setup-tools/kubeadm/kubeadm-init/

    ip_addr = get_ip_addr()

    print("---")
    print("Initializing master node")

    join_info = {}

    # capture output from kubeadm init command
    #    kubeadm join 10.1.13.99:6443 --token k20a86.1zq19kucigr2g9y7 \
    #            --discovery-token-ca-cert-hash sha256:13818de7009f31f4d899f2d3c4f81aad68ff53b3895955f4d83c52bc5b9c7a14 
    # FIXME : want to print and capture output at the same time
    p = subprocess.run( [ *sudo_command, "kubeadm", "init", f"--apiserver-advertise-address={ip_addr}", f"--pod-network-cidr={network_cidr}" ], check=True, capture_output=True )
    for line in p.stdout.decode("utf-8").splitlines():
        print(line)
        re_result = re.match(r"kubeadm join ([0-9.:]+) --token ([a-z0-9.]+)", line)
        if re_result:
            join_info["master_addr_port"] = re_result.group(1)
            join_info["token"] = re_result.group(2)
            continue

        re_result = re.match(r"\s+--discovery-token-ca-cert-hash sha256:([a-f0-9]+)", line)
        if re_result:
            join_info["discovery_token_ca_cert_hash"] = re_result.group(1)
            continue

    
    print("---")
    print("Storing join information for worker nodes")
    put_join_info_from_master_node(join_info)


    print("---")
    print("Copying kube config")
    subprocess.run( [ "bash", "./utils/copy_kube_config.sh" ], check=True )


def init_worker_node():

    # https://kubernetes.io/docs/reference/setup-tools/kubeadm/kubeadm-join/

    print("---")
    print("Getting join token from master node.")
    while True:
        join_info = get_join_info_from_master_node()
        if join_info is not None:
            break
        print("Join information is not ready in SecretsManager. Retrying...")
        time.sleep(10)

    print("---")
    print("Joining to the cluster")
    subprocess.run( [ *sudo_command, "kubeadm", "join", join_info["master_addr_port"], "--token", join_info["token"], "--discovery-token-ca-cert-hash", "sha256:"+join_info["discovery_token_ca_cert_hash"] ], check=True )


# This is needed only on master node
def install_cni_flannel():

    print("---")
    print(f"Installing flannel")

    subprocess.run( [ "wget", "https://github.com/flannel-io/flannel/releases/latest/download/kube-flannel.yml" ], check=True )

    with open("kube-flannel.yml") as fd_src:
        d = fd_src.read()

    d = re.sub( r'"Network": "[0-9./]+"', f'"Network": "{network_cidr}"', d )

    with open("kube-flannel.yml","w") as fd_dst:
        fd_dst.write(d)

    subprocess.run( [ "kubectl", "apply", "-f", "./kube-flannel.yml" ], check=True )



def configure_k8s( is_master_node ):

    print("Starting Kubernetes configuration steps")

    # common
    install_python_packages()
    configure_bridged_traffic()
    configure_cri_containerd()
    install_kubernetes()

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
