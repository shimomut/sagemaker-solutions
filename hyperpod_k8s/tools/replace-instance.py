import os
import time
import subprocess
import tempfile
import re
import json
import argparse
import getpass
import io

import boto3


# --------------
# Configurations

# If this script is executed by root already, this variable can be empty
if getpass.getuser() == "root":
    sudo_command = []
else:
    sudo_command = ["sudo","-E"]

secret_name_prefix = "hyperpod-k8s-"
#secret_name_prefix = "hyperpod-k8s-" + str(uuid.uuid4())[:8] + "-" # for local testing purpose


# ---

# FIXME : move to common module with LCC script
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

    def iter_instances(self):
        for instance_group in self.d["InstanceGroups"]:
            for instance in instance_group["Instances"]:
                instance2 = instance.copy()
                instance2["InstanceType"] = instance_group["InstanceType"]
                instance2["InstanceGroupName"] = instance_group["Name"]
                instance2["Name"] = "ip-" + instance["CustomerIpAddress"].replace(".","-")
                yield instance2


# FIXME : move to common module with LCC script
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


# FIXME : move to common module with LCC script
def get_secret_name():
    cluster_id = ResourceConfig.instance().get_cluster_id()
    return f"{secret_name_prefix}{cluster_id}"


# FIXME : move to common module with LCC script
def put_join_info_from_master_node(join_info, update_existing=False):

    region_name = ResourceConfig.instance().get_region()

    session = boto3.session.Session()
    secretsmanager_client = session.client(
        service_name="secretsmanager",
        region_name=region_name,
    )

    if update_existing:
        secretsmanager_client.update_secret(
            SecretId=get_secret_name(),
            SecretString=json.dumps(join_info)
        )
    else:
        secretsmanager_client.create_secret(
            Name=get_secret_name(),
            SecretString=json.dumps(join_info)
        )


# FIXME : move to common module with LCC script
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


# TODO : implement
def check_node_drain_status(hostname):
    pass


def generate_new_join_token():

    print("---")
    print(f"Generating new join token")

    captured_output = run_subprocess_wrap(["kubeadm", "token", "create", "--description", "Bootstrap token generated for instance replacement"])
    captured_output = captured_output.strip()
    output_lines = captured_output.strip().splitlines()
    assert len(output_lines)==1, f"Unexpected output from kubeadm token create command [{captured_output}]"

    new_token = output_lines[0]

    re_result = re.match(r"[a-z0-9]{6}\.[a-z0-9]{16}", new_token)
    assert re_result is not None, f"Unexpected output from kubeadm token create command [{new_token}]"

    # get previous join token
    join_info = get_join_info_from_master_node()

    join_info["token"] = new_token

    # set new join token
    put_join_info_from_master_node(join_info, update_existing=True)


def remove_node(hostname):

    print("---")
    print(f"Removing the node from cluster")

    captured_output = run_subprocess_wrap(["kubectl", "delete", "node", hostname])
    captured_output = captured_output.strip()
    output_lines = captured_output.strip().splitlines()
    assert len(output_lines)==1, f"Unexpected output from kubectl delete node command [{captured_output}]"

    re_result = re.match(r"node \"ip-[0-9]+-[0-9]+-[0-9]+-[0-9]+\" deleted", output_lines[0])
    assert re_result is not None, f"Unexpected output from kubectl delete node command [{captured_output}]"


def trigger_replacement(hostname):

    print("---")
    print(f"Triggering instance replacement")

    run_subprocess_wrap([*sudo_command, "scontrol", "update", f"node={hostname}", "state=fail", 'reason="Action:Replace"'])


def wait_for_replacement_completion(hostname):

    print("---")
    print(f"Waiting for instance replacement completion")

    while True:
        
        status = None
        captured_output = run_subprocess_wrap(["sinfo", "--node", hostname])
        for line in captured_output.splitlines():
            re_result = re.match(r"([^\s]+)\s+([^\s]+)\s+([^\s]+)\s+([^\s]+)\s+([^\s]+)\s+([^\s]+)", line)
            if re_result and re_result.group(6)==hostname:
                status = re_result.group(5)

        if status=="idle":
            break

        time.sleep(10)


def wait_until_all_nodes_become_ready():

    print("---")
    print(f"Waiting for all nodes become ready")

    while True:

        ready_state_nodes = set()
        found_not_ready = False

        """
        NAME             STATUS   ROLES           AGE     VERSION
        ip-10-2-79-131   Ready    control-plane   3h14m   v1.29.1
        ip-10-2-91-139   Ready    <none>          3h14m   v1.29.1
        ip-10-2-92-5     Ready    <none>          3h14m   v1.29.1
        """

        captured_output = run_subprocess_wrap( [ "kubectl", "get", "nodes" ] )
        for line in captured_output.splitlines():
            re_result = re.match(r"(ip-[0-9]+-[0-9]+-[0-9]+-[0-9]+)\s+Ready\s+.*", line)
            if re_result:
                ready_state_nodes.add(re_result.group(1))
                continue

        for instance in ResourceConfig.instance().iter_instances():
            if instance["Name"] not in ready_state_nodes:
                found_not_ready = True
                break

        if not found_not_ready:
            break

        time.sleep(10)

    print(f"All nodes are ready now")


def replace_instance(hostname):

    check_node_drain_status(hostname)
    generate_new_join_token()
    remove_node(hostname)
    trigger_replacement(hostname)
    wait_for_replacement_completion(hostname)
    wait_until_all_nodes_become_ready()


if __name__ == "__main__":

    argparser = argparse.ArgumentParser(description="Script to replace faulty node")
    argparser.add_argument('--debug', action="store_true", help="Print full exception information")
    argparser.add_argument('--hostname', action="store", required=True, help="Hostname (e.g. ip-10.0.12.34)")
    args = argparser.parse_args()

    try:
        replace_instance( hostname=args.hostname )
    except Exception as e:
        if args.debug:
            raise
        else:
            print(e)
