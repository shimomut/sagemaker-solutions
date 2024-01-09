
import boto3


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
