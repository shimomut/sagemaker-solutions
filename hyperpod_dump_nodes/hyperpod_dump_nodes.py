import argparse
import csv

import boto3


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


def dump_nodes(cluster_name):
    
    sagemaker_client = boto3.client("sagemaker")
    
    nodes = list_cluster_nodes_all( sagemaker_client, cluster_name )

    with open("nodes.csv", "w") as fd:
        csv_writer = csv.writer(fd)
        csv_writer.writerow([
            "instance-id", 
            "status", 
            "hostname", 
            "IP address"
        ])

        for node in nodes:
            .......


if __name__ == "__main__":

    argparser = argparse.ArgumentParser(description="Dump all HyperPod cluster nodes and their details in a CSV")
    argparser.add_argument("--cluster-name", action="store", required=True, help="Name of cluster to dump")
    args = argparser.parse_args()

    dump_nodes(args.cluster_name)
