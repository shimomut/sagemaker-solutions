import boto3
import signal

import pexpect
import pexpect.popen_spawn

# ---
# Please configure following fields for your environment

class Config:
    cluster_name = "G5-1"
    cmd_aws = ["aws"]
    worker_instance_group_name = "WorkerGroup"

# ---

sagemaker_client = boto3.client("sagemaker")

def list_cluster_nodes_all(sagemaker_client, cluster_name):

    nodes = []
    next_token = None

    while True:
        
        params = {
            "ClusterName" : cluster_name
        }
        if next_token:
            params["NextToken"] = next_token

        response = sagemaker_client.list_cluster_nodes(**params)

        nodes += response["ClusterNodeSummaries"]

        if "NextToken" in response and response["NextToken"]:
            next_token = response["NextToken"]
            continue

        break

    return nodes


def print_pexpect_output(p):
    print( p.before.decode("utf-8") + p.after.decode("utf-8"), end="" )
    

def main():

    try:
        cluster = sagemaker_client.describe_cluster(
            ClusterName = Config.cluster_name
        )
    except sagemaker_client.exceptions.ResourceNotFound:
        print(f"Cluster [{Config.cluster_name}] not found.")
        return
    
    nodes = list_cluster_nodes_all( sagemaker_client, Config.cluster_name )

    cluster_id = cluster["ClusterArn"].split("/")[-1]
    
    num_restarted = 0

    for node in nodes:
        
        instance_group_name = node["InstanceGroupName"]
        
        if instance_group_name != Config.worker_instance_group_name:
            continue
        
        node_id = node["InstanceId"]
        ssm_target = f"sagemaker-cluster:{cluster_id}_{instance_group_name}-{node_id}"

        print(f"Logging into {node_id}")

        p = pexpect.popen_spawn.PopenSpawn([*Config.cmd_aws, "ssm", "start-session", "--target", ssm_target])
        p.expect("#")
        print_pexpect_output(p)
        cmd = f"sudo systemctl restart slurmd.service"
        p.sendline(cmd)
        p.expect("#")
        print_pexpect_output(p)

        p.kill(signal.SIGINT)
        
        print("")
        print(f"Done {node_id}.")
        print("")
        
        num_restarted += 1

    print(f"Restarted slurmd in {num_restarted} instances")
    

main()
