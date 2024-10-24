import sys
import os
import time
import re
import json
import argparse

import boto3

from config import Config

def extract_components_from_cluster_arn():
    re_result = re.match(r"arn:aws:sagemaker:([^:]+):([0-9]+):cluster/([a-z0-9]+)", Config.hyperpod_cluster_arn)

    if re_result is None:
        print( f"Error: malformed Cluster ARN: {Config.hyperpod_cluster_arn}" )
        sys.exit(1)

    Config.region = re_result.group(1)
    Config.account = re_result.group(2)
    Config.cluster_id = re_result.group(3)


def tags_as_dict(tags):
    d = {}
    for tag in tags:
        d[ tag["Key"] ] = tag["Value"]
    return d


def list_enis(ec2_client):
    
    def _describe_network_interfaces_all(ec2_client):
        
        network_interfaces = []
        next_token = None

        while True:

            params = {
                "MaxResults": 5
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

    eni_table = {}
    enis = _describe_network_interfaces_all(ec2_client)
    for eni in enis:
        if eni["Description"].startswith(Config.hyperpod_cluster_arn):
            eni_table[eni["Description"]] = eni
    
    return eni_table


def list_eips(ec2_client):

    response = ec2_client.describe_addresses()
    eip_table = {}
    for eip in response["Addresses"]:
        if "Tags" in eip:
            tags = tags_as_dict(eip["Tags"])
            if "HyperPodEni" in tags:
                eip_table[ tags["HyperPodEni"] ] = eip

    return eip_table


def create_missing_eips(args):

    ec2_client = boto3.client("ec2", region_name=Config.region)

    eni_table = list_enis(ec2_client)
    eip_table = list_eips(ec2_client)

    missing_eip_keys = set(eni_table.keys()) - set(eip_table.keys())

    for missing_eip_key in missing_eip_keys:

        print(f"Creating EIP - {missing_eip_key}")

        response = ec2_client.allocate_address(
            Domain="vpc",
            TagSpecifications=[
                {
                    "ResourceType": "elastic-ip",
                    "Tags": [
                        {
                            "Key": "Name",
                            "Value": f"HyperPod ({Config.cluster_id})",
                        },
                        {
                            "Key": "HyperPodEni",
                            "Value": missing_eip_key,
                        }
                    ]
                },
            ],
        )
        print(response)


def attach_eips(args):

    ec2_client = boto3.client("ec2", region_name=Config.region)

    eni_table = list_enis(ec2_client)
    eip_table = list_eips(ec2_client)

    keys = set(eni_table.keys()).intersection(set(eip_table.keys()))
    for key in keys:

        eni = eni_table[key]
        eip = eip_table[key]

        if "Association" in eni:
            if "AssociationId" in eni["Association"]:
                continue

        if "AssociationId" in eip:
            continue

        print(f"Associatating EIP with ENI - {key}")

        print(eni)
        print(eip)

        response = ec2_client.associate_address(
            AllocationId = eip["AllocationId"],
            NetworkInterfaceId = eni["NetworkInterfaceId"],
            PrivateIpAddress = eni["PrivateIpAddress"],
        )

        print(response)


def cmd_create_and_attach_eips(args):

    create_missing_eips(args)
    attach_eips(args)


def cmd_delete_unused_eips(args):

    ec2_client = boto3.client("ec2", region_name=Config.region)

    eip_table = list_eips(ec2_client)

    for key in eip_table:
        eip = eip_table[key]

        if "AssociationId" in eip:
            continue

        print(f"Releasing unused EIP - {key}")

        response = ec2_client.release_address(
            AllocationId = eip["AllocationId"],
        )

        print(response)


def cmd_clean_up(args):
    
    ec2_client = boto3.client("ec2", region_name=Config.region)

    eip_table = list_eips(ec2_client)

    # Disassociate and delete EIPs
    for key in eip_table:
        eip = eip_table[key]
        if "AssociationId" in eip:

            print(f"Disassociating EIP from ENI - {key}")

            response = ec2_client.disassociate_address(
                AssociationId = eip["AssociationId"]
            )

            print(response)

        print(f"Releasing EIP - {key}")

        response = ec2_client.release_address(
            AllocationId = eip["AllocationId"],
        )

        print(response)


    
if __name__ == "__main__":

    extract_components_from_cluster_arn()

    argparser1 = argparse.ArgumentParser( description = 'HyperPod subnet public/private switching tool' )
    subparsers = argparser1.add_subparsers()

    help = "Create and attach EIPs to ENIs if it is not done yet"
    argparser2 = subparsers.add_parser( "create-and-attach-eips", help=help, description=help )
    argparser2.set_defaults(func=cmd_create_and_attach_eips)

    help = "Delete unused EIPs"
    argparser2 = subparsers.add_parser( "delete-unused-eips", help=help, description=help )
    argparser2.set_defaults(func=cmd_delete_unused_eips)

    # help = "Switch route table association"
    # argparser2 = subparsers.add_parser( "switch-route", help=help, description=help )
    # argparser2.set_defaults(func=cmd_switch_route)

    help = "Clean up all for testing"
    argparser2 = subparsers.add_parser( "clean-up", help=help, description=help )
    argparser2.set_defaults(func=cmd_clean_up)

    args = argparser1.parse_args( sys.argv[1:] )
    if hasattr(args,"func"):
        args.func(args)
    else:
        argparser1.print_usage()
