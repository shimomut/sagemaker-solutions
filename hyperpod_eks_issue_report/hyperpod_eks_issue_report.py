#!/usr/bin/env python3
"""
HyperPod EKS Issue Report Collector

Collects diagnostic logs and configurations from multiple HyperPod EKS nodes.
Uses hyperpod_run_on_multi_nodes mechanism to execute collection scripts on nodes.
Downloads collection script from S3 and uploads results back to S3.
"""

import argparse
import boto3
import json
import os
import pexpect
import signal
import sys
import tempfile
import time
from datetime import datetime, timezone
from typing import List, Dict, Optional


class HyperPodEKSIssueReportCollector:
    def __init__(self, cluster_name: str, s3_path: str, debug: bool = False):
        self.cluster_name = cluster_name
        self.debug = debug
        
        # Parse S3 path
        self.s3_bucket, self.s3_prefix = self.parse_s3_path(s3_path)
        
        self.sagemaker_client = boto3.client('sagemaker')
        self.s3_client = boto3.client('s3')
        
        self.cluster_arn = None
        self.cluster_id = None
        self.nodes = []
        
        # Generate unique report ID using UTC time
        self.report_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        self.report_s3_key = f"{self.s3_prefix}/{cluster_name}/{self.report_id}"
    
    def parse_s3_path(self, s3_path: str) -> tuple:
        """Parse S3 path into bucket and prefix.
        
        Accepts formats:
        - s3://bucket-name/prefix/path
        - s3://bucket-name
        - bucket-name/prefix/path
        - bucket-name
        """
        s3_path = s3_path.strip()
        
        # Remove s3:// prefix if present
        if s3_path.startswith('s3://'):
            s3_path = s3_path[5:]
        
        # Split into bucket and prefix
        parts = s3_path.split('/', 1)
        bucket = parts[0]
        prefix = parts[1].rstrip('/') if len(parts) > 1 else 'hyperpod-issue-reports'
        
        return bucket, prefix
    
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
    
    def get_cluster_nodes(self) -> List[Dict]:
        """Get all nodes in the HyperPod cluster."""
        try:
            print(f"Describing cluster: {self.cluster_name}")
            response = self.sagemaker_client.describe_cluster(ClusterName=self.cluster_name)
            
            print(f"Cluster status: {response.get('ClusterStatus', 'Unknown')}")
            
            self.cluster_arn = response.get('ClusterArn')
            self.cluster_id = self.extract_cluster_id_from_arn(self.cluster_arn)
            print(f"Cluster ID: {self.cluster_id}")
            
            if not self.cluster_id:
                print("Warning: Could not extract cluster ID from ARN")
                return []
            
            # List all nodes with pagination
            instance_ids = []
            next_token = None
            page_count = 0
            
            while True:
                page_count += 1
                print(f"Fetching nodes page {page_count}...")
                
                list_params = {'ClusterName': self.cluster_name}
                if next_token:
                    list_params['NextToken'] = next_token
                
                nodes_response = self.sagemaker_client.list_cluster_nodes(**list_params)
                
                current_page_nodes = nodes_response.get('ClusterNodeSummaries', [])
                print(f"Found {len(current_page_nodes)} nodes on page {page_count}")
                
                for node in current_page_nodes:
                    instance_id = node.get('InstanceId')
                    if instance_id:
                        instance_ids.append({
                            'InstanceId': instance_id,
                            'NodeGroup': node.get('InstanceGroupName', 'unknown'),
                            'InstanceType': node.get('InstanceType', 'unknown'),
                            'InstanceStatus': node.get('InstanceStatus', {}).get('Status', 'unknown')
                        })
                
                next_token = nodes_response.get('NextToken')
                if not next_token:
                    break
            
            print(f"Total instances found: {len(instance_ids)}")
            return instance_ids
            
        except Exception as e:
            print(f"Error getting cluster nodes: {e}")
            return []
    
    def generate_collector_script(self, commands: List[str], run_eks_log_collector: bool = False) -> str:
        """Generate the bash script that will run on each node.
        Instance group and ID are passed as environment variables."""
        script_lines = [
            "#!/bin/bash",
            "# HyperPod EKS Issue Report Collector Script",
            "# Auto-generated script to collect diagnostic information",
            "# Expects INSTANCE_GROUP and INSTANCE_ID environment variables",
            "",
            "# Note: We don't use 'set -e' because some commands (like grep) may return non-zero",
            "# exit codes even when they succeed (e.g., grep returns 1 when no matches found)",
            "",
            "# Validate required environment variables",
            "if [ -z \"${INSTANCE_GROUP}\" ] || [ -z \"${INSTANCE_ID}\" ]; then",
            "    echo \"Error: INSTANCE_GROUP and INSTANCE_ID environment variables are required\"",
            "    exit 1",
            "fi",
            "",
            "# Instance identification",
            "TIMESTAMP=$(date -u +%Y%m%d_%H%M%S)",
            "OUTPUT_DIR=\"/tmp/hyperpod_report_${INSTANCE_GROUP}_${INSTANCE_ID}_${TIMESTAMP}\"",
            "",
            "echo \"Creating output directory: ${OUTPUT_DIR}\"",
            "mkdir -p \"${OUTPUT_DIR}\"",
            "if [ $? -ne 0 ]; then",
            "    echo \"ERROR: Failed to create output directory\"",
            "    exit 1",
            "fi",
            "",
            "# Collect system information",
            "echo \"Collecting system information...\"",
            "echo \"${INSTANCE_GROUP}\" > \"${OUTPUT_DIR}/instance_group.txt\"",
            "echo \"${INSTANCE_ID}\" > \"${OUTPUT_DIR}/instance_id.txt\"",
            "hostname > \"${OUTPUT_DIR}/hostname.txt\"",
            "date -u > \"${OUTPUT_DIR}/timestamp.txt\"",
            "",
            "# Collect HyperPod resource config if available",
            "if [ -f /opt/ml/config/resource_config.json ]; then",
            "    echo \"Collecting HyperPod resource config...\"",
            "    cp /opt/ml/config/resource_config.json \"${OUTPUT_DIR}/resource_config.json\" 2>/dev/null || echo \"Could not copy resource_config.json\"",
            "fi",
            "",
            "# Collect cluster logs if available",
            "if [ -d /var/log/aws/clusters ]; then",
            "    echo \"Collecting cluster logs...\"",
            "    mkdir -p \"${OUTPUT_DIR}/cluster_logs\"",
            "    cp -r /var/log/aws/clusters/* \"${OUTPUT_DIR}/cluster_logs/\" 2>/dev/null || echo \"Could not copy cluster logs\"",
            "fi",
            "",
            "# Collect systemd service status",
            "echo \"Collecting systemd service status...\"",
            "systemctl list-units --type=service --all --no-pager > \"${OUTPUT_DIR}/systemd_services.txt\" 2>&1 || echo \"Could not collect systemd services\"",
            "",
            "# Collect disk usage",
            "echo \"Collecting disk usage...\"",
            "df > \"${OUTPUT_DIR}/disk_usage.txt\" 2>&1 || echo \"Could not collect disk usage\"",
            "",
            "# Collect nvidia-smi output",
            "echo \"Collecting nvidia-smi output...\"",
            "nvidia-smi > \"${OUTPUT_DIR}/nvidia_smi.txt\" 2>&1 || echo \"nvidia-smi not available or failed\"",
            "",
        ]
        
        # Add EKS log collector if requested
        if run_eks_log_collector:
            script_lines.extend([
                "# Run EKS log collector script",
                "echo \"Running EKS log collector...\"",
                "EKS_LOG_COLLECTOR_URL=\"https://raw.githubusercontent.com/awslabs/amazon-eks-ami/main/log-collector-script/linux/eks-log-collector.sh\"",
                "curl -o /tmp/eks-log-collector.sh \"${EKS_LOG_COLLECTOR_URL}\"",
                "chmod +x /tmp/eks-log-collector.sh",
                "",
                "# Run the collector and capture its output",
                "/tmp/eks-log-collector.sh > \"${OUTPUT_DIR}/eks-log-collector-output.txt\" 2>&1 || echo \"EKS log collector completed with warnings\"",
                "",
                "# Find the generated tarball (it's created in /var/log/)",
                "EKS_TARBALL=$(ls -t /var/log/eks_*.tar.gz 2>/dev/null | head -1)",
                "if [ -n \"${EKS_TARBALL}\" ]; then",
                "    echo \"Found EKS logs at ${EKS_TARBALL}\"",
                "    echo \"Extracting EKS logs from ${EKS_TARBALL}\"",
                "    mkdir -p \"${OUTPUT_DIR}/eks-logs\"",
                "    tar -xzf \"${EKS_TARBALL}\" -C \"${OUTPUT_DIR}/eks-logs\" 2>/dev/null || echo \"Extracted EKS logs\"",
                "    rm -f \"${EKS_TARBALL}\"",
                "else",
                "    echo \"ERROR: No EKS log tarball found in /var/log/\" | tee -a \"${OUTPUT_DIR}/eks-log-collector-output.txt\"",
                "    echo \"EKS log collector may have failed. Check eks-log-collector-output.txt for details.\" | tee -a \"${OUTPUT_DIR}/eks-log-collector-output.txt\"",
                "    rm -f /tmp/eks-log-collector.sh",
                "    exit 1",
                "fi",
                "",
                "# Clean up the collector script",
                "rm -f /tmp/eks-log-collector.sh",
                "",
            ])
        
        # Add each command to the script
        for i, cmd in enumerate(commands, 1):
            # Sanitize command for filename - replace problematic characters
            safe_name = cmd.replace(' ', '_').replace('/', '_').replace('|', '_').replace('>', '_').replace('<', '_').replace('&', '_').replace(';', '_').replace('(', '_').replace(')', '_').replace('$', '_').replace('`', '_').replace('"', '_').replace("'", '_')[:50]
            output_file = f"command_{i:02d}_{safe_name}.txt"
            
            # Use regular string (not f-string) to avoid any escaping issues with bash variables
            cmd_line = f"{cmd} > \"${{OUTPUT_DIR}}/{output_file}\" 2>&1 || echo \"Command failed with exit code $?\" >> \"${{OUTPUT_DIR}}/{output_file}\""
            
            script_lines.extend([
                f"# Command {i}: {cmd}",
                f"echo \"Running: {cmd}\"",
                cmd_line,
                "",
            ])
        
        # Add S3 upload logic with new filename format
        script_lines.extend([
            "# Upload results to S3",
            f"S3_BUCKET=\"{self.s3_bucket}\"",
            f"S3_PREFIX=\"{self.report_s3_key}/results\"",
            "",
            "echo \"Creating tarball...\"",
            "TARBALL=\"/tmp/${INSTANCE_GROUP}_${INSTANCE_ID}.tar.gz\"",
            "tar -czf \"${TARBALL}\" -C /tmp \"$(basename ${OUTPUT_DIR})\"",
            "if [ $? -ne 0 ]; then",
            "    echo \"ERROR: Failed to create tarball\"",
            "    exit 1",
            "fi",
            "",
            "echo \"Uploading to S3...\"",
            "aws s3 cp \"${TARBALL}\" \"s3://${S3_BUCKET}/${S3_PREFIX}/$(basename ${TARBALL})\"",
            "",
            "if [ $? -eq 0 ]; then",
            "    echo \"Successfully uploaded report to s3://${S3_BUCKET}/${S3_PREFIX}/$(basename ${TARBALL})\"",
            "    rm -rf \"${OUTPUT_DIR}\" \"${TARBALL}\"",
            "    exit 0",
            "else",
            "    echo \"ERROR: Failed to upload to S3\"",
            "    exit 1",
            "fi",
            "",
            "echo \"Report collection completed for ${INSTANCE_GROUP}/${INSTANCE_ID}\"",
        ])
        
        return '\n'.join(script_lines)
    
    def get_hyperpod_ssm_target(self, instance_id: str, instance_group_name: str) -> str:
        """Construct the HyperPod SSM target format."""
        if not self.cluster_id:
            raise ValueError("Cluster ID is required for HyperPod SSM targets")
        return f"sagemaker-cluster:{self.cluster_id}_{instance_group_name}-{instance_id}"
    
    def execute_collection_on_node(self, node: Dict, commands: List[str], script_s3_uri: str) -> Dict:
        """Execute the collection script on a single node via SSM using pexpect."""
        instance_id = node['InstanceId']
        instance_group = node.get('NodeGroup', 'unknown')
        
        try:
            ssm_target = self.get_hyperpod_ssm_target(instance_id, instance_group)
        except ValueError as e:
            return {
                'InstanceId': instance_id,
                'NodeGroup': instance_group,
                'Success': False,
                'Error': str(e)
            }
        
        # Build the command to download and execute the script with environment variables
        commands_to_run = [
            f"aws s3 cp {script_s3_uri} /tmp/collector_script.sh",
            "chmod +x /tmp/collector_script.sh",
            f"INSTANCE_GROUP={instance_group} INSTANCE_ID={instance_id} /tmp/collector_script.sh"
        ]
        
        full_command = " && ".join(commands_to_run)
        
        print(f"Executing collection on {instance_id} ({instance_group})...")
        
        child = None
        custom_prompt = "PEXPECT_READY# "
        
        try:
            ssm_command = f"aws ssm start-session --target {ssm_target}"
            
            if self.debug:
                print(f"[DEBUG] {instance_id}: SSM command: {ssm_command}")
                print(f"[DEBUG] {instance_id}: Full command: {full_command}")
            
            # Use pexpect to handle the interactive session
            child = pexpect.spawn(ssm_command, timeout=300, encoding='utf-8')
            child.logfile_read = None
            
            # Wait for initial prompt
            initial_prompt_patterns = [
                r'[\$#]\s+',            # Standard shell prompt
                r'sh-\d+\.\d+[\$#]\s*', # sh prompt
                pexpect.TIMEOUT
            ]
            
            prompt_index = child.expect(initial_prompt_patterns, timeout=30)
            
            if prompt_index == len(initial_prompt_patterns) - 1:  # TIMEOUT
                child.sendline('')
                try:
                    child.expect(initial_prompt_patterns[:-1], timeout=10)
                except pexpect.TIMEOUT:
                    return {
                        'InstanceId': instance_id,
                        'NodeGroup': instance_group,
                        'Success': False,
                        'Error': 'Failed to establish shell session - no prompt detected'
                    }
            
            # Set custom prompt
            child.sendline(f'export PS1="{custom_prompt}"')
            child.sendline('echo "PROMPT_SET_MARKER"')
            child.expect('PROMPT_SET_MARKER', timeout=10)
            child.expect(custom_prompt, timeout=10)
            
            if self.debug:
                print(f"[DEBUG] {instance_id}: Custom prompt set")
            
            # Execute the command and capture exit code immediately
            child.sendline(f'{full_command}; EXIT_CODE=$?; echo "EXIT_CODE:$EXIT_CODE"')
            
            # Wait for command completion (up to 5 minutes)
            child.expect(custom_prompt, timeout=300)
            
            # Extract output
            output = child.before
            exit_code = 1  # Default to failure
            
            if output:
                lines = output.split('\n')
                cleaned_lines = []
                command_echo_removed = False
                
                for line in lines:
                    line_stripped = line.strip()
                    
                    # Remove command echo
                    if not command_echo_removed and full_command in line:
                        command_echo_removed = True
                        continue
                    
                    # Extract exit code
                    if line_stripped.startswith('EXIT_CODE:'):
                        try:
                            exit_code = int(line_stripped.split(':')[1].strip())
                        except:
                            pass
                        continue
                    
                    if line_stripped:
                        cleaned_lines.append(line_stripped)
                
                output = '\n'.join(cleaned_lines)
            else:
                output = ""
            
            # Close session
            try:
                child.sendline('exit')
                child.expect(pexpect.EOF, timeout=5)
            except:
                try:
                    child.kill(signal.SIGINT)
                except:
                    pass
            
            # Determine success based solely on exit code
            if exit_code == 0:
                return {
                    'InstanceId': instance_id,
                    'NodeGroup': instance_group,
                    'Success': True,
                    'Output': output
                }
            else:
                # Show last 15 lines of output which usually contain the error
                output_lines = output.split('\n')
                error_context = '\n'.join(output_lines[-15:]) if len(output_lines) > 15 else output
                
                return {
                    'InstanceId': instance_id,
                    'NodeGroup': instance_group,
                    'Success': False,
                    'Error': f"Script execution failed (exit code: {exit_code})\n{error_context}",
                    'Output': output
                }
            
        except pexpect.TIMEOUT:
            error_msg = f"Command timed out after 5 minutes"
            if child and hasattr(child, 'before') and child.before:
                error_msg += f"\nPartial output: {child.before[:500]}..."
            return {
                'InstanceId': instance_id,
                'NodeGroup': instance_group,
                'Success': False,
                'Error': error_msg
            }
            
        except pexpect.EOF:
            error_msg = "SSM session ended unexpectedly"
            if child and hasattr(child, 'before') and child.before:
                error_msg += f"\nLast output: {child.before[:500]}..."
            return {
                'InstanceId': instance_id,
                'NodeGroup': instance_group,
                'Success': False,
                'Error': error_msg
            }
            
        except Exception as e:
            error_msg = f"Error executing command: {str(e)}"
            if self.debug:
                import traceback
                error_msg += f"\nTraceback: {traceback.format_exc()}"
            return {
                'InstanceId': instance_id,
                'NodeGroup': instance_group,
                'Success': False,
                'Error': error_msg
            }
            
        finally:
            if child and child.isalive():
                try:
                    child.terminate(force=True)
                except:
                    pass
    
    def collect_reports(self, commands: List[str], instance_group: Optional[str] = None, instance_ids: Optional[List[str]] = None, max_workers: int = 10, run_eks_log_collector: bool = False):
        """Collect reports from all nodes, specific instance group, or specific instance IDs."""
        # Get cluster nodes
        self.nodes = self.get_cluster_nodes()
        
        if not self.nodes:
            print("No nodes found in cluster")
            return
        
        # Filter by specific instance IDs if specified
        if instance_ids:
            self.nodes = [n for n in self.nodes if n.get('InstanceId') in instance_ids]
            if not self.nodes:
                print(f"No nodes found with specified instance IDs: {', '.join(instance_ids)}")
                return
            # Show which requested IDs were not found
            found_ids = {n.get('InstanceId') for n in self.nodes}
            missing_ids = set(instance_ids) - found_ids
            if missing_ids:
                print(f"Warning: Instance IDs not found in cluster: {', '.join(missing_ids)}")
        # Filter by instance group if specified (only if instance_ids not specified)
        elif instance_group:
            self.nodes = [n for n in self.nodes if n.get('NodeGroup', '').lower() == instance_group.lower()]
            if not self.nodes:
                print(f"No nodes found in instance group: {instance_group}")
                return
        
        print(f"\nCollecting reports from {len(self.nodes)} nodes")
        print(f"Report ID: {self.report_id}")
        print(f"S3 Location: s3://{self.s3_bucket}/{self.report_s3_key}/")
        print(f"Default collections: nvidia-smi, EKS log collector")
        if len(commands) > 1:
            print(f"Additional commands: {', '.join(commands[1:])}")
        print("-" * 60)
        
        # Generate and upload the collector script once
        script_content = self.generate_collector_script(commands, run_eks_log_collector)
        script_key = f"{self.report_s3_key}/collector_script.sh"
        
        try:
            self.s3_client.put_object(
                Bucket=self.s3_bucket,
                Key=script_key,
                Body=script_content.encode('utf-8'),
                ContentType='text/x-shellscript'
            )
            script_s3_uri = f"s3://{self.s3_bucket}/{script_key}"
            print(f"Uploaded collector script to: {script_s3_uri}")
        except Exception as e:
            print(f"Error uploading collector script: {e}")
            return
        
        # Execute collection on all nodes using ThreadPoolExecutor
        from concurrent.futures import ThreadPoolExecutor, as_completed
        
        results = []
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_node = {
                executor.submit(self.execute_collection_on_node, node, commands, script_s3_uri): node
                for node in self.nodes
            }
            
            for future in as_completed(future_to_node):
                node = future_to_node[future]
                try:
                    result = future.result()
                    results.append(result)
                    
                    status = "✓" if result['Success'] else "✗"
                    print(f"[{status}] {result['InstanceId']} ({result['NodeGroup']})")
                    
                    if not result['Success']:
                        error_msg = result.get('Error', 'Unknown error')
                        # Print error details with indentation for readability
                        for line in error_msg.split('\n'):
                            if line.strip():
                                print(f"    {line}")
                    
                except Exception as e:
                    print(f"[✗] {node['InstanceId']}: Exception: {e}")
                    results.append({
                        'InstanceId': node['InstanceId'],
                        'NodeGroup': node.get('NodeGroup', 'unknown'),
                        'Success': False,
                        'Error': str(e)
                    })
        
        # Save summary
        self.save_summary(results)
        
        print("-" * 60)
        print(f"\nReport collection completed!")
        print(f"Results uploaded to: s3://{self.s3_bucket}/{self.report_s3_key}/results/")
        print(f"Summary: s3://{self.s3_bucket}/{self.report_s3_key}/summary.json")
        
        # Print statistics
        successful = sum(1 for r in results if r['Success'])
        failed = len(results) - successful
        print(f"\nStatistics:")
        print(f"  Total nodes: {len(results)}")
        print(f"  Successful: {successful}")
        print(f"  Failed: {failed}")
    
    def save_summary(self, results: List[Dict]):
        """Save collection summary to S3."""
        summary = {
            'cluster_name': self.cluster_name,
            'cluster_id': self.cluster_id,
            'report_id': self.report_id,
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'total_nodes': len(results),
            'successful': sum(1 for r in results if r['Success']),
            'failed': sum(1 for r in results if not r['Success']),
            'results': results
        }
        
        summary_key = f"{self.report_s3_key}/summary.json"
        
        try:
            self.s3_client.put_object(
                Bucket=self.s3_bucket,
                Key=summary_key,
                Body=json.dumps(summary, indent=2).encode('utf-8'),
                ContentType='application/json'
            )
            print(f"Summary saved to: s3://{self.s3_bucket}/{summary_key}")
        except Exception as e:
            print(f"Error saving summary: {e}")


