import os
import json
import pprint
import argparse
import urllib

import boto3


callback_port = 8080
callback_path = "/secret"

# FIXME: for testing
os.environ['AWS_REGION'] = "us-west-2"
skip_node_status_check = True


def provide_secret(cluster_name, node_id, secret_name):
    
    print(cluster_name, node_id, secret_name)

    region_name = os.environ['AWS_REGION']

    # ----------
    # Getting node details

    sagemaker_client = boto3.client("sagemaker", region_name=region_name )
    response = sagemaker_client.describe_cluster_node(ClusterName=cluster_name, NodeId=node_id)
    pprint.pprint(response["NodeDetails"])

    node_status = response["NodeDetails"]["InstanceStatus"]["Status"]
    node_ipaddr = response["NodeDetails"]["PrivatePrimaryIp"]

    # We may be able to use this information to varidate that the node is 
    # really running lifecycle script in SystemUpdating status
    last_software_update_time = response["NodeDetails"]["LastSoftwareUpdateTime"]

    # ----------
    # Validate node status

    if not skip_node_status_check:
        if node_status not in ["Pending", "SystemUpdating"]:
            # FIXME: should return failure
            assert False, "Node is not in Pending/SystemUpdating status"

    # TODO: Validate providing only one time

    # ----------
    # Getting secret

    secretsmanager_client = boto3.client("secretsmanager", region_name=region_name)
    response = secretsmanager_client.get_secret_value(SecretId=secret_name)
    secret = json.loads(response["SecretString"])
    pprint.pprint(secret)

    # ----------
    # Callback to lifecycle script

    url = f"http://{node_ipaddr}:{callback_port}{callback_path}"

    data = {
        "secret": secret
    }

    # Convert data to JSON string and encode as bytes
    data_bytes = json.dumps(data).encode('utf-8')

    # Create request object with headers
    headers = {
        'Content-Type': 'application/json',
    }

    # Create the request
    req = urllib.request.Request(
        url=url,
        data=data_bytes,
        headers=headers,
        method='POST'
    )

    try:
        # Send the request and get the response
        with urllib.request.urlopen(req) as response:
            response_data = response.read().decode('utf-8')
            print(f"Response: {response_data}")
    except urllib.error.URLError as e:
        print(f"Error: {e.reason}")



if __name__ == '__main__':

    argparser = argparse.ArgumentParser(description="Lambda function to get secret value and call back to lifecycle script")
    argparser.add_argument('--cluster-name', action="store", required=True, help='Cluster name')
    argparser.add_argument('--node-id', action="store", required=True, help='Instance ID to callback')
    argparser.add_argument('--secret-name', action="store", required=True, help='Secret name')
    args = argparser.parse_args()

    provide_secret(args.cluster_name, args.node_id, args.secret_name)
