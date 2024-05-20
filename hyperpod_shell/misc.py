
import concurrent.futures
import pexpect
import pexpect.popen_spawn
import signal

import boto3

from config import Config


def get_region():
    boto3_session = boto3.session.Session()
    region = boto3_session.region_name
    return region


def list_clusters_all(sagemaker_client):

    clusters = []    
    next_token = None

    while True:
        
        params = {}
        if next_token:
            params["NextToken"] = next_token

        response = sagemaker_client.list_clusters(**params)

        clusters += response["ClusterSummaries"]

        if "NextToken" in response and response["NextToken"]:
            next_token = response["NextToken"]
            continue

        break

    return clusters


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


def list_log_streams_all(logs_client, log_group):

    streams = []
    next_token = None

    while True:
        
        params = {
            "logGroupName" : log_group,
            "limit" : 50,
        }
        if next_token:
            params["nextToken"] = next_token

        response = logs_client.describe_log_streams(**params)

        streams += response["logStreams"]

        if "nextToken" in response and response["nextToken"]:
            next_token = response["nextToken"]
            continue

        break

    return streams


class Hostnames:

    _instance = None

    @staticmethod
    def instance():
        if Hostnames._instance is None:
            Hostnames._instance = Hostnames()
        return Hostnames._instance

    def __init__(self):
        self.node_id_to_hostname = {}
        self.hostname_to_node_id = {}

    def resolve(self, cluster, nodes):

        cluster_id = cluster["ClusterArn"].split("/")[-1]

        with concurrent.futures.ThreadPoolExecutor(max_workers=16) as thread_pool:
            
            def resolve_hostname(node):

                node_id = node["InstanceId"]

                if node_id in self.node_id_to_hostname and self.node_id_to_hostname[node_id]:
                    return self.node_id_to_hostname[node_id]

                instance_group_name = node["InstanceGroupName"]
                ssm_target = f"sagemaker-cluster:{cluster_id}_{instance_group_name}-{node_id}"
                
                hostname = None

                p = pexpect.popen_spawn.PopenSpawn([*Config.cmd_aws, "ssm", "start-session", "--target", ssm_target])
                try:
                    p.expect("#")
                    cmd = f"hostname"
                    p.sendline(cmd)
                    p.expect("#")

                    for line in p.before.decode("utf-8").strip().splitlines():
                        if line.startswith("ip-"):
                            hostname = line
                            break
                except pexpect.exceptions.EOF:
                    pass

                p.kill(signal.SIGINT)

                return hostname

            for node, hostname in zip( nodes, thread_pool.map(resolve_hostname, nodes) ):
                node_id = node["InstanceId"]
                self.node_id_to_hostname[node_id] = hostname
                self.hostname_to_node_id[hostname] = node_id

    def get_hostname(self, node_id):
        return self.node_id_to_hostname[node_id]

    def get_node_id(self, hostname):
        return self.hostname_to_node_id[hostname]


def get_max_len( d, keys ):

    if not isinstance( keys, (list,tuple) ):
        keys = [keys]

    max_len = 0
    for item in d:
        for k in keys:
            item = item[k]
        max_len = max(len(item),max_len)
    return max_len


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
