#!/bin/bash

# HyperPod Slurm Custom Health Monitor
# Continuously monitors worker node health and triggers remediation

set -euo pipefail

# Configuration
CHECK_INTERVAL=60  # Seconds between health checks
LOG_PREFIX="[HyperPod Health Monitor]"

# Logging function
log() {
    echo "$LOG_PREFIX $(date '+%Y-%m-%d %H:%M:%S') - $1"
}

# Check if this is a worker node (not head node)
is_worker_node() {
    # Head node typically has slurmctld running
    if systemctl is-active --quiet slurmctld; then
        return 1  # This is head node
    fi
    
    # Worker nodes should have slurmd
    if systemctl list-unit-files | grep -q slurmd.service; then
        return 0  # This is worker node
    fi
    
    return 1  # Not a worker node
}

# Check if slurmd is healthy
is_slurmd_healthy() {
    if ! systemctl is-active --quiet slurmd; then
        return 1
    fi
    
    # Additional health checks can be added here
    # For example: check if slurmd is responding to commands
    if ! systemctl status slurmd >/dev/null 2>&1; then
        return 1
    fi
    
    return 0
}

# Trigger instance reboot via HyperPod API
trigger_reboot() {
    log "Triggering instance reboot via batch-reboot-cluster-nodes API..."
    
    # Get cluster name from ec2-metadata user-data
    local cluster_name
    cluster_name=$(ec2-metadata --user-data | grep -oP 'export CLUSTER_NAME=\K[^\s]+' || true)
    
    if [ -z "$cluster_name" ]; then
        log "ERROR: Could not determine cluster name from ec2-metadata"
        return 1
    fi
    
    # Get region from ec2-metadata
    local region
    region=$(ec2-metadata --availability-zone | cut -d ' ' -f 2 | sed 's/[a-z]$//')
    
    # Get instance ID from ec2-metadata
    local instance_id
    instance_id=$(ec2-metadata --instance-id | cut -d ' ' -f 2)
    
    if [ -z "$instance_id" ]; then
        log "ERROR: Could not determine instance ID from ec2-metadata"
        return 1
    fi
    
    log "Cluster: $cluster_name, Instance: $instance_id, Region: $region"
    
    # Call batch-reboot-cluster-nodes API with instance ID
    aws sagemaker batch-reboot-cluster-nodes \
        --region "$region" \
        --cluster-name "$cluster_name" \
        --node-ids "$instance_id" \
        2>&1 | while read -r line; do log "API Response: $line"; done
    
    local exit_code=${PIPESTATUS[0]}
    if [ $exit_code -eq 0 ]; then
        log "Successfully triggered reboot for instance $instance_id"
        return 0
    else
        log "ERROR: Failed to trigger reboot (exit code: $exit_code)"
        return 1
    fi
}

# Main health check loop
main() {
    log "Starting HyperPod Slurm health monitor..."
    
    # Check if this is a worker node
    if ! is_worker_node; then
        log "This is not a worker node. Exiting."
        exit 0
    fi
    
    log "Worker node detected. Starting health monitoring..."
    
    while true; do
        if is_slurmd_healthy; then
            log "slurmd is healthy"
        else
            log "WARNING: slurmd is not healthy"
            log "Triggering instance reboot..."
            
            if trigger_reboot; then
                log "Reboot triggered successfully. Service will exit."
                exit 0
            else
                log "ERROR: Failed to trigger reboot. Will retry on next check."
            fi
        fi
        
        sleep $CHECK_INTERVAL
    done
}

# Run main function
main
