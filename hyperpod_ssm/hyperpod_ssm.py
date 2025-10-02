#!/usr/bin/env python3
"""
HyperPod SSM Interactive Shell

A utility tool that helps with SSM login to HyperPod nodes and provides 
an interactive shell for running commands.
"""

import argparse
import boto3
import subprocess
import sys
from typing import List, Dict, Optional


class HyperPodSSMShell:
    def __init__(self, debug=False):
        self.sagemaker_client = boto3.client('sagemaker')
        self.debug = debug
        self.cluster_name = None
        self.cluster_arn = None
        self.cluster_id = None
    
    def extract_cluster_id_from_arn(self, cluster_arn: str) -> str:
        """Extract cluster ID from cluster ARN."""
        if cluster_arn:
            if '/cluster/' in cluster_arn:
                return cluster_arn.split('/cluster/')[-1]
            elif ':cluster/' in cluster_arn:
                return cluster_arn.split(':cluster/')[-1]
            parts = cluster_arn.split(':')
            if len(parts) > 0:
                return parts[-1]
        return None
    
    def get_hyperpod_ssm_target(self, instance_id: str, instance_group_name: str) -> str:
        """Construct the HyperPod SSM target format."""
        if not self.cluster_id:
            raise ValueError("Cluster ID is required for HyperPod SSM targets.")
        
        return f"sagemaker-cluster:{self.cluster_id}_{instance_group_name}-{instance_id}"
    
    def list_clusters(self) -> List[Dict]:
        """List all available HyperPod clusters."""
        try:
            response = self.sagemaker_client.list_clusters()
            clusters = []
            
            for cluster in response.get('ClusterSummaries', []):
                clusters.append({
                    'Name': cluster.get('ClusterName'),
                    'Status': cluster.get('ClusterStatus'),
                    'CreationTime': cluster.get('CreationTime'),
                    'Arn': cluster.get('ClusterArn')
                })
            
            return clusters
        except Exception as e:
            print(f"Error listing clusters: {e}")
            return []
    
    def get_cluster_info(self, cluster_name: str) -> bool:
        """Get cluster information and set internal state."""
        try:
            response = self.sagemaker_client.describe_cluster(ClusterName=cluster_name)
            
            self.cluster_name = cluster_name
            self.cluster_arn = response.get('ClusterArn')
            self.cluster_id = self.extract_cluster_id_from_arn(self.cluster_arn)
            
            if self.debug:
                print(f"Cluster ARN: {self.cluster_arn}")
                print(f"Cluster ID: {self.cluster_id}")
                print(f"Cluster Status: {response.get('ClusterStatus')}")
            
            return True
        except Exception as e:
            print(f"Error getting cluster info: {e}")
            return False
    
    def get_cluster_nodes(self, cluster_name: str) -> List[Dict]:
        """Get all nodes in the HyperPod cluster."""
        try:
            nodes = []
            next_token = None
            
            while True:
                params = {'ClusterName': cluster_name}
                if next_token:
                    params['NextToken'] = next_token
                
                response = self.sagemaker_client.list_cluster_nodes(**params)
                
                for node in response.get('ClusterNodeSummaries', []):
                    instance_id = node.get('InstanceId')
                    if instance_id:
                        nodes.append({
                            'InstanceId': instance_id,
                            'NodeGroup': node.get('InstanceGroupName', 'unknown'),
                            'InstanceType': node.get('InstanceType', 'unknown'),
                            'LaunchTime': node.get('LaunchTime'),
                            'InstanceStatus': node.get('InstanceStatus', {}).get('Status', 'unknown')
                        })
                
                next_token = response.get('NextToken')
                if not next_token:
                    break
            
            return nodes
        except Exception as e:
            print(f"Error getting cluster nodes: {e}")
            return []
    
    def select_cluster(self) -> Optional[str]:
        """Interactive cluster selection."""
        clusters = self.list_clusters()
        
        if not clusters:
            print("No HyperPod clusters found.")
            return None
        
        if len(clusters) == 1:
            cluster_name = clusters[0]['Name']
            print(f"Found one cluster: {cluster_name}")
            return cluster_name
        
        print("\nAvailable HyperPod clusters:")
        for i, cluster in enumerate(clusters, 1):
            status = cluster['Status']
            print(f"{i}. {cluster['Name']} ({status})")
        
        while True:
            try:
                choice = input(f"\nSelect cluster (1-{len(clusters)}): ").strip()
                if not choice:
                    continue
                
                choice_num = int(choice)
                if 1 <= choice_num <= len(clusters):
                    selected_cluster = clusters[choice_num - 1]['Name']
                    print(f"Selected: {selected_cluster}")
                    return selected_cluster
                else:
                    print(f"Invalid choice. Please enter 1-{len(clusters)}")
            except ValueError:
                print("Invalid input. Please enter a number.")
            except KeyboardInterrupt:
                return None
    
    def select_node(self, nodes: List[Dict], instance_group: str = None) -> Optional[Dict]:
        """Interactive node selection."""
        # Filter by instance group if specified
        if instance_group:
            filtered_nodes = [n for n in nodes if n['NodeGroup'].lower() == instance_group.lower()]
            if not filtered_nodes:
                print(f"No nodes found in instance group '{instance_group}'")
                return None
            nodes = filtered_nodes
        
        if not nodes:
            print("No nodes available.")
            return None
        
        if len(nodes) == 1:
            node = nodes[0]
            print(f"Found one node: {node['InstanceId']} ({node['NodeGroup']})")
            return node
        
        # Group nodes by instance group for better display
        groups = {}
        for node in nodes:
            group = node['NodeGroup']
            if group not in groups:
                groups[group] = []
            groups[group].append(node)
        
        print(f"\nAvailable nodes ({len(nodes)} total):")
        
        node_list = []
        for group_name, group_nodes in sorted(groups.items()):
            print(f"\n  Instance Group: {group_name}")
            for node in group_nodes:
                node_list.append(node)
                idx = len(node_list)
                status = node['InstanceStatus']
                instance_type = node['InstanceType']
                print(f"    {idx}. {node['InstanceId']} ({instance_type}) [{status}]")
        
        while True:
            try:
                choice = input(f"\nSelect node (1-{len(node_list)}): ").strip()
                if not choice:
                    continue
                
                choice_num = int(choice)
                if 1 <= choice_num <= len(node_list):
                    selected_node = node_list[choice_num - 1]
                    print(f"Selected: {selected_node['InstanceId']} ({selected_node['NodeGroup']})")
                    return selected_node
                else:
                    print(f"Invalid choice. Please enter 1-{len(node_list)}")
            except ValueError:
                print("Invalid input. Please enter a number.")
            except KeyboardInterrupt:
                return None
    
    def start_ssm_session(self, node: Dict) -> bool:
        """Start an interactive SSM session to the specified node."""
        instance_id = node['InstanceId']
        instance_group = node['NodeGroup']
        
        try:
            ssm_target = self.get_hyperpod_ssm_target(instance_id, instance_group)
            if self.debug:
                print(f"SSM Target: {ssm_target}")
            
            print(f"Connecting to {instance_id} ({instance_group})...")
            print("Type 'exit' to disconnect from the session.")
            print("-" * 50)
            
            # Start the SSM session directly - user will interact with it
            result = subprocess.run([
                'aws', 'ssm', 'start-session', 
                '--target', ssm_target
            ])
            
            print("-" * 50)
            print("SSM session ended.")
            
            return result.returncode == 0
            
        except KeyboardInterrupt:
            print("\nSession interrupted by user.")
            return True
        except FileNotFoundError:
            print("Error: AWS CLI not found. Please install and configure AWS CLI.")
            return False
        except Exception as e:
            print(f"Error starting SSM session: {e}")
            return False
    
    def connect_to_node(self, node: Dict):
        """Connect to a node and handle reconnection logic."""
        while True:
            success = self.start_ssm_session(node)
            
            if not success:
                print("Connection failed.")
                retry = input("Retry connection? (y/n): ").strip().lower()
                if retry != 'y':
                    break
            else:
                # Ask if user wants to reconnect or switch nodes
                print("\nConnection options:")
                print("1. Reconnect to same node")
                print("2. Switch to different node") 
                print("3. Exit")
                
                try:
                    choice = input("Choose option (1-3): ").strip()
                    if choice == '1':
                        continue  # Reconnect to same node
                    elif choice == '2':
                        return 'switch'  # Switch to different node
                    else:
                        break  # Exit
                except KeyboardInterrupt:
                    break
        
        return 'exit'
    
    def run_interactive_mode(self):
        """Run the tool in interactive mode."""
        print("HyperPod SSM Interactive Shell")
        print("=" * 35)
        
        # Get cluster name
        if not self.cluster_name:
            cluster_name = self.select_cluster()
            if not cluster_name:
                return
        else:
            cluster_name = self.cluster_name
        
        # Get cluster info
        if not self.get_cluster_info(cluster_name):
            return
        
        # Get nodes
        print(f"\nFetching nodes for cluster: {cluster_name}")
        nodes = self.get_cluster_nodes(cluster_name)
        
        if not nodes:
            print("No nodes found in cluster.")
            return
        
        print(f"Found {len(nodes)} nodes")
        
        # Main loop for node selection and connection
        while True:
            # Select node
            node = self.select_node(nodes)
            if not node:
                break
            
            # Connect to node
            result = self.connect_to_node(node)
            
            if result == 'switch':
                continue  # Go back to node selection
            else:
                break  # Exit
    
    def run_direct_mode(self, cluster_name: str, instance_group: str = None, instance_id: str = None):
        """Run with direct parameters."""
        # Get cluster info
        if not self.get_cluster_info(cluster_name):
            return
        
        # Get nodes
        nodes = self.get_cluster_nodes(cluster_name)
        if not nodes:
            print("No nodes found in cluster.")
            return
        
        # Find specific node if instance_id provided
        if instance_id:
            target_node = None
            for node in nodes:
                if node['InstanceId'] == instance_id:
                    target_node = node
                    break
            
            if not target_node:
                print(f"Instance {instance_id} not found in cluster.")
                return
            
            node = target_node
        else:
            # Select node interactively
            node = self.select_node(nodes, instance_group)
            if not node:
                return
        
        # Connect to node
        self.connect_to_node(node)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description='HyperPod SSM Interactive Shell')
    parser.add_argument('--cluster', '-c', help='HyperPod cluster name')
    parser.add_argument('--instance-group', '-g', help='Instance group name')
    parser.add_argument('--instance-id', '-i', help='Specific instance ID to connect to')
    parser.add_argument('--list-clusters', action='store_true', help='List available clusters')
    parser.add_argument('--list-nodes', action='store_true', help='List nodes in cluster')
    parser.add_argument('--debug', '-d', action='store_true', help='Enable debug mode')
    
    args = parser.parse_args()
    
    try:
        shell = HyperPodSSMShell(debug=args.debug)
        
        if args.list_clusters:
            clusters = shell.list_clusters()
            if clusters:
                print("Available HyperPod clusters:")
                for cluster in clusters:
                    status = cluster['Status']
                    print(f"  - {cluster['Name']} ({status})")
            else:
                print("No clusters found.")
            return
        
        if args.list_nodes:
            if not args.cluster:
                print("--cluster is required when using --list-nodes")
                return
            
            if not shell.get_cluster_info(args.cluster):
                return
            
            nodes = shell.get_cluster_nodes(args.cluster)
            if nodes:
                print(f"Nodes in cluster '{args.cluster}':")
                
                # Group by instance group
                groups = {}
                for node in nodes:
                    group = node['NodeGroup']
                    if group not in groups:
                        groups[group] = []
                    groups[group].append(node)
                
                for group_name, group_nodes in sorted(groups.items()):
                    print(f"\n  Instance Group: {group_name}")
                    for node in group_nodes:
                        status = node['InstanceStatus']
                        instance_type = node['InstanceType']
                        print(f"    - {node['InstanceId']} ({instance_type}) [{status}]")
            else:
                print("No nodes found.")
            return
        
        if args.cluster:
            shell.cluster_name = args.cluster
            shell.run_direct_mode(args.cluster, args.instance_group, args.instance_id)
        else:
            shell.run_interactive_mode()
    
    except KeyboardInterrupt:
        print("\nExiting...")
    except Exception as e:
        print(f"Error: {e}")
        if args.debug:
            import traceback
            traceback.print_exc()


if __name__ == '__main__':
    main()