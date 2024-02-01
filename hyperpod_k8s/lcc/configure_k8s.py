import sys
import os
import time
import subprocess
import tempfile
import re
import json
import argparse
import ipaddress
import getpass
import socket
import fcntl
import struct

import boto3


# TODO:
# - logging when using capture_output
# - eliminate configuration fields as much as possible
# - use FSx to store join information instead of SecretsManager


# ---------------------------------
# Configurations you need to modify

# If this script is executed by root already, this variable can be empty
if getpass.getuser() == "root":
    sudo_command = []
else:
    sudo_command = ["sudo","-E"]

apt_install_max_retries = 10

# ---------------------------------
# Templates for configuration files

containerd_config = f"""
[plugins."io.containerd.grpc.v1.cri".containerd.runtimes.runc]
  [plugins."io.containerd.grpc.v1.cri".containerd.runtimes.runc.options]
    SystemdCgroup = true
"""


# ---

class ResourceConfig:

    _instance = None

    @staticmethod
    def instance():
        if ResourceConfig._instance is None:
            ResourceConfig._instance = ResourceConfig()
        return ResourceConfig._instance

    def __init__(self):

        if "SAGEMAKER_RESOURCE_CONFIG_PATH" in os.environ:
            resource_config_filename = os.environ["SAGEMAKER_RESOURCE_CONFIG_PATH"]
        else:
            resource_config_filename = "/opt/ml/config/resource_config.json"

        # due to directory permission, regular user cannot open the file.
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_filename = os.path.join(tmp_dir, os.path.basename(resource_config_filename))

            subprocess.run( [ *sudo_command, "cp", resource_config_filename, tmp_filename ] )
            subprocess.run( [ *sudo_command, "chmod", "644", tmp_filename ] )

            with open(tmp_filename) as fd:
                d = fd.read()

        self.d = json.loads(d)

        """
        {
            'ClusterConfig': {
                'ClusterArn': 'arn:aws:sagemaker:us-west-2:842413447717:cluster/kb8v11zrrpvr',
                'ClusterName': 'K8-1'
            },
            'InstanceGroups': [
                {
                    'InstanceType': 'ml.t3.xlarge',
                    'Instances': [
                        {
                            'AgentIpAddress': '172.16.102.203',
                            'CustomerIpAddress': '10.1.113.28',
                            'InstanceId': 'i-07259dd159a1c7130',
                            'InstanceName': 'ControllerGroup-1'
                        }
                    ],
                    'Name': 'ControllerGroup'
                },
                {
                    'InstanceType': 'ml.t3.xlarge',
                    'Instances': [
                        {
                            'AgentIpAddress': '172.16.100.157',
                            'CustomerIpAddress': '10.1.38.128',
                            'InstanceId': 'i-0cbbe3075137ffa1d',
                            'InstanceName': 'WorkerGroup-1'
                        },
                        {
                            'AgentIpAddress': '172.16.98.182',
                            'CustomerIpAddress': '10.1.29.16',
                            'InstanceId': 'i-0cc2532921ec06344',
                            'InstanceName': 'WorkerGroup-2'
                        }
                    ],
                    'Name': 'WorkerGroup'
                }
            ]
        }
        """

    def get_cluster_name(self):
        return self.d["ClusterConfig"]["ClusterName"]

    def get_cluster_arn(self):
        return self.d["ClusterConfig"]["ClusterArn"]

    def get_region(self):
        arn = self.get_cluster_arn()
        re_result = re.match( "arn:aws:sagemaker:([a-z0-9-]+):([0-9]+):cluster/([a-z0-9]+)", arn )
        assert re_result, "Region name not found in cluster ARN"
        return re_result.group(1)

    def get_cluster_id(self):
        arn = self.get_cluster_arn()
        re_result = re.match( "arn:aws:sagemaker:([a-z0-9-]+):([0-9]+):cluster/([a-z0-9]+)", arn )
        assert re_result, "Cluster ID not found in cluster ARN"
        return re_result.group(3)


class IpAddressInfo:

    _instance = None

    @staticmethod
    def instance():
        if IpAddressInfo._instance is None:
            IpAddressInfo._instance = IpAddressInfo()
        return IpAddressInfo._instance

    def __init__(self):

        interface_name = b"ens6"

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.addr = socket.inet_ntoa(fcntl.ioctl(sock, 35095, struct.pack('256s', interface_name))[20:24])
        self.mask = socket.inet_ntoa(fcntl.ioctl(sock, 35099, struct.pack('256s', interface_name))[20:24])
        self.cidr = str(ipaddress.IPv4Network(self.addr+"/"+self.mask, strict=False))


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

    # Kubernetes installation could fail with "Could not get lock /var/lib/dpkg/lock-frontend. It is held by process 4065 (apt-get)"
    for i_retry in range(apt_install_max_retries):
        
        if i_retry>0:
            time.sleep(10)
            print("Retrying")

        try:
            subprocess.run( [ "bash", "./utils/install_kubernetes.sh" ], check=True )
            break
        except subprocess.CalledProcessError:
            continue

    subprocess.run( [ *sudo_command, "systemctl", "enable", "kubelet" ], check=True )
    subprocess.run( [ *sudo_command, "systemctl", "start", "kubelet" ], check=True )


def get_secret_name():
    cluster_id = ResourceConfig.instance().get_cluster_id()
    return f"hyperpod-k8s-{cluster_id}"


def put_join_info_from_master_node(join_info):

    region_name = ResourceConfig.instance().get_region()

    session = boto3.session.Session()
    secretsmanager_client = session.client(
        service_name="secretsmanager",
        region_name=region_name,
    )

    secretsmanager_client.create_secret(
        Name=get_secret_name(),
        SecretString=json.dumps(join_info)
    )


def get_join_info_from_master_node():

    region_name = ResourceConfig.instance().get_region()

    session = boto3.session.Session()
    secretsmanager_client = session.client(
        service_name="secretsmanager",
        region_name=region_name
    )

    try:
        response = secretsmanager_client.get_secret_value(
            SecretId=get_secret_name()
        )
    except secretsmanager_client.exceptions.ResourceNotFoundException:
        return None

    return json.loads(response["SecretString"])


def init_master_node():

    # https://kubernetes.io/docs/reference/setup-tools/kubeadm/kubeadm-init/

    print("---")
    print("Initializing master node")

    join_info = {}

    # capture output from kubeadm init command
    # FIXME : want to print and capture output at the same time
    p = subprocess.run( [ *sudo_command, "kubeadm", "init", f"--apiserver-advertise-address={IpAddressInfo.instance().addr}", f"--pod-network-cidr={IpAddressInfo.instance().cidr}" ], check=True, capture_output=True )
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

    d = re.sub( r'"Network": "[0-9./]+"', f'"Network": "{IpAddressInfo.instance().cidr}"', d )

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
