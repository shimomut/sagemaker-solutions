import sys
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


# ---

# FIXME : move to common module with LCC script
class ProgressDots:

    def __init__(self):
        self.status = None

    def tick(self,status):

        if self.status != status:

            # first line doesn't require line break
            if self.status is not None:
                print()

            self.status = status

            # print new status if not ending
            if self.status is not None:
                print(self.status, end=" ", flush=True)

            return

        # print dots if status didn't change
        if self.status is not None:
            print(".", end="", flush=True)


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
def run_subprocess_wrap(cmd, print_output=True):

    captured_stdout = io.StringIO()

    p = subprocess.Popen( cmd, bufsize=1, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT )
    for line in iter(p.stdout.readline, ""):
        captured_stdout.write(line)
        if print_output:
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


def generate_new_token():

    print(f"Generating new join token")

    captured_output = run_subprocess_wrap(["kubeadm", "token", "create", "--description", "Bootstrap token generated for instance replacement"], print_output=False)
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


def trigger_replacement(hostname):

    print(f"Triggering instance replacement")

    run_subprocess_wrap([*sudo_command, "scontrol", "update", f"node={hostname}", "state=fail", 'reason="Action:Replace"'], print_output=False)


def wait_for_replacement_completion(hostname):

    status_message = "Instance replacement in-progress"

    progress_dots = ProgressDots()

    while True:
        
        status = None
        captured_output = run_subprocess_wrap(["sinfo", "--node", hostname], print_output=False)
        for line in captured_output.splitlines():
            re_result = re.match(r"([^\s]+)\s+([^\s]+)\s+([^\s]+)\s+([^\s]+)\s+([^\s]+)\s+([^\s]+)", line)
            if re_result and re_result.group(6)==hostname:
                status = re_result.group(5)

        if status=="idle":
            break

        progress_dots.tick(status_message)

        time.sleep(10)

    progress_dots.tick(None)


def delete_orphan_nodes():

    # get list of existing nodes from HyperPod's resource_config.json
    existing_instance_addresses = set()
    for instance in ResourceConfig.instance().iter_instances():
        existing_instance_addresses.add(instance["CustomerIpAddress"])

    # get list of nodes from kubectl get nodes
    captured_output = run_subprocess_wrap(["kubectl", "get", "nodes", "-o", "json"], print_output=False)
    d = json.loads(captured_output)

    # check the status of nodes and list orphan nodes to delete
    node_names_to_delete = []
    for node in d["items"]:

        if node["kind"]!="Node":
            continue

        if "node-role.kubernetes.io/control-plane" in node["metadata"]["labels"]:
            continue

        for address in node["status"]["addresses"]:
            if address["type"]=="InternalIP":
                instance_address = address["address"]
                break
        else:
            assert False, "IP address not found"

        for status_condition in node["status"]["conditions"]:
            if status_condition["type"]=="Ready":
                ready_status = status_condition["status"]
                break
        else:
            assert False, "Ready status not found"
        
        if ready_status=="Unknown" and instance_address not in existing_instance_addresses:
            node_names_to_delete.append(node["metadata"]["name"])

    if not node_names_to_delete:
        print("No orphan node detected")
        return

    print("Orphan nodes:")
    for node_name in node_names_to_delete:
        print(f"  {node_name}")

    # Confirm deletion
    answer = input("Delete these orphan nodes? [y/N]")

    # Delete
    if answer.lower() in ["y", "yes"]:
        for node_name in node_names_to_delete:
            print(f"  Deleting {node_name}")
            run_subprocess_wrap(["kubectl", "delete", "node", node_name], print_output=True)



def cmd_replace_instance(args):

    generate_new_token()
    trigger_replacement(args.hostname)
    wait_for_replacement_completion(args.hostname)

    print("Finished replacing instance")


def cmd_generate_new_token(args):

    generate_new_token()

    print("Finished")


def cmd_delete_orphan_nodes(args):

    delete_orphan_nodes()
    
    
if __name__ == "__main__":

    argparser1 = argparse.ArgumentParser( description = 'K8 on HyperPod operation tool' )
    subparsers = argparser1.add_subparsers()

    help = 'Replace an instance'
    argparser2 = subparsers.add_parser( "replace-instance", help=help, description=help )
    argparser2.add_argument('hostname', metavar="HOSTNAME", action="store", help="Hostname to replace (e.g. ip-10.0.12.34)")
    argparser2.set_defaults(func=cmd_replace_instance)

    help = 'Generate a new token for scaling-up'
    argparser2 = subparsers.add_parser( "generate-new-token", help=help, description=help )
    argparser2.set_defaults(func=cmd_generate_new_token)

    help = 'Delete orphan nodes (after cluster roll-back)'
    argparser2 = subparsers.add_parser( "delete-orphan-nodes", help=help, description=help )
    argparser2.set_defaults(func=cmd_delete_orphan_nodes)

    args = argparser1.parse_args( sys.argv[1:] )
    if hasattr(args,"func"):
        args.func(args)
    else:
        argparser1.print_usage()
