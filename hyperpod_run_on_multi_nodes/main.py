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
        self.cluster_name = None
        self.cluster_arn = None
        self.cluster_id = None
        self.nodes = []
    
    def get_hyperpod_ssm_target(self, instance_id: str, instance_group_name: str) -> str:
        """Construct the HyperPod SSM target format."""
        if not self.cluster_id:
            return instance_id  # Fallback to regular EC2 format
        
        # Format: sagemaker-cluster:{cluster-id}_{instance-group-name}-{instance-id}
        return f"sagemaker-cluster:{self.cluster_id}_{instance_group_name}-{instance_id}"
    
    def extract_cluster_id_from_arn(self, cluster_arn: str) -> str:
        """Extract cluster ID from cluster ARN."""
        # ARN format: arn:aws:sagemaker:region:account:cluster/cluster-id
        if cluster_arn:
            if '/cluster/' in cluster_arn:
                return cluster_arn.split('/cluster/')[-1]
            elif ':cluster/' in cluster_arn:
                return cluster_arn.split(':cluster/')[-1]
            # Try splitting by colon and taking the last part
            parts = cluster_arn.split(':')
            if len(parts) > 0:
                return parts[-1]
        return None
    
    def get_cluster_nodes(self, cluster_name: str) -> List[Dict]:
        """Get all nodes in the HyperPod cluster using only SageMaker APIs."""
        try:
            # Get cluster details
            print(f"Describing cluster: {cluster_name}")
            response = self.sagemaker_client.describe_cluster(ClusterName=cluster_name)
            
            print(f"Cluster status: {response.get('ClusterStatus', 'Unknown')}")
            
            # Extract cluster ARN and ID for SSM target construction
            self.cluster_arn = response.get('ClusterArn')
            self.cluster_id = self.extract_cluster_id_from_arn(self.cluster_arn)
            print(f"Cluster ARN: {self.cluster_arn}")
            print(f"Cluster ID: {self.cluster_id}")
            
            if not self.cluster_id:
                print("Warning: Could not extract cluster ID from ARN. SSM targets may not work correctly.")
            
            # Use SageMaker list_cluster_nodes API
            instance_ids = []
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
                print(f"list_cluster_nodes failed: {e}")
                return []
            
            print(f"Total instances found: {len(instance_ids)}")
            return instance_ids
            
        except Exception as e:
            print(f"Error getting cluster nodes: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    def execute_command_on_node(self, node: Dict, command: str, timeout: int = 60) -> Tuple[str, str, bool]:
        """Execute a command on a single node via SSM."""
        instance_id = node['InstanceId']
        instance_group_name = node.get('NodeGroup', 'unknown')
        
        if not self.cluster_id:
            return instance_id, "Cluster ID not available - cannot construct HyperPod SSM target", False
        
        # Use HyperPod SSM target format only
        ssm_target = self.get_hyperpod_ssm_target(instance_id, instance_group_name)
        child = None
        
        try:
            ssm_command = f"aws ssm start-session --target {ssm_target}"

            
            # Use pexpect to handle the interactive session
            child = pexpect.spawn(ssm_command, timeout=timeout, encoding='utf-8')
            child.logfile_read = None  # Disable verbose logging
            
            # Wait for the SSM session to establish
            # Look for various possible prompts and session indicators
            session_patterns = [
                r'Starting session with SessionId:',  # SSM session start
                r'sh-\d+\.\d+\$',  # Common shell prompt
                r'\[.*@.*\][\$#]',  # Common Linux prompt
                r'[\$#]\s*$',  # Generic shell prompt
                r'.*@.*:.*[\$#]',  # User@host prompt
                pexpect.TIMEOUT
            ]
            
            # Wait for session to be ready
            index = child.expect(session_patterns, timeout=15)
            if index == len(session_patterns) - 1:  # TIMEOUT
                return instance_id, "Timeout waiting for SSM session to start", False
            
            # Give the session a moment to fully initialize
            time.sleep(2)
            
            # Send a newline to get a fresh prompt
            child.sendline('')
            
            # Wait for prompt
            try:
                child.expect([
                    r'[\$#]\s*$',  # Simple prompt
                    r'.*[\$#]',    # Any prompt
                    pexpect.TIMEOUT
                ], timeout=10)
            except Exception:
                pass
            
            # Send the actual command
            child.sendline(command)
            
            # Wait for command to execute and collect output manually
            time.sleep(3)  # Give command more time to execute
            
            raw_output = ""
            try:
                # Read all available output
                max_attempts = 10
                attempts = 0
                
                while attempts < max_attempts:
                    try:
                        chunk = child.read_nonblocking(size=1024, timeout=0.5)
                        if chunk:
                            raw_output += chunk
                            attempts = 0  # Reset counter if we're still getting data
                        else:
                            attempts += 1
                    except pexpect.TIMEOUT:
                        attempts += 1
                    except pexpect.EOF:
                        break
                        
            except Exception as e:
                return instance_id, f"Error reading command output: {str(e)}", False
            
            # Debug: show what we captured
            print(f"[DEBUG] {instance_id}: Raw output length={len(raw_output)}")
            if raw_output:
                print(f"[DEBUG] {instance_id}: Raw sample: {repr(raw_output[:100])}")
            

            
            # Clean up the output - remove command echo and prompts
            if raw_output:
                lines = raw_output.split('\n')
                cleaned_lines = []
                
                for line in lines:
                    stripped_line = line.strip()
                    
                    # Skip empty lines
                    if not stripped_line:
                        continue
                    
                    # Skip command echo lines (lines that contain the command and start with prompt)
                    if command in stripped_line and stripped_line.startswith('sh-'):
                        continue
                    
                    # Skip prompt-only lines
                    if stripped_line.startswith('sh-') and stripped_line.endswith('#'):
                        continue
                    
                    # Keep actual command output
                    cleaned_lines.append(stripped_line)
                
                output = '\n'.join(cleaned_lines)
            else:
                output = ""
            
            # Close the session gracefully
            try:
                child.sendline('exit')
                child.expect(pexpect.EOF, timeout=5)
            except:
                pass  # Ignore errors during cleanup
            
            return instance_id, output, True
            
        except pexpect.TIMEOUT:
            error_msg = f"Command '{command}' timed out after {timeout} seconds"
            if child and hasattr(child, 'before') and child.before:
                error_msg += f"\nPartial output: {child.before[:200]}..."
            return instance_id, error_msg, False
            
        except pexpect.EOF:
            error_msg = "SSM session ended unexpectedly"
            if child and hasattr(child, 'before') and child.before:
                error_msg += f"\nLast output: {child.before[:200]}..."
            return instance_id, error_msg, False
            
        except Exception as e:
            return instance_id, f"Error executing command: {str(e)}", False
            
        finally:
            # Ensure child process is cleaned up
            if child and child.isalive():
                try:
                    child.terminate(force=True)
                except:
                    pass
    
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
                executor.submit(self.execute_command_on_node, node, command): node
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
    
    def test_ssm_connectivity(self, node: Dict) -> bool:
        """Test SSM connectivity to a single node."""
        instance_id = node['InstanceId']
        instance_group_name = node.get('NodeGroup', 'unknown')
        
        print(f"Testing SSM connectivity to {instance_id} ({instance_group_name})...")
        
        # Show both target formats for debugging
        hyperpod_target = self.get_hyperpod_ssm_target(instance_id, instance_group_name)
        print(f"HyperPod SSM target: {hyperpod_target}")
        
        # Test basic connectivity
        result_instance_id, output, success = self.execute_command_on_node(node, "echo 'SSM test successful'", timeout=30)
        
        if success:
            print(f"✓ SSM connectivity test passed: {output}")
            return True
        else:
            print(f"✗ SSM connectivity test failed: {output}")
            return False
    
    def interactive_mode(self):
        """Run in interactive mode with command input loop."""
        # Test SSM connectivity on first node before starting
        if self.nodes:
            print("Testing SSM connectivity...")
            test_node = self.nodes[0]
            if not self.test_ssm_connectivity(test_node):
                print("\nSSM connectivity test failed. Please check:")
                print("1. SSM Agent is running on the instances")
                print("2. Instances have proper IAM role for SSM")
                print("3. Security groups allow SSM traffic")
                print("4. Your AWS credentials have SSM permissions")
                
                try:
                    continue_anyway = input("\nContinue anyway? (y/n): ").strip().lower()
                    if continue_anyway != 'y':
                        return
                except KeyboardInterrupt:
                    return
            else:
                print("SSM connectivity test passed!\n")
        
        while True:
            try:
                command = input("Enter command to run on all nodes (or 'exit' to quit): ").strip()
                
                if command.lower() in ['exit', 'quit', 'q']:
                    print("Goodbye!")
                    break
                
                if command.lower() == 'test':
                    # Run a simple test command
                    self.run_command_on_all_nodes("echo 'Hello from $(hostname)'")
                    continue
                
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
            
            # Suggest manual debugging steps
            print("\nFor debugging, you can try:")
            print("1. aws sagemaker describe-cluster --cluster-name", cluster_name)
            print("2. aws sagemaker list-cluster-nodes --cluster-name", cluster_name)
            
            return
        
        # Display found nodes
        print(f"\nFound {len(self.nodes)} nodes in cluster: {cluster_name}")
        for node in self.nodes:
            node_group = node.get('NodeGroup', 'unknown')
            instance_type = node.get('InstanceType', 'unknown')
            print(f"- {node['InstanceId']} ({node_group}) [{instance_type}]")
        
        print("\nStarting interactive mode...")
        print("Note: Commands will be executed on ALL nodes simultaneously.")
        print("Use 'exit' to quit the tool.\n")
        
        # Start interactive mode
        self.interactive_mode()


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description='HyperPod Multi-Node Command Runner')
    parser.add_argument('--cluster', '-c', help='HyperPod cluster name')
    parser.add_argument('--debug', '-d', action='store_true', help='Enable debug mode')
    parser.add_argument('--test-node', '-t', help='Test SSM connectivity to specific instance ID')
    parser.add_argument('--command', help='Single command to execute (non-interactive mode)')
    
    args = parser.parse_args()
    
    try:
        runner = HyperPodMultiNodeRunner()
        
        if args.test_node:
            # Test single node connectivity
            # Create a mock node object for testing
            test_node = {
                'InstanceId': args.test_node,
                'NodeGroup': 'test-group'  # Default for testing
            }
            success = runner.test_ssm_connectivity(test_node)
            sys.exit(0 if success else 1)
            
        if args.cluster:
            runner.cluster_name = args.cluster
            if args.debug:
                runner.debug_cluster_info(args.cluster)
            runner.nodes = runner.get_cluster_nodes(args.cluster)
            if runner.nodes:
                print(f"Found {len(runner.nodes)} nodes in cluster: {args.cluster}")
                for node in runner.nodes:
                    node_group = node.get('NodeGroup', 'unknown')
                    instance_type = node.get('InstanceType', 'unknown')
                    print(f"- {node['InstanceId']} ({node_group}) [{instance_type}]")
                print()
                
                if args.command:
                    # Single command mode
                    runner.run_command_on_all_nodes(args.command)
                else:
                    # Interactive mode
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