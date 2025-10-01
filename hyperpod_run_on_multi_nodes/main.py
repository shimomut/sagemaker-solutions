#!/usr/bin/env python3
"""
HyperPod Multi-Node Command Runner

A utility to execute commands on all nodes in a HyperPod cluster using SSM sessions.
"""

import argparse
import boto3
import pexpect
import re
import signal
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Tuple


class HyperPodMultiNodeRunner:
    def __init__(self, debug=False):
        self.sagemaker_client = boto3.client('sagemaker')
        self.cluster_name = None
        self.cluster_arn = None
        self.cluster_id = None
        self.nodes = []
        self.debug = debug
        self.current_instance_group = None  # For interactive mode filtering
    
    def get_hyperpod_ssm_target(self, instance_id: str, instance_group_name: str) -> str:
        """Construct the HyperPod SSM target format."""
        if not self.cluster_id:
            raise ValueError("Cluster ID is required for HyperPod SSM targets. Cannot proceed without valid cluster information.")
        
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
            
            # Use SageMaker list_cluster_nodes API with pagination support
            instance_ids = []
            next_token = None
            page_count = 0
            
            try:
                while True:
                    page_count += 1
                    print(f"Fetching nodes page {page_count}...")
                    
                    # Prepare API call parameters
                    list_params = {'ClusterName': cluster_name}
                    if next_token:
                        list_params['NextToken'] = next_token
                    
                    nodes_response = self.sagemaker_client.list_cluster_nodes(**list_params)
                    
                    # Process nodes from current page
                    current_page_nodes = nodes_response.get('ClusterNodeSummaries', [])
                    print(f"Found {len(current_page_nodes)} nodes on page {page_count}")
                    
                    for node in current_page_nodes:
                        instance_id = node.get('InstanceId')
                        if instance_id:
                            instance_ids.append({
                                'InstanceId': instance_id,
                                'NodeGroup': node.get('InstanceGroupName', 'unknown'),
                                'InstanceType': node.get('InstanceType', 'unknown'),
                                'LaunchTime': node.get('LaunchTime', 'unknown'),
                                'InstanceStatus': node.get('InstanceStatus', {}).get('Status', 'unknown')
                            })
                    
                    # Check if there are more pages
                    next_token = nodes_response.get('NextToken')
                    if not next_token:
                        break
                
                print(f"Completed pagination: {page_count} pages processed")
                        
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
        """Execute a command on a single node via SSM using improved prompt handling for AL2023."""
        instance_id = node['InstanceId']
        instance_group_name = node.get('NodeGroup', 'unknown')
        
        # Use HyperPod SSM target format
        try:
            ssm_target = self.get_hyperpod_ssm_target(instance_id, instance_group_name)
        except ValueError as e:
            return instance_id, f"Failed to construct HyperPod SSM target: {str(e)}", False
        child = None
        
        # Custom prompt for reliable output parsing
        custom_prompt = "PEXPECT_READY# "
        
        def print_pexpect_output(p):
            """Helper function to print pexpect output for debugging."""
            if self.debug:
                print(f"[DEBUG] {instance_id} Before: {repr(p.before)}")
                print(f"[DEBUG] {instance_id} After: {repr(p.after)}")
        
        try:
            ssm_command = f"aws ssm start-session --target {ssm_target}"
            
            if self.debug:
                print(f"[DEBUG] {instance_id}: Starting SSM session with command: {ssm_command}")
            
            # Use pexpect to handle the interactive session
            child = pexpect.spawn(ssm_command, timeout=timeout, encoding='utf-8')
            child.logfile_read = None  # Disable verbose logging
            
            # AL2023 compatibility: Wait for SSM session establishment first
            if self.debug:
                print(f"[DEBUG] {instance_id}: Waiting for SSM session establishment...")
            
            # More flexible initial prompt detection for AL2023
            # AL2023 may have different prompt formats, so we try multiple patterns
            initial_prompt_patterns = [
                r'[\$#]\s+',            # HyperPod Slurm
                r'sh-\d+\.\d+[\$#]\s*', # HyperPod EKS
                pexpect.TIMEOUT         # Fallback for timeout
            ]
            
            if self.debug:
                print(f"[DEBUG] {instance_id}: Waiting for initial prompt...")
            
            # Try to match any of the prompt patterns with extended timeout for AL2023
            prompt_index = child.expect(initial_prompt_patterns, timeout=30)
            
            if prompt_index == len(initial_prompt_patterns) - 1:  # TIMEOUT case
                if self.debug:
                    print(f"[DEBUG] {instance_id}: Initial prompt timeout, trying to proceed anyway...")
                # Send a newline to potentially trigger a prompt
                child.sendline('')
                try:
                    child.expect(initial_prompt_patterns[:-1], timeout=10)
                except pexpect.TIMEOUT:
                    return instance_id, "Failed to establish shell session - no prompt detected", False
            
            if self.debug:
                print(f"[DEBUG] {instance_id}: Initial prompt detected (pattern {prompt_index})")
                print_pexpect_output(child)
            
            # Set the custom prompt with explicit formatting
            # Use a marker-based approach to avoid matching the prompt in the command itself
            child.sendline(f'export PS1="{custom_prompt}"')
            
            # Send a unique marker command to verify the new prompt is active
            marker_command = 'echo "PROMPT_SET_MARKER"'
            child.sendline(marker_command)
            
            # Wait for the marker output followed by the new custom prompt
            child.expect('PROMPT_SET_MARKER', timeout=10)
            child.expect(custom_prompt, timeout=10)
            
            if self.debug:
                print(f"[DEBUG] {instance_id}: Custom prompt set successfully")
                print_pexpect_output(child)
            
            # Send the actual command
            if self.debug:
                print(f"[DEBUG] {instance_id}: Executing command: {command}")
            
            child.sendline(command)
            
            # Wait for command completion and custom prompt return
            child.expect(custom_prompt, timeout=timeout)
            
            if self.debug:
                print(f"[DEBUG] {instance_id}: Command completed")
                print_pexpect_output(child)
            
            # Extract output (everything before the final prompt)
            output = child.before
            if output:
                # Clean up the output - remove command echo and extra whitespace
                lines = output.split('\n')
                
                # Remove command echo if present (first non-empty line)
                cleaned_lines = []
                command_echo_removed = False
                
                for line in lines:
                    line = line.strip()
                    if not command_echo_removed and line == command:
                        command_echo_removed = True
                        continue
                    if line:  # Only add non-empty lines
                        cleaned_lines.append(line)
                
                output = '\n'.join(cleaned_lines)
            else:
                output = ""
            
            # Close the session gracefully
            try:
                child.sendline('exit')
                child.expect(pexpect.EOF, timeout=5)
            except:
                try:
                    child.kill(signal.SIGINT)
                except:
                    pass  # Ignore errors during cleanup
            
            return instance_id, output, True
            
        except pexpect.TIMEOUT:
            error_msg = f"Command '{command}' timed out after {timeout} seconds"
            if child and hasattr(child, 'before') and child.before:
                error_msg += f"\nPartial output: {child.before[:500]}..."
            if self.debug:
                error_msg += f"\nSSM Target: {ssm_target}"
            return instance_id, error_msg, False
            
        except pexpect.EOF:
            error_msg = "SSM session ended unexpectedly"
            if child and hasattr(child, 'before') and child.before:
                error_msg += f"\nLast output: {child.before[:500]}..."
            return instance_id, error_msg, False
            
        except Exception as e:
            error_msg = f"Error executing command: {str(e)}"
            if self.debug:
                import traceback
                error_msg += f"\nTraceback: {traceback.format_exc()}"
            return instance_id, error_msg, False
            
        finally:
            # Ensure child process is cleaned up
            if child and child.isalive():
                try:
                    child.terminate(force=True)
                except:
                    pass
    
    def get_nodes_by_instance_group(self, instance_group: str = None) -> List[Dict]:
        """Filter nodes by instance group. If None, return all nodes."""
        if not instance_group:
            return self.nodes
        
        filtered_nodes = [node for node in self.nodes if node.get('NodeGroup', '').lower() == instance_group.lower()]
        return filtered_nodes
    
    def list_instance_groups(self) -> Dict[str, int]:
        """Get a summary of all instance groups and their node counts."""
        groups = {}
        for node in self.nodes:
            group_name = node.get('NodeGroup', 'unknown')
            groups[group_name] = groups.get(group_name, 0) + 1
        return groups
    
    def run_command_on_all_nodes(self, command: str, max_workers: int = 10, instance_group: str = None) -> None:
        """Execute command on all nodes or nodes in a specific instance group concurrently."""
        if not self.nodes:
            print("No nodes available. Please check cluster name.")
            return
        
        # Filter nodes by instance group if specified
        target_nodes = self.get_nodes_by_instance_group(instance_group)
        
        if not target_nodes:
            if instance_group:
                print(f"No nodes found in instance group '{instance_group}'.")
                available_groups = self.list_instance_groups()
                if available_groups:
                    print("Available instance groups:")
                    for group, count in available_groups.items():
                        print(f"  - {group}: {count} nodes")
            else:
                print("No nodes available.")
            return
        
        group_info = f" in instance group '{instance_group}'" if instance_group else ""
        print(f"\nExecuting command on {len(target_nodes)} nodes{group_info}: {command}")
        print("-" * 60)
        
        # Use ThreadPoolExecutor for concurrent execution
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit tasks for target nodes
            future_to_node = {
                executor.submit(self.execute_command_on_node, node, command): node
                for node in target_nodes
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
        
        # Show target format for debugging
        hyperpod_target = self.get_hyperpod_ssm_target(instance_id, instance_group_name)
        print(f"HyperPod SSM target: {hyperpod_target}")
        
        # Test basic connectivity with hostname command for better verification
        # Use a longer timeout for the initial connectivity test
        result_instance_id, output, success = self.execute_command_on_node(node, "echo 'SSM test successful from' $(hostname)", timeout=45)
        
        if success and output:
            print(f"✓ SSM connectivity test passed: {output}")
            return True
        else:
            print(f"✗ SSM connectivity test failed: {output}")
            # Provide additional troubleshooting info for AL2023
            print("\nTroubleshooting tips for AL2023:")
            print("1. Ensure SSM Agent is running: sudo systemctl status amazon-ssm-agent")
            print("2. Check SSM Agent logs: sudo journalctl -u amazon-ssm-agent -f")
            print("3. Verify instance has SSM permissions in IAM role")
            print("4. Check if instance is registered: aws ssm describe-instance-information")
            return False
    
    def select_instance_group(self) -> str:
        """Prompt user to select an instance group or all groups."""
        groups = self.list_instance_groups()
        
        if not groups:
            print("No instance groups found.")
            return None
        
        if len(groups) == 1:
            group_name = list(groups.keys())[0]
            print(f"Only one instance group found: {group_name} ({groups[group_name]} nodes)")
            return group_name
        
        print("\nAvailable instance groups:")
        print("0. All groups (run on all nodes)")
        
        group_list = sorted(groups.items())
        for i, (group_name, count) in enumerate(group_list, 1):
            print(f"{i}. {group_name} ({count} nodes)")
        
        while True:
            try:
                choice = input(f"\nSelect instance group (0-{len(group_list)}): ").strip()
                
                if not choice:
                    continue
                
                choice_num = int(choice)
                
                if choice_num == 0:
                    print("Selected: All groups")
                    return None  # None means all groups
                elif 1 <= choice_num <= len(group_list):
                    selected_group = group_list[choice_num - 1][0]
                    selected_count = group_list[choice_num - 1][1]
                    print(f"Selected: {selected_group} ({selected_count} nodes)")
                    return selected_group
                else:
                    print(f"Invalid choice. Please enter a number between 0 and {len(group_list)}")
                    
            except ValueError:
                print("Invalid input. Please enter a number.")
            except KeyboardInterrupt:
                print("\nExiting...")
                return None
    
    def interactive_mode(self):
        """Run in interactive mode with command input loop."""
        # Select instance group first
        print("Instance Group Selection")
        print("=" * 25)
        selected_group = self.select_instance_group()
        
        if selected_group is False:  # User cancelled
            return
        
        self.current_instance_group = selected_group
        
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
        
        # Show current target
        target_info = "all nodes" if not self.current_instance_group else f"instance group '{self.current_instance_group}'"
        print(f"\nReady to execute commands on {target_info}")
        print("Use 'exit' to quit the tool.\n")
        
        while True:
            try:
                # Simple prompt based on current target
                if self.current_instance_group:
                    prompt = f"[{self.current_instance_group}] Enter command: "
                else:
                    prompt = "[all nodes] Enter command: "
                
                command = input(prompt).strip()
                
                if command.lower() in ['exit', 'quit', 'q']:
                    print("Goodbye!")
                    break
                
                if command.lower() == 'test':
                    # Run a simple test command
                    self.run_command_on_all_nodes("echo 'Hello from $(hostname)'", instance_group=self.current_instance_group)
                    continue
                
                if command.lower() == 'help':
                    print("\nAvailable commands:")
                    print("  test     - Run a simple test command")
                    print("  help     - Show this help message")
                    print("  debug    - Toggle debug mode for troubleshooting")
                    print("  al2023   - Show AL2023 specific troubleshooting tips")
                    print("  exit/quit/q - Exit the tool")
                    print("  Any other command will be executed on the selected target")
                    print(f"\nCurrent target: {target_info}")
                    print()
                    continue
                
                if command.lower() == 'al2023':
                    print("\nAL2023 Troubleshooting Tips:")
                    print("1. SSM Agent status: sudo systemctl status amazon-ssm-agent")
                    print("2. SSM Agent logs: sudo journalctl -u amazon-ssm-agent -f")
                    print("3. Instance registration: aws ssm describe-instance-information")
                    print("4. Test single node: python main.py --test-node <instance-id>")
                    print("5. Enable debug mode: python main.py --debug")
                    print("6. Check IAM role has AmazonSSMManagedInstanceCore policy")
                    print()
                    continue
                
                if command.lower() == 'debug':
                    self.debug = not self.debug
                    print(f"Debug mode {'enabled' if self.debug else 'disabled'}")
                    continue
                
                if not command:
                    continue
                
                # Execute command on selected target
                self.run_command_on_all_nodes(command, instance_group=self.current_instance_group)
                
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
        
        # Display found nodes summary
        print(f"\nFound {len(self.nodes)} nodes in cluster: {cluster_name}")
        
        # Show instance groups summary
        groups = self.list_instance_groups()
        if len(groups) > 1:
            print(f"Instance groups: {', '.join(f'{g}({c})' for g, c in sorted(groups.items()))}")
        
        # List individual nodes if not too many
        if len(self.nodes) <= 20:
            for node in self.nodes:
                node_group = node.get('NodeGroup', 'unknown')
                instance_type = node.get('InstanceType', 'unknown')
                print(f"- {node['InstanceId']} ({node_group}) [{instance_type}]")
        else:
            print(f"({len(self.nodes)} nodes total)")
        
        # Start interactive mode
        self.interactive_mode()


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description='HyperPod Multi-Node Command Runner')
    parser.add_argument('--cluster', '-c', help='HyperPod cluster name')
    parser.add_argument('--debug', '-d', action='store_true', help='Enable debug mode')
    parser.add_argument('--test-node', '-t', help='Test SSM connectivity to specific instance ID')
    parser.add_argument('--command', help='Single command to execute (non-interactive mode)')
    parser.add_argument('--instance-group', '-g', help='Target specific instance group only')
    parser.add_argument('--list-groups', action='store_true', help='List all instance groups and exit')
    
    args = parser.parse_args()
    
    try:
        runner = HyperPodMultiNodeRunner(debug=args.debug)
        
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
                
                # Show instance groups summary
                groups = runner.list_instance_groups()
                if len(groups) > 1:
                    print(f"Instance groups: {', '.join(f'{g}({c})' for g, c in sorted(groups.items()))}")
                
                # List individual nodes if not too many or if debug mode
                if len(runner.nodes) <= 20 or args.debug:
                    for node in runner.nodes:
                        node_group = node.get('NodeGroup', 'unknown')
                        instance_type = node.get('InstanceType', 'unknown')
                        print(f"- {node['InstanceId']} ({node_group}) [{instance_type}]")
                else:
                    print(f"({len(runner.nodes)} nodes total - use --debug to see all)")
                print()
                
                # Handle --list-groups option
                if args.list_groups:
                    print("Instance Groups:")
                    for group, count in sorted(groups.items()):
                        print(f"  - {group}: {count} nodes")
                    return
                
                # Validate instance group if specified
                if args.instance_group:
                    if args.instance_group not in groups:
                        print(f"Error: Instance group '{args.instance_group}' not found.")
                        print("Available groups:")
                        for group, count in sorted(groups.items()):
                            print(f"  - {group}: {count} nodes")
                        sys.exit(1)
                
                if args.command:
                    # Single command mode
                    runner.run_command_on_all_nodes(args.command, instance_group=args.instance_group)
                else:
                    # Interactive mode - set instance group if specified via command line
                    if args.instance_group:
                        runner.current_instance_group = args.instance_group
                        print(f"Using command-line specified instance group: {args.instance_group}")
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