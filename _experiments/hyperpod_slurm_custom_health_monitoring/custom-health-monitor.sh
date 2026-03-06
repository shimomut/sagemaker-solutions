#!/bin/bash

# HyperPod Slurm Custom Health Monitor
# Continuously monitors worker node health and triggers remediation

set -euo pipefail

# Configuration
CHECK_INTERVAL=60  # Seconds between health checks
SLURMD_RESTART_ATTEMPTS=3
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

# Attempt to restart slurmd
restart_slurmd() {
    log "Attempting to restart slurmd..."
    if systemctl restart slurmd; then
        sleep 5
        if is_slurmd_healthy; then
            log "Successfully restarted slurmd"
            return 0
        fi
    fi
    log "Failed to restart slurmd"
    return 1
}

# Trigger instance reboot via HyperPod API
trigger_reboot() {
    log "Triggering instance reboot via batch-reboot-cluster-nodes API..."
    
    # Get instance metadata
    local instance_id
    local region
    
    instance_id=$(ec2-metadata --instance-id | cut -d ' ' -f 2)
    region=$(ec2-metadata --availability-zone | cut -d ' ' -f 2 | sed 's/[a-z]$//')
    
    # Get cluster name from instance tags
    local cluster_name
    cluster_name=$(aws ec2 describe-tags \
        --region "$region" \
        --filters "Name=resource-id,Values=$instance_id" "Name=key,Values=aws:sagemaker:cluster-name" \
        --query 'Tags[0].Value' \
        --output text)
    
    if [ -z "$cluster_name" ] || [ "$cluster_name" == "None" ]; then
        log "ERROR: Could not determine cluster name from instance tags"
        return 1
    fi
    
    # Get node ID from instance tags
    local node_id
    node_id=$(aws ec2 describe-tags \
        --region "$region" \
        --filters "Name=resource-id,Values=$instance_id" "Name=key,Values=aws:sagemaker:node-id" \
        --query 'Tags[0].Value' \
        --output text)
    
    if [ -z "$node_id" ] || [ "$node_id" == "None" ]; then
        log "ERROR: Could not determine node ID from instance tags"
        return 1
    fi
    
    log "Cluster: $cluster_name, Node: $node_id, Instance: $instance_id"
    
    # Call batch-reboot-cluster-nodes API
    aws sagemaker batch-reboot-cluster-nodes \
        --region "$region" \
        --cluster-name "$cluster_name" \
        --node-ids "$node_id" \
        2>&1 | while read -r line; do log "API Response: $line"; done
    
    local exit_code=${PIPESTATUS[0]}
    if [ $exit_code -eq 0 ]; then
        log "Successfully triggered reboot for node $node_id"
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
    
    local restart_attempts=0
    
    while true; do
        if is_slurmd_healthy; then
            if [ $restart_attempts -gt 0 ]; then
                log "slurmd is now healthy after restart"
                restart_attempts=0
            fi
        else
            log "WARNING: slurmd is not healthy"
            
            if [ $restart_attempts -lt $SLURMD_RESTART_ATTEMPTS ]; then
                restart_attempts=$((restart_attempts + 1))
                log "Restart attempt $restart_attempts of $SLURMD_RESTART_ATTEMPTS"
                
                if restart_slurmd; then
                    restart_attempts=0
                fi
            else
                log "ERROR: slurmd failed to recover after $SLURMD_RESTART_ATTEMPTS restart attempts"
                log "Triggering instance reboot..."
                
                if trigger_reboot; then
                    log "Reboot triggered successfully. Service will exit."
                    exit 0
                else
                    log "ERROR: Failed to trigger reboot. Will retry on next check."
                    restart_attempts=0  # Reset to try restart again
                fi
            fi
        fi
        
        sleep $CHECK_INTERVAL
    done
}

# Run main function
main
