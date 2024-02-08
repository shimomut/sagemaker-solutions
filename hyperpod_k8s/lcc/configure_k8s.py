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
import uuid
import urllib.request
import io

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

secret_name_prefix = "hyperpod-k8s-"
#secret_name_prefix = "hyperpod-k8s-" + str(uuid.uuid4())[:8] + "-" # for local testing purpose

# Pod network CIDR has to be different range from Node level network.
pod_cidr = "10.244.0.0/16"

apt_install_max_retries = 10
kubectl_apply_max_retries = 10

# If NVMe is available, use it as containerd data path
if os.path.exists("/opt/dlami/nvme"):
    containerd_root = "/opt/dlami/nvme/containerd"
else:
    containerd_root = "/var/lib/containerd"

# ---------------------------------
# Templates for configuration files

containerd_config = f"""
root = "{containerd_root}"

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

            run_subprocess_wrap( [ *sudo_command, "cp", resource_config_filename, tmp_filename ] )
            run_subprocess_wrap( [ *sudo_command, "chmod", "644", tmp_filename ] )

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


def run_subprocess_wrap(cmd):

    captured_stdout = io.StringIO()

    p = subprocess.Popen( cmd, bufsize=1, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT )
    for line in iter(p.stdout.readline, ""):
        captured_stdout.write(line)
        print( line, end="", flush=True )
    p.wait()

    if p.returncode != 0:
        raise ChildProcessError(f"Subprocess {cmd} returned non-zero exit code {p.returncode}.")
    
    return captured_stdout.getvalue()


def install_python_packages():

    print("---")
    print("Installing Python packages")
    run_subprocess_wrap( [ "pip3", "install", "boto3" ] )


def configure_bridged_traffic():

    print("---")
    print("Configuring bridged traffic")
    run_subprocess_wrap( [ "bash", "./utils/configure_bridged_traffic.sh" ] )


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

        run_subprocess_wrap( [ *sudo_command, "chmod", "644", tmp_filename ] )
        run_subprocess_wrap( [ *sudo_command, "chown", "root:root", tmp_filename ] )
        run_subprocess_wrap( [ *sudo_command, "cp", tmp_filename, dst_filename ] )

    print("---")
    print("Restarting containerd")

    run_subprocess_wrap( [ *sudo_command, "systemctl", "restart", "containerd" ] )
    

def install_kubernetes():

    print("---")
    print("Installing Kubernetes")

    # Kubernetes installation sometimes fail with "Could not get lock /var/lib/dpkg/lock-frontend. It is held by process 4065 (apt-get)"
    i_retry = 0
    while True:
        try:
            run_subprocess_wrap([ "bash", "./utils/install_kubernetes.sh" ])
            break
        except ChildProcessError:
            if i_retry >= kubectl_apply_max_retries:
                raise
            i_retry += 1
            time.sleep(10)
            print("Retrying")

    run_subprocess_wrap( [ *sudo_command, "systemctl", "enable", "kubelet" ] )
    run_subprocess_wrap( [ *sudo_command, "systemctl", "start", "kubelet" ] )


def get_secret_name():
    cluster_id = ResourceConfig.instance().get_cluster_id()
    return f"{secret_name_prefix}{cluster_id}"


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

    captured_output = run_subprocess_wrap( [ *sudo_command, "kubeadm", "init", f"--apiserver-advertise-address={IpAddressInfo.instance().addr}", f"--pod-network-cidr={pod_cidr}" ] )
    for line in captured_output.splitlines():
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
    run_subprocess_wrap([ "bash", "./utils/copy_kube_config.sh" ])


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
    run_subprocess_wrap([ *sudo_command, "kubeadm", "join", join_info["master_addr_port"], "--token", join_info["token"], "--discovery-token-ca-cert-hash", "sha256:"+join_info["discovery_token_ca_cert_hash"] ])


# This is needed only on master node
def install_cni_flannel():

    print("---")
    print(f"Installing flannel")

    # Current directory is not read/write for ubuntu user. Create a temporary directory.
    with tempfile.TemporaryDirectory() as tmp_dir:

        tmp_filename = os.path.join(tmp_dir, "kube-flannel.yml")

        with urllib.request.urlopen("https://github.com/flannel-io/flannel/releases/latest/download/kube-flannel.yml") as fd:
            d = fd.read().decode("utf-8")

        d = re.sub( r'"Network": "[0-9./]+"', f'"Network": "{pod_cidr}"', d )
        print(d)

        with open(tmp_filename,"w") as fd_dst:
            fd_dst.write(d)

        # kubectl apply fails with "error validating data: failed to download openapi".
        # checking if this can be solved by retrying.
        print("---")
        print(f"Applying kube-flannel.yml")
        i_retry = 0
        while True:
            try:
                run_subprocess_wrap(["kubectl", "apply", "-f", tmp_filename])
                break
            except ChildProcessError:
                if i_retry >= kubectl_apply_max_retries:
                    raise
                i_retry += 1
                time.sleep(10)
                print("Retrying")


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
