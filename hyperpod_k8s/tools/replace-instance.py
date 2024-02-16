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


def generate_new_join_token():

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


def replace_instance(hostname):

    generate_new_join_token()
    trigger_replacement(hostname)
    wait_for_replacement_completion(hostname)


if __name__ == "__main__":

    argparser = argparse.ArgumentParser(description="Script to replace faulty node")
    argparser.add_argument('--hostname', action="store", required=True, help="Hostname (e.g. ip-10.0.12.34)")
    args = argparser.parse_args()

    replace_instance( hostname=args.hostname )