def main():
    parser = argparse.ArgumentParser(
        description='HyperPod EKS Issue Report Collector',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic usage - collects nvidia-smi and EKS logs from all nodes
  python hyperpod_eks_issue_report.py --cluster my-cluster --s3-path s3://my-bucket
  
  # With custom prefix
  python hyperpod_eks_issue_report.py --cluster my-cluster --s3-path s3://my-bucket/diagnostics
  
  # Add additional commands
  python hyperpod_eks_issue_report.py --cluster my-cluster --s3-path s3://my-bucket \\
    --command "df -h" \\
    --command "free -h"
  
  # Target specific instance group
  python hyperpod_eks_issue_report.py --cluster my-cluster --s3-path s3://my-bucket \\
    --instance-group worker-group
  
  # Target specific instance IDs
  python hyperpod_eks_issue_report.py --cluster my-cluster --s3-path s3://my-bucket \\
    --nodes i-abc123 i-def456
  
  # Use custom S3 prefix
  python hyperpod_eks_issue_report.py --cluster my-cluster --s3-path s3://my-bucket/diagnostics
        """
    )
    
    parser.add_argument('--cluster', '-c', required=True, help='HyperPod cluster name')
    parser.add_argument('--s3-path', '-s', required=True, help='S3 path for storing reports (e.g., s3://bucket-name/prefix or s3://bucket-name)')
    parser.add_argument('--command', '-cmd', action='append', help='Additional command to execute on nodes (can be specified multiple times)')
    parser.add_argument('--instance-group', '-g', help='Target specific instance group only')
    parser.add_argument('--nodes', '-n', nargs='+', help='Target specific instance IDs (e.g., --nodes i-abc123 i-def456)')
    parser.add_argument('--max-workers', '-w', type=int, default=10, help='Maximum concurrent workers (default: 10)')
    parser.add_argument('--debug', '-d', action='store_true', help='Enable debug mode')
    
    args = parser.parse_args()
    
    # Validate mutually exclusive options
    if args.instance_group and args.nodes:
        print("Error: --instance-group and --nodes cannot be used together")
        sys.exit(1)
    
    try:
        collector = HyperPodEKSIssueReportCollector(
            cluster_name=args.cluster,
            s3_path=args.s3_path,
            debug=args.debug
        )
        
        # User-specified commands (nvidia-smi is now collected by default, not as a command)
        commands = []
        
        # Add any user-specified commands
        if args.command:
            commands.extend(args.command)
        
        collector.collect_reports(
            commands=commands,
            instance_group=args.instance_group,
            instance_ids=args.nodes,
            max_workers=args.max_workers,
            run_eks_log_collector=True  # Always run EKS log collector
        )
        
    except KeyboardInterrupt:
        print("\n\nInterrupted by user. Exiting...")
        sys.exit(1)
    except Exception as e:
        print(f"\nError: {e}")
        if args.debug:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
