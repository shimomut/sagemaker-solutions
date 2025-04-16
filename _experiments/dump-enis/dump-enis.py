
import boto3
import csv

subnet_id = "subnet-0cd2ac8aa9e1b24e3"

def list_network_interfaces_all():

    ec2_client = boto3.client("ec2")

    network_interfaces = []
    next_token = None

    while True:

        params = {
            "MaxResults": 100
        }

        if next_token:
            params["NextToken"] = next_token

        response = ec2_client.describe_network_interfaces( **params )

        network_interfaces += response["NetworkInterfaces"]

        if "NextToken" in response:
            next_token = response["NextToken"]
        else:
            break

    return network_interfaces

enis = list_network_interfaces_all()

#print(enis)

print(enis[0])

with open('enis.csv', 'w', newline='') as fd:

    csv_writer = csv.writer(fd)
    csv_writer.writerow(["Id", "Description", "ClusterName", "InstanceId", "NumIpAddr"])
    
    for eni in enis:

        if eni["SubnetId"] != subnet_id:
            continue

        cluster_name = None
        instance_id = None
        for tag in eni["TagSet"]:
            if tag["Key"] == "cluster.k8s.amazonaws.com/name":
                cluster_name = tag["Value"]
            if tag["Key"] == "node.k8s.amazonaws.com/instance_id":
                instance_id = tag["Value"]

        eni_id = eni["NetworkInterfaceId"]    
        desc = eni["Description"]
        num_ipaddr = len(eni["PrivateIpAddresses"])

        csv_writer.writerow([eni_id, desc, cluster_name, instance_id, num_ipaddr])
