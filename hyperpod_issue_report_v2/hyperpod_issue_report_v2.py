#!/usr/bin/env python3
"""
HyperPod Issue Report Collector

Collects diagnostic logs and configurations from multiple HyperPod nodes.
Supports both HyperPod EKS and HyperPod Slurm clusters.
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


class HyperPodIssueReportCollector:
    def __init__(self, cluster_name: str, s3_path: str, debug: bool = False):
        self.cluster_name = cluster_name
        self.debug = debug
        
        # Parse S3 path
        self.s3_bucket, self.s3_prefix = self.parse_s3_path(s3_path)
        
        self.sagemaker_client = boto3.client('sagemaker')
        self.s3_client = boto3.client('s3')
        self.eks_client = boto3.client('eks')
        
        self.cluster_arn = None
        self.cluster_id = None
        self.cluster_type = None  # 'eks' or 'slurm'
        self.eks_cluster_arn = None
        self.eks_cluster_name = None
        self.nodes = []
        
        # Generate unique report ID using UTC time
        self.report_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        self.report_s3_key = f"{self.s3_prefix}/{cluster_name}/{self.report_id}"
    
    def parse_s3_path(self, s3_path: str) -> tuple:
        """Parse S3 path into bucket and prefix.
        
        Accepts formats:
        - s3://bucket-name/prefix/path
        - s3://bucket-name
        """
        s3_path = s3_path.strip()
        
        # Require s3:// prefix
        if not s3_path.startswith('s3://'):
            raise ValueError(
                f"S3 path must start with 's3://' prefix.\n"
                f"Received: {s3_path}\n"
                f"Expected format: s3://bucket-name or s3://bucket-name/custom-prefix"
            )
        
        # Remove s3:// prefix
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
        """Get all nodes in the HyperPod cluster and detect cluster type."""
        try:
            print(f"Describing cluster: {self.cluster_name}")
            response = self.sagemaker_client.describe_cluster(ClusterName=self.cluster_name)
            
            print(f"Cluster status: {response.get('ClusterStatus', 'Unknown')}")
            
            # Detect cluster type from Orchestrator field
            orchestrator = response.get('Orchestrator', {})
            
            if 'Eks' in orchestrator:
                self.cluster_type = 'eks'
                print(f"Detected cluster type: EKS")
                # Extract EKS cluster ARN
                eks_config = orchestrator.get('Eks', {})
                self.eks_cluster_arn = eks_config.get('ClusterArn')
                if self.eks_cluster_arn:
                    # Extract cluster name from ARN: arn:aws:eks:region:account:cluster/cluster-name
                    self.eks_cluster_name = self.eks_cluster_arn.split('/')[-1]
                    print(f"EKS Cluster ARN: {self.eks_cluster_arn}")
                    print(f"EKS Cluster Name: {self.eks_cluster_name}")
                else:
                    print("Warning: Could not extract EKS cluster ARN from orchestrator config")
            elif 'Slurm' in orchestrator:
                self.cluster_type = 'slurm'
                print(f"Detected cluster type: Slurm")
            else:
                # If Orchestrator field is missing or doesn't contain Eks/Slurm, assume Slurm
                self.cluster_type = 'slurm'
                print(f"Orchestrator field not found or unrecognized, assuming cluster type: Slurm")
            
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
    
    def generate_collector_script(self, commands: List[str]) -> str:
        """Generate the bash script that will run on each node.
        Instance group and ID are passed as environment variables.
        Script content varies based on cluster type (EKS vs Slurm)."""
        script_lines = [
            "#!/bin/bash",
            "# HyperPod Issue Report Collector Script",
            "# Auto-generated script to collect diagnostic information",
            "# Expects INSTANCE_GROUP, INSTANCE_ID, and CLUSTER_TYPE environment variables",
            "",
            "# Note: We don't use 'set -e' because some commands (like grep) may return non-zero",
            "# exit codes even when they succeed (e.g., grep returns 1 when no matches found)",
            "",
            "# Validate required environment variables",
            "if [ -z \"${INSTANCE_GROUP}\" ] || [ -z \"${INSTANCE_ID}\" ] || [ -z \"${CLUSTER_TYPE}\" ]; then",
            "    echo \"Error: INSTANCE_GROUP, INSTANCE_ID, and CLUSTER_TYPE environment variables are required\"",
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
            "echo \"${CLUSTER_TYPE}\" > \"${OUTPUT_DIR}/cluster_type.txt\"",
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
        
        # Add cluster-type specific collections
        if self.cluster_type == 'eks':
            script_lines.extend([
                "# EKS-specific collections",
                "echo \"Collecting containerd service status...\"",
                "systemctl status containerd > \"${OUTPUT_DIR}/containerd_status.txt\" 2>&1 || echo \"containerd service not found or not running\"",
                "",
                "echo \"Collecting kubelet service status...\"",
                "systemctl status kubelet > \"${OUTPUT_DIR}/kubelet_status.txt\" 2>&1 || echo \"kubelet service not found or not running\"",
                "",
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
        elif self.cluster_type == 'slurm':
            script_lines.extend([
                "# Slurm-specific collections",
                "echo \"Collecting Slurm information...\"",
                "",
                "# Slurm info commands",
                "sinfo > \"${OUTPUT_DIR}/sinfo.txt\" 2>&1 || echo \"sinfo not available\"",
                "sinfo -R > \"${OUTPUT_DIR}/sinfo_R.txt\" 2>&1 || echo \"sinfo -R not available\"",
                "",
                "# Slurm service status",
                "systemctl status slurmctld > \"${OUTPUT_DIR}/slurmctld_status.txt\" 2>&1 || echo \"slurmctld not running on this node\"",
                "systemctl status slurmd > \"${OUTPUT_DIR}/slurmd_status.txt\" 2>&1 || echo \"slurmd not running on this node\"",
                "",
                "# Slurm configuration",
                "if [ -d /opt/slurm/etc ]; then",
                "    echo \"Collecting Slurm configuration...\"",
                "    mkdir -p \"${OUTPUT_DIR}/opt_slurm_etc\"",
                "    cp -r /opt/slurm/etc/* \"${OUTPUT_DIR}/opt_slurm_etc/\" 2>/dev/null || echo \"Could not copy Slurm config\"",
                "fi",
                "",
                "# NVIDIA bug report",
                "echo \"Running nvidia-bug-report.sh...\"",
                "nvidia-bug-report.sh --output-file \"${OUTPUT_DIR}/nvidia-bug-report.log.gz\" 2>&1 || echo \"nvidia-bug-report.sh not available or failed\"",
                "",
                "# System logs",
                "echo \"Collecting system logs...\"",
                "cp /var/log/syslog \"${OUTPUT_DIR}/syslog\" 2>/dev/null || echo \"Could not copy syslog\"",
                "cp /var/log/kern.log \"${OUTPUT_DIR}/kern.log\" 2>/dev/null || echo \"Could not copy kern.log\"",
                "dmesg -T > \"${OUTPUT_DIR}/dmesg_T.txt\" 2>&1 || echo \"Could not run dmesg -T\"",
                "",
                "# Slurm logs",
                "if [ -d /var/log/slurm ]; then",
                "    echo \"Collecting Slurm logs...\"",
                "    mkdir -p \"${OUTPUT_DIR}/var_log_slurm\"",
                "    cp -r /var/log/slurm/* \"${OUTPUT_DIR}/var_log_slurm/\" 2>/dev/null || echo \"Could not copy Slurm logs\"",
                "fi",
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
            f"S3_PREFIX=\"{self.report_s3_key}/instances\"",
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
            f"INSTANCE_GROUP={instance_group} INSTANCE_ID={instance_id} CLUSTER_TYPE={self.cluster_type} /tmp/collector_script.sh"
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
    
    def collect_reports(self, commands: List[str], instance_groups: Optional[List[str]] = None, instance_ids: Optional[List[str]] = None, max_workers: int = 10):
        """Collect reports from all nodes, specific instance groups, or specific instance IDs."""
        # Get cluster nodes
        self.nodes = self.get_cluster_nodes()
        
        if not self.nodes:
            print("No nodes found in cluster")
            return
        
        # Collect kubectl information first (for EKS clusters)
        if self.cluster_type == 'eks':
            self.collect_kubectl_node_info()
        
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
        # Filter by instance groups if specified (only if instance_ids not specified)
        elif instance_groups:
            # Convert instance groups to lowercase for case-insensitive matching
            instance_groups_lower = [ig.lower() for ig in instance_groups]
            self.nodes = [n for n in self.nodes if n.get('NodeGroup', '').lower() in instance_groups_lower]
            if not self.nodes:
                print(f"No nodes found in instance groups: {', '.join(instance_groups)}")
                return
            print(f"Filtering to instance groups: {', '.join(instance_groups)}")
        
        print(f"\nCollecting reports from {len(self.nodes)} nodes")
        print(f"Cluster type: {self.cluster_type.upper()}")
        print(f"Report ID: {self.report_id}")
        print(f"S3 Location: s3://{self.s3_bucket}/{self.report_s3_key}/")
        
        # Show what will be collected based on cluster type
        if self.cluster_type == 'eks':
            print(f"Default collections: nvidia-smi, containerd status, kubelet status, EKS log collector, resource config, cluster logs, systemd services, disk usage")
        elif self.cluster_type == 'slurm':
            print(f"Default collections: nvidia-smi, nvidia-bug-report, sinfo, Slurm services, Slurm config, Slurm logs, system logs")
        
        if commands:
            print(f"Additional commands: {', '.join(commands)}")
        print("-" * 60)
        
        # Generate and upload the collector script once
        script_content = self.generate_collector_script(commands)
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
        print(f"Instance reports uploaded to: s3://{self.s3_bucket}/{self.report_s3_key}/instances/")
        print(f"Summary: s3://{self.s3_bucket}/{self.report_s3_key}/summary.json")
        
        # Print statistics
        successful = sum(1 for r in results if r['Success'])
        failed = len(results) - successful
        print(f"\nStatistics:")
        print(f"  Total nodes: {len(results)}")
        print(f"  Successful: {successful}")
        print(f"  Failed: {failed}")
        
        # Offer to download results
        self.offer_download_results()
    
    def offer_download_results(self):
        """Ask user if they want to download results from S3."""
        print("\n" + "=" * 60)
        print("Download Results")
        print("=" * 60)
        
        try:
            response = input("\nWould you like to download all results from S3 to the current directory? (y/n): ").strip().lower()
            
            if response in ['y', 'yes']:
                download_dir = self.download_results_from_s3()
                
                if download_dir:
                    # Ask about creating zip archive
                    response = input("\nWould you like to create a zip archive of the downloaded results? (y/n): ").strip().lower()
                    
                    if response in ['y', 'yes']:
                        self.create_zip_archive(download_dir)
            else:
                print("\nSkipping download. You can download manually using:")
                print(f"  aws s3 sync s3://{self.s3_bucket}/{self.report_s3_key}/ ./{self.cluster_name}_{self.report_id}/")
                
        except KeyboardInterrupt:
            print("\n\nDownload cancelled by user.")
        except Exception as e:
            print(f"\nError during download prompt: {e}")
    
    def download_results_from_s3(self) -> Optional[str]:
        """Download all results from S3 to local directory.
        
        Returns:
            str: Path to download directory if successful, None otherwise
        """
        # Create download directory
        download_dir = f"{self.cluster_name}_{self.report_id}"
        
        print(f"\nDownloading results to: ./{download_dir}/")
        print(f"Source: s3://{self.s3_bucket}/{self.report_s3_key}/")
        
        try:
            # List all objects in the S3 prefix
            paginator = self.s3_client.get_paginator('list_objects_v2')
            pages = paginator.paginate(Bucket=self.s3_bucket, Prefix=self.report_s3_key)
            
            files_to_download = []
            for page in pages:
                if 'Contents' in page:
                    for obj in page['Contents']:
                        key = obj['Key']
                        # Skip the prefix itself (directory marker)
                        if key != self.report_s3_key and key != f"{self.report_s3_key}/":
                            files_to_download.append(key)
            
            if not files_to_download:
                print("No files found to download.")
                return None
            
            print(f"Found {len(files_to_download)} files to download...")
            
            # Download each file
            downloaded = 0
            failed = 0
            
            for key in files_to_download:
                # Calculate relative path (remove the report_s3_key prefix)
                relative_path = key[len(self.report_s3_key):].lstrip('/')
                local_path = os.path.join(download_dir, relative_path)
                
                # Create parent directory if needed
                local_dir = os.path.dirname(local_path)
                if local_dir:
                    os.makedirs(local_dir, exist_ok=True)
                
                try:
                    # Download file
                    self.s3_client.download_file(self.s3_bucket, key, local_path)
                    downloaded += 1
                    
                    # Show progress for every 5 files or last file
                    if downloaded % 5 == 0 or downloaded == len(files_to_download):
                        print(f"  Downloaded {downloaded}/{len(files_to_download)} files...")
                        
                except Exception as e:
                    print(f"  Failed to download {relative_path}: {e}")
                    failed += 1
            
            print(f"\n✓ Download completed!")
            print(f"  Downloaded: {downloaded} files")
            if failed > 0:
                print(f"  Failed: {failed} files")
            print(f"  Location: ./{download_dir}/")
            
            return download_dir
            
        except Exception as e:
            print(f"\nError downloading results: {e}")
            if self.debug:
                import traceback
                traceback.print_exc()
            return None
    
    def create_zip_archive(self, directory: str):
        """Create a zip archive of the downloaded results.
        
        Args:
            directory: Path to directory to archive
        """
        import zipfile
        
        zip_filename = f"{directory}.zip"
        
        print(f"\nCreating zip archive: {zip_filename}")
        
        try:
            with zipfile.ZipFile(zip_filename, 'w', zipfile.ZIP_DEFLATED) as zipf:
                # Walk through directory
                file_count = 0
                for root, dirs, files in os.walk(directory):
                    for file in files:
                        file_path = os.path.join(root, file)
                        # Calculate archive name (relative to directory)
                        arcname = os.path.relpath(file_path, os.path.dirname(directory))
                        zipf.write(file_path, arcname)
                        file_count += 1
                        
                        # Show progress
                        if file_count % 5 == 0:
                            print(f"  Archived {file_count} files...")
            
            # Get zip file size
            zip_size = os.path.getsize(zip_filename)
            zip_size_mb = zip_size / (1024 * 1024)
            
            print(f"\n✓ Zip archive created!")
            print(f"  File: {zip_filename}")
            print(f"  Size: {zip_size_mb:.2f} MB")
            print(f"  Files: {file_count}")
            
            # Ask if user wants to delete the uncompressed directory
            response = input(f"\nWould you like to delete the uncompressed directory '{directory}'? (y/n): ").strip().lower()
            
            if response in ['y', 'yes']:
                import shutil
                shutil.rmtree(directory)
                print(f"✓ Deleted directory: {directory}")
            else:
                print(f"Keeping directory: {directory}")
                
        except Exception as e:
            print(f"\nError creating zip archive: {e}")
            if self.debug:
                import traceback
                traceback.print_exc()
    
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
    
    def verify_kubectl_config(self) -> bool:
        """Verify kubectl is configured for the EKS cluster."""
        if not self.eks_cluster_name:
            print("Warning: EKS cluster name not available, skipping kubectl verification")
            return False
        
        try:
            import subprocess
            
            # Check if kubectl is installed
            result = subprocess.run(['kubectl', 'version', '--client'], 
                                  capture_output=True, text=True, timeout=10)
            if result.returncode != 0:
                print("\n" + "!" * 60)
                print("ERROR: kubectl is not installed or not in PATH")
                print("!" * 60)
                return False
            
            # Extract just the version line
            version_line = result.stdout.strip().split('\n')[0] if result.stdout else "kubectl installed"
            print(f"kubectl version: {version_line}")
            
            # Check current context
            result = subprocess.run(['kubectl', 'config', 'current-context'], 
                                  capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                current_context = result.stdout.strip()
                print(f"Current kubectl context: {current_context}")
                
                # Check if context matches EKS cluster
                if self.eks_cluster_name in current_context:
                    print(f"✓ kubectl is configured for EKS cluster: {self.eks_cluster_name}")
                    return True
                else:
                    # Extract region from EKS cluster ARN
                    region = self.eks_cluster_arn.split(':')[3] if self.eks_cluster_arn else 'REGION'
                    
                    print("\n" + "!" * 60)
                    print(f"ERROR: kubectl context does not match EKS cluster")
                    print(f"Current context: {current_context}")
                    print(f"Expected cluster: {self.eks_cluster_name}")
                    print("!" * 60)
                    print("\nTo configure kubectl for this EKS cluster, run:")
                    print(f"  aws eks update-kubeconfig --name {self.eks_cluster_name} --region {region}")
                    return False
            else:
                # Extract region from EKS cluster ARN
                region = self.eks_cluster_arn.split(':')[3] if self.eks_cluster_arn else 'REGION'
                
                print("\n" + "!" * 60)
                print("ERROR: No kubectl context configured")
                print("!" * 60)
                print("\nTo configure kubectl for this EKS cluster, run:")
                print(f"  aws eks update-kubeconfig --name {self.eks_cluster_name} --region {region}")
                return False
                
        except subprocess.TimeoutExpired:
            print("Warning: kubectl command timed out")
            return False
        except FileNotFoundError:
            print("\n" + "!" * 60)
            print("ERROR: kubectl not found in PATH")
            print("!" * 60)
            return False
        except Exception as e:
            print(f"Warning: Error verifying kubectl config: {e}")
            return False
    
    def collect_kubectl_node_info(self):
        """Collect kubectl describe node information for all nodes."""
        if self.cluster_type != 'eks':
            print("Skipping kubectl collection - not an EKS cluster")
            return
        
        if not self.eks_cluster_name:
            print("Skipping kubectl collection - EKS cluster name not available")
            return
        
        print("\n" + "=" * 60)
        print("Collecting kubectl node information...")
        print("=" * 60)
        
        # Verify kubectl configuration - exit if not configured
        if not self.verify_kubectl_config():
            print("\n" + "!" * 60)
            print("ERROR: kubectl must be configured for EKS clusters")
            print("!" * 60)
            print("\nPlease configure kubectl and re-run the tool.\n")
            sys.exit(1)
        
        try:
            import subprocess
            
            # Create output directory
            kubectl_output_dir = tempfile.mkdtemp(prefix='kubectl_output_')
            
            # Define resources to collect
            collections = [
                # High Priority - Essential for troubleshooting
                {
                    'name': 'nodes_describe',
                    'command': ['kubectl', 'describe', 'nodes'],
                    'description': 'Node descriptions (capacity, conditions, pods)'
                },
                {
                    'name': 'pods_all_namespaces',
                    'command': ['kubectl', 'get', 'pods', '-A', '-o', 'wide'],
                    'description': 'All pods across namespaces (wide output)'
                },
                {
                    'name': 'pods_describe_all_namespaces',
                    'command': ['kubectl', 'describe', 'pods', '-A'],
                    'description': 'Detailed pod descriptions (all namespaces)'
                },
                {
                    'name': 'events_all_namespaces',
                    'command': ['kubectl', 'get', 'events', '-A', '--sort-by=.lastTimestamp'],
                    'description': 'Cluster events sorted by timestamp'
                },
                {
                    'name': 'pvcs_all_namespaces',
                    'command': ['kubectl', 'get', 'pvc', '-A', '-o', 'wide'],
                    'description': 'PersistentVolumeClaims (storage)'
                },
                {
                    'name': 'pvcs_describe_all_namespaces',
                    'command': ['kubectl', 'describe', 'pvc', '-A'],
                    'description': 'Detailed PVC descriptions'
                },
                {
                    'name': 'services_all_namespaces',
                    'command': ['kubectl', 'get', 'svc', '-A', '-o', 'wide'],
                    'description': 'Services (network endpoints)'
                },
                {
                    'name': 'services_describe_all_namespaces',
                    'command': ['kubectl', 'describe', 'svc', '-A'],
                    'description': 'Detailed service descriptions'
                },
                
                # Medium Priority - Very useful
                {
                    'name': 'deployments_all_namespaces',
                    'command': ['kubectl', 'get', 'deployments', '-A', '-o', 'wide'],
                    'description': 'Deployments'
                },
                {
                    'name': 'statefulsets_all_namespaces',
                    'command': ['kubectl', 'get', 'statefulsets', '-A', '-o', 'wide'],
                    'description': 'StatefulSets'
                },
                {
                    'name': 'daemonsets_all_namespaces',
                    'command': ['kubectl', 'get', 'daemonsets', '-A', '-o', 'wide'],
                    'description': 'DaemonSets'
                },
                {
                    'name': 'configmaps_all_namespaces',
                    'command': ['kubectl', 'get', 'configmaps', '-A'],
                    'description': 'ConfigMaps (metadata only)'
                },
                {
                    'name': 'secrets_all_namespaces',
                    'command': ['kubectl', 'get', 'secrets', '-A'],
                    'description': 'Secrets (metadata only, no content)'
                },
                {
                    'name': 'resourcequotas_all_namespaces',
                    'command': ['kubectl', 'get', 'resourcequota', '-A'],
                    'description': 'Resource quotas'
                },
                {
                    'name': 'networkpolicies_all_namespaces',
                    'command': ['kubectl', 'get', 'networkpolicies', '-A'],
                    'description': 'Network policies'
                },
            ]
            
            print(f"Collecting {len(collections)} Kubernetes resource types...")
            successful = 0
            failed = 0
            
            for collection in collections:
                name = collection['name']
                command = collection['command']
                description = collection['description']
                
                print(f"  Collecting: {description}...", end=' ')
                
                try:
                    result = subprocess.run(
                        command,
                        capture_output=True,
                        text=True,
                        timeout=60
                    )
                    
                    output_file = os.path.join(kubectl_output_dir, f'{name}.txt')
                    
                    if result.returncode == 0:
                        if result.stdout.strip():
                            with open(output_file, 'w') as f:
                                f.write(result.stdout)
                            print(f"✓")
                            successful += 1
                        else:
                            # Empty output (no resources of this type)
                            with open(output_file, 'w') as f:
                                f.write("No resources found\n")
                            print(f"✓ (empty)")
                            successful += 1
                    else:
                        # Command failed
                        with open(output_file, 'w') as f:
                            f.write(f"Error: {result.stderr}\n")
                        print(f"✗ ({result.stderr.strip()[:50]})")
                        failed += 1
                        
                except subprocess.TimeoutExpired:
                    output_file = os.path.join(kubectl_output_dir, f'{name}.txt')
                    with open(output_file, 'w') as f:
                        f.write("Error: Command timed out\n")
                    print(f"✗ (timeout)")
                    failed += 1
                    
                except Exception as e:
                    output_file = os.path.join(kubectl_output_dir, f'{name}.txt')
                    with open(output_file, 'w') as f:
                        f.write(f"Error: {str(e)}\n")
                    print(f"✗ ({str(e)[:50]})")
                    failed += 1
            
            print(f"\nCollection summary: {successful} successful, {failed} failed")
            
            # Create tarball with files at root level (no wrapper directory)
            print("\nCreating kubectl output tarball...")
            tarball_path = os.path.join(tempfile.gettempdir(), 'kubectl_resources.tar.gz')
            
            import tarfile
            with tarfile.open(tarball_path, 'w:gz') as tar:
                # Add each file directly to the tarball root (no parent directory)
                for filename in os.listdir(kubectl_output_dir):
                    file_path = os.path.join(kubectl_output_dir, filename)
                    tar.add(file_path, arcname=filename)
            
            print(f"Created tarball: {tarball_path}")
            
            # Upload to S3
            s3_key = f"{self.report_s3_key}/kubectl_resources.tar.gz"
            print(f"Uploading to S3: s3://{self.s3_bucket}/{s3_key}")
            
            self.s3_client.upload_file(tarball_path, self.s3_bucket, s3_key)
            
            print(f"✓ Successfully uploaded kubectl resource information to S3")
            print(f"  Location: s3://{self.s3_bucket}/{s3_key}")
            
            # Cleanup
            import shutil
            shutil.rmtree(kubectl_output_dir, ignore_errors=True)
            os.remove(tarball_path)
            
        except Exception as e:
            print(f"Error collecting kubectl information: {e}")
            if self.debug:
                import traceback
                traceback.print_exc()


def main():
    parser = argparse.ArgumentParser(
        description='HyperPod Issue Report Collector - Supports both EKS and Slurm clusters',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic usage - auto-detects cluster type and collects appropriate diagnostics
  python hyperpod_eks_issue_report.py --cluster my-cluster --s3-path s3://my-bucket
  
  # EKS cluster - collects nvidia-smi, containerd status, kubelet status, EKS logs, resource config, cluster logs, systemd services, disk usage
  python hyperpod_eks_issue_report.py --cluster my-eks-cluster --s3-path s3://my-bucket
  
  # Slurm cluster - collects nvidia-smi, nvidia-bug-report, sinfo, Slurm services/config/logs, system logs
  python hyperpod_eks_issue_report.py --cluster my-slurm-cluster --s3-path s3://my-bucket
  
  # With custom prefix
  python hyperpod_eks_issue_report.py --cluster my-cluster --s3-path s3://my-bucket/diagnostics
  
  # Add additional commands
  python hyperpod_eks_issue_report.py --cluster my-cluster --s3-path s3://my-bucket \\
    --command "df -h" \\
    --command "free -h"
  
  # Target specific instance groups
  python hyperpod_eks_issue_report.py --cluster my-cluster --s3-path s3://my-bucket \\
    --instance-groups worker-group-1 worker-group-2
  
  # Target specific instance IDs
  python hyperpod_eks_issue_report.py --cluster my-cluster --s3-path s3://my-bucket \\
    --nodes i-abc123 i-def456
        """
    )
    
    parser.add_argument('--cluster', '-c', required=True, help='HyperPod cluster name (EKS or Slurm)')
    parser.add_argument('--s3-path', '-s', required=True, help='S3 path for storing reports (e.g., s3://bucket-name/prefix or s3://bucket-name)')
    parser.add_argument('--command', '-cmd', action='append', help='Additional command to execute on nodes (can be specified multiple times)')
    parser.add_argument('--instance-groups', '-g', nargs='+', help='Target specific instance groups (e.g., --instance-groups worker1 worker2)')
    parser.add_argument('--nodes', '-n', nargs='+', help='Target specific instance IDs (e.g., --nodes i-abc123 i-def456)')
    parser.add_argument('--max-workers', '-w', type=int, default=64, help='Maximum concurrent workers (default: 64)')
    parser.add_argument('--debug', '-d', action='store_true', help='Enable debug mode')
    
    args = parser.parse_args()
    
    # Validate mutually exclusive options
    if args.instance_groups and args.nodes:
        print("Error: --instance-groups and --nodes cannot be used together")
        sys.exit(1)
    
    try:
        collector = HyperPodIssueReportCollector(
            cluster_name=args.cluster,
            s3_path=args.s3_path,
            debug=args.debug
        )
        
        # User-specified commands
        commands = []
        
        # Add any user-specified commands
        if args.command:
            commands.extend(args.command)
        
        collector.collect_reports(
            commands=commands,
            instance_groups=args.instance_groups,
            instance_ids=args.nodes,
            max_workers=args.max_workers
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
