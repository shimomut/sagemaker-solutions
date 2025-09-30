#!/usr/bin/env python3
"""
HyperPod Multi-Node Command Runner

A utility to execute commands on all nodes in a HyperPod cluster using SSM sessions.
"""

import argparse
import boto3
import pexpect
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Tuple


class HyperPodMultiNodeRunner:
    def __init__(self):
        self.sagemaker_client = boto3.client('sagemaker')
        self.ec2_client = boto3.client('ec2')
        self.cluster_name = None
        self.nodes = []
    
    def get_cluster_nodes(self, cluster_name: str) -> List[Dict]:
        """Get all nodes in the HyperPod cluster."""
        try:
            # Get cluster details
            print(f"Describing cluster: {cluster_name}")
            response = self.sagemaker_client.describe_cluster(ClusterName=cluster_name)
            
            print(f"Cluster status: {response.get('ClusterStatus', 'Unknown')}")
            
            # Try multiple approaches to find instances
            instance_ids = []
            
            # Method 1: Use SageMaker list_cluster_nodes API if available
            try:
                nodes_response = self.sagemaker_client.list_cluster_nodes(ClusterName=cluster_name)
                print(f"Found {len(nodes_response.get('ClusterNodeSummaries', []))} nodes via list_cluster_nodes")
                
                for node in nodes_response.get('ClusterNodeSummaries', []):
                    instance_id = node.get('InstanceId')
                    if instance_id:
                        instance_ids.append({
                            'InstanceId': instance_id,
                            'NodeGroup': node.get('InstanceGroupName', 'unknown'),
                            'InstanceType': node.get('InstanceType', 'unknown'),
                            'LaunchTime': node.get('LaunchTime', 'unknown'),
                            'InstanceStatus': node.get('InstanceStatus', {}).get('Status', 'unknown')
                        })
                        
            except Exception as e:
                print(f"list_cluster_nodes not available or failed: {e}")
            
            # Method 2: Search EC2 instances with various tag patterns
            if not instance_ids:
                print("Trying EC2 tag-based search...")
                
                # Try different tag combinations that HyperPod might use
                tag_filters = [
                    # Standard SageMaker cluster tags
                    [
                        {'Name': 'tag:sagemaker:cluster-name', 'Values': [cluster_name]},
                        {'Name': 'instance-state-name', 'Values': ['running']}
                    ],
                    # Alternative tag patterns
                    [
                        {'Name': 'tag:aws:sagemaker:cluster-name', 'Values': [cluster_name]},
                        {'Name': 'instance-state-name', 'Values': ['running']}
                    ],
                    [
                        {'Name': 'tag:ClusterName', 'Values': [cluster_name]},
                        {'Name': 'instance-state-name', 'Values': ['running']}
                    ],
                    # Search by name pattern
                    [
                        {'Name': 'tag:Name', 'Values': [f'*{cluster_name}*']},
                        {'Name': 'instance-state-name', 'Values': ['running']}
                    ]
                ]
                
                for filters in tag_filters:
                    try:
                        print(f"Trying filter: {filters}")
                        ec2_response = self.ec2_client.describe_instances(Filters=filters)
                        
                        for reservation in ec2_response['Reservations']:
                            for instance in reservation['Instances']:
                                instance_id = instance['InstanceId']
                                
                                # Get all tags for debugging
                                tags = {tag['Key']: tag['Value'] for tag in instance.get('Tags', [])}
                                
                                # Try to determine node group from various tag patterns
                                node_group = (
                                    tags.get('sagemaker:node-group-name') or
                                    tags.get('aws:sagemaker:node-group-name') or
                                    tags.get('NodeGroupName') or
                                    tags.get('InstanceGroupName') or
                                    'unknown'
                                )
                                
                                instance_ids.append({
                                    'InstanceId': instance_id,
                                    'NodeGroup': node_group,
                                    'PrivateIpAddress': instance.get('PrivateIpAddress', 'N/A'),
                                    'InstanceType': instance.get('InstanceType', 'unknown'),
                                    'LaunchTime': instance.get('LaunchTime', 'unknown'),
                                    'Tags': tags  # Include all tags for debugging
                                })
                        
                        if instance_ids:
                            print(f"Found {len(instance_ids)} instances with filter set")
                            break
                            
                    except Exception as e:
                        print(f"Filter failed: {e}")
                        continue
            
            # Method 3: If still no instances, try broader search
            if not instance_ids:
                print("Trying broader search for any running instances...")
                try:
                    # Get all running instances and check their tags
                    ec2_response = self.ec2_client.describe_instances(
                        Filters=[{'Name': 'instance-state-name', 'Values': ['running']}]
                    )
                    
                    for reservation in ec2_response['Reservations']:
                        for instance in reservation['Instances']:
                            tags = {tag['Key']: tag['Value'] for tag in instance.get('Tags', [])}
                            
                            # Check if any tag value contains the cluster name
                            cluster_related = any(
                                cluster_name.lower() in str(value).lower() 
                                for value in tags.values()
                            )
                            
                            if cluster_related:
                                instance_id = instance['InstanceId']
                                node_group = (
                                    tags.get('sagemaker:node-group-name') or
                                    tags.get('aws:sagemaker:node-group-name') or
                                    tags.get('NodeGroupName') or
                                    tags.get('InstanceGroupName') or
                                    'unknown'
                                )
                                
                                instance_ids.append({
                                    'InstanceId': instance_id,
                                    'NodeGroup': node_group,
                                    'PrivateIpAddress': instance.get('PrivateIpAddress', 'N/A'),
                                    'InstanceType': instance.get('InstanceType', 'unknown'),
                                    'LaunchTime': instance.get('LaunchTime', 'unknown'),
                                    'Tags': tags
                                })
                                
                except Exception as e:
                    print(f"Broader search failed: {e}")
            
            print(f"Total instances found: {len(instance_ids)}")
            return instance_ids
            
        except Exception as e:
            print(f"Error getting cluster nodes: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    def execute_command_on_node(self, instance_id: str, command: str, timeout: int = 30) -> Tuple[str, str, bool]:
        """Execute a command on a single node via SSM."""
        try:
            # Start SSM session
            ssm_command = f"aws ssm start-session --target {instance_id}"
            
            # Use pexpect to handle the interactive session
            child = pexpect.spawn(ssm_command, timeout=timeout)
            
            # Wait for shell prompt (common prompts)
            child.expect([r'\$', r'#', r'>', pexpect.TIMEOUT], timeout=10)
            
            # Send the command
            child.sendline(command)
            
            # Wait for command to complete and get output
            child.expect([r'\$', r'#', r'>', pexpect.TIMEOUT], timeout=timeout)
            
            # Get the output
            output = child.before.decode('utf-8', errors='ignore')
            
            # Clean up the output (remove the command echo)
            lines = output.split('\n')
            if len(lines) > 1:
                # Remove first line (command echo) and last line (prompt)
                output = '\n'.join(lines[1:-1]).strip()
            
            # Close the session
            child.sendline('exit')
            child.close()
            
            return instance_id, output, True
            
        except pexpect.TIMEOUT:
            return instance_id, f"Command timed out after {timeout} seconds", False
        except pexpect.EOF:
            return instance_id, "Session ended unexpectedly", False
        except Exception as e:
            return instance_id, f"Error: {str(e)}", False
    
    def run_command_on_all_nodes(self, command: str, max_workers: int = 10) -> None:
        """Execute command on all nodes concurrently."""
        if not self.nodes:
            print("No nodes available. Please check cluster name.")
            return
        
        print(f"\nExecuting command on {len(self.nodes)} nodes: {command}")
        print("-" * 60)
        
        # Use ThreadPoolExecutor for concurrent execution
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit tasks for all nodes
            future_to_node = {
                executor.submit(self.execute_command_on_node, node['InstanceId'], command): node
                for node in self.nodes
            }
            
            # Collect results as they complete
            for future in as_completed(future_to_node):
                node = future_to_node[future]
                try:
                    instance_id, output, success = future.result()
                    status = "✓" if success else "✗"
                    node_group = node.get('NodeGroup', 'unknown')
                    
                    print(f"[{status}] {instance_id} ({node_group}):")
                    if output.strip():
                        # Indent output for better readability
                        indented_output = '\n'.join(f"    {line}" for line in output.split('\n'))
                        print(indented_output)
                    else:
                        print("    (no output)")
                    print()
                    
                except Exception as e:
                    print(f"[✗] {node['InstanceId']}: Exception occurred: {e}")
                    print()
        
        print("-" * 60)
        print("Command execution completed on all nodes.\n")
    
    def interactive_mode(self):
        """Run in interactive mode with command input loop."""
        while True:
            try:
                command = input("Enter command to run on all nodes (or 'exit' to quit): ").strip()
                
                if command.lower() in ['exit', 'quit', 'q']:
                    print("Goodbye!")
                    break
                
                if not command:
                    continue
                
                self.run_command_on_all_nodes(command)
                
            except KeyboardInterrupt:
                print("\n\nInterrupted by user. Exiting...")
                break
            except EOFError:
                print("\nExiting...")
                break
    
    def debug_cluster_info(self, cluster_name: str):
        """Debug cluster information."""
        try:
            print(f"\n=== DEBUG: Cluster Information ===")
            response = self.sagemaker_client.describe_cluster(ClusterName=cluster_name)
            
            print(f"Cluster Name: {response.get('ClusterName')}")
            print(f"Cluster Status: {response.get('ClusterStatus')}")
            print(f"Creation Time: {response.get('CreationTime')}")
            
            node_groups = response.get('NodeGroups', [])
            print(f"Node Groups: {len(node_groups)}")
            
            for i, ng in enumerate(node_groups):
                print(f"  Node Group {i+1}:")
                print(f"    Name: {ng.get('InstanceGroupName')}")
                print(f"    Type: {ng.get('InstanceType')}")
                print(f"    Count: {ng.get('CurrentCount', 'N/A')}")
                print(f"    Target Count: {ng.get('TargetCount', 'N/A')}")
                
        except Exception as e:
            print(f"Debug failed: {e}")
    
    def run(self):
        """Main execution method."""
        print("HyperPod Multi-Node Command Runner")
        print("=" * 40)
        
        # Get cluster name
        try:
            cluster_name = input("Enter HyperPod cluster name: ").strip()
            if not cluster_name:
                print("Cluster name cannot be empty.")
                return
            
            self.cluster_name = cluster_name
            
        except KeyboardInterrupt:
            print("\nExiting...")
            return
        
        # Debug cluster info
        self.debug_cluster_info(cluster_name)
        
        # Get cluster nodes
        print(f"\nFetching nodes for cluster: {cluster_name}")
        self.nodes = self.get_cluster_nodes(cluster_name)
        
        if not self.nodes:
            print(f"\nNo running nodes found in cluster '{cluster_name}'.")
            print("\nTroubleshooting steps:")
            print("1. Verify cluster name is correct")
            print("2. Check cluster status (should be 'InService')")
            print("3. Ensure instances are in 'running' state")
            print("4. Verify AWS permissions for SageMaker and EC2")
            print("5. Try running: aws sagemaker describe-cluster --cluster-name", cluster_name)
            print("6. Try running: aws sagemaker list-cluster-nodes --cluster-name", cluster_name)
            
            # Offer to show all running instances for debugging
            try:
                show_all = input("\nShow all running EC2 instances for debugging? (y/n): ").strip().lower()
                if show_all == 'y':
                    self.show_all_running_instances()
            except KeyboardInterrupt:
                pass
            
            return
        
        # Display found nodes
        print(f"\nFound {len(self.nodes)} nodes in cluster: {cluster_name}")
        for node in self.nodes:
            node_group = node.get('NodeGroup', 'unknown')
            private_ip = node.get('PrivateIpAddress', 'N/A')
            instance_type = node.get('InstanceType', 'unknown')
            print(f"- {node['InstanceId']} ({node_group}) - {private_ip} [{instance_type}]")
        
        print("\nStarting interactive mode...")
        print("Note: Commands will be executed on ALL nodes simultaneously.")
        print("Use 'exit' to quit the tool.\n")
        
        # Start interactive mode
        self.interactive_mode()
    
    def show_all_running_instances(self):
        """Show all running instances for debugging."""
        try:
            print("\n=== All Running EC2 Instances ===")
            response = self.ec2_client.describe_instances(
                Filters=[{'Name': 'instance-state-name', 'Values': ['running']}]
            )
            
            count = 0
            for reservation in response['Reservations']:
                for instance in reservation['Instances']:
                    count += 1
                    instance_id = instance['InstanceId']
                    instance_type = instance.get('InstanceType', 'unknown')
                    private_ip = instance.get('PrivateIpAddress', 'N/A')
                    
                    # Get tags
                    tags = {tag['Key']: tag['Value'] for tag in instance.get('Tags', [])}
                    name = tags.get('Name', 'unnamed')
                    
                    print(f"{count}. {instance_id} - {name} [{instance_type}] - {private_ip}")
                    
                    # Show relevant tags
                    relevant_tags = {k: v for k, v in tags.items() 
                                   if any(keyword in k.lower() for keyword in 
                                         ['sagemaker', 'cluster', 'node', 'group'])}
                    if relevant_tags:
                        for k, v in relevant_tags.items():
                            print(f"    {k}: {v}")
                    
                    if count >= 20:  # Limit output
                        print("... (showing first 20 instances)")
                        break
                        
        except Exception as e:
            print(f"Failed to list instances: {e}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description='HyperPod Multi-Node Command Runner')
    parser.add_argument('--cluster', '-c', help='HyperPod cluster name')
    parser.add_argument('--debug', '-d', action='store_true', help='Enable debug mode')
    parser.add_argument('--list-instances', '-l', action='store_true', 
                       help='List all running instances and exit')
    
    args = parser.parse_args()
    
    try:
        runner = HyperPodMultiNodeRunner()
        
        if args.list_instances:
            runner.show_all_running_instances()
            return
            
        if args.cluster:
            runner.cluster_name = args.cluster
            if args.debug:
                runner.debug_cluster_info(args.cluster)
            runner.nodes = runner.get_cluster_nodes(args.cluster)
            if runner.nodes:
                print(f"Found {len(runner.nodes)} nodes in cluster: {args.cluster}")
                for node in runner.nodes:
                    node_group = node.get('NodeGroup', 'unknown')
                    private_ip = node.get('PrivateIpAddress', 'N/A')
                    instance_type = node.get('InstanceType', 'unknown')
                    print(f"- {node['InstanceId']} ({node_group}) - {private_ip} [{instance_type}]")
                print()
                runner.interactive_mode()
            else:
                print(f"No nodes found for cluster: {args.cluster}")
        else:
            runner.run()
            
    except KeyboardInterrupt:
        print("\nExiting...")
    except Exception as e:
        print(f"Unexpected error: {e}")
        if args.debug:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()