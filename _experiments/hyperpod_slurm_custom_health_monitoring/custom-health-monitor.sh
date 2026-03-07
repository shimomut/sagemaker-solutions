#!/bin/bash

# HyperPod Slurm Custom Health Monitor
# Continuously monitors worker node health and triggers remediation

set -euo pipefail

# Configuration
CHECK_INTERVAL=60  # Seconds between health checks
DISK_USAGE_THRESHOLD=98  # Percentage - trigger replacement for disk space issues
LOG_PREFIX="[HyperPod Health Monitor]"

# Logging function
log() {
    echo "$LOG_PREFIX $(date '+%Y-%m-%d %H:%M:%S') - $1"
}

# Check if this is a worker node (not head node)
is_worker_node() {
    # Head node typically has slurmctld service
    if systemctl list-unit-files 2>/dev/null | grep -q slurmctld.service; then
        log "DEBUG: slurmctld.service found - this is a head node"
        return 1  # This is head node
    fi
    
    # Worker nodes should have slurmd service
    if systemctl list-unit-files 2>/dev/null | grep -q slurmd.service; then
        log "DEBUG: slurmd.service found - this is a worker node"
        return 0  # This is worker node
    fi
    
    # Neither service found - return error code to trigger retry
    log "DEBUG: Neither slurmctld nor slurmd service found"
    return 2  # Special code for "not ready yet"
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

# Check disk space health (outputs usage percentage of root filesystem)
check_disk_space() {
    # Get root filesystem usage percentage (without % sign)
    local usage
    usage=$(df -h / | awk 'NR==2 {print $5}' | sed 's/%//')
    
    if [ -z "$usage" ] || ! [[ "$usage" =~ ^[0-9]+$ ]]; then
        log "ERROR: Could not determine disk usage"
        echo "0"
        return
    fi
    
    echo "$usage"
}

# Trigger instance remediation via HyperPod API
# Parameters: $1 = action ("reboot" or "replace")
trigger_remediation() {
    local action="$1"
    
    if [ "$action" != "reboot" ] && [ "$action" != "replace" ]; then
        log "ERROR: Invalid action '$action'. Must be 'reboot' or 'replace'"
        return 1
    fi
    
    log "Triggering instance $action via batch-${action}-cluster-nodes API..."
    
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
    
    log "Cluster: $cluster_name, Instance: $instance_id, Region: $region, Action: $action"
    
    # Call appropriate SageMaker API
    aws sagemaker "batch-${action}-cluster-nodes" \
        --region "$region" \
        --cluster-name "$cluster_name" \
        --node-ids "$instance_id" \
        2>&1 | while read -r line; do log "API Response: $line"; done
    
    local exit_code=${PIPESTATUS[0]}
    if [ $exit_code -eq 0 ]; then
        log "Successfully triggered $action for instance $instance_id"
        return 0
    else
        log "ERROR: Failed to trigger $action (exit code: $exit_code)"
        return 1
    fi
}

# Main health check loop
main() {
    log "Starting HyperPod Slurm health monitor..."
    
    # Wait for slurmd.service to be available (with timeout)
    local max_wait=120  # 2 minutes (reduced from 5 since slurmd should already be running)
    local elapsed=0
    local check_interval=5  # Check more frequently (every 5 seconds instead of 10)
    
    log "Waiting for slurmd.service to be available..."
    while [ $elapsed -lt $max_wait ]; do
        if systemctl list-unit-files 2>/dev/null | grep -q slurmd.service; then
            log "slurmd.service unit file detected"
            break
        fi
        
        if [ $elapsed -eq 0 ] || [ $((elapsed % 30)) -eq 0 ]; then
            # Only log every 30 seconds to reduce noise
            log "slurmd.service not yet available, waiting... (${elapsed}s/${max_wait}s)"
        fi
        sleep $check_interval
        elapsed=$((elapsed + check_interval))
    done
    
    if [ $elapsed -ge $max_wait ]; then
        log "ERROR: Timeout waiting for slurmd.service. This may not be a worker node."
        exit 1
    fi
    
    # Give systemd a moment to fully register the service
    sleep 2
    
    # Check if this is a worker node (retry infinitely if services not ready)
    while true; do
        is_worker_node
        local result=$?
        
        if [ $result -eq 0 ]; then
            # This is a worker node - proceed with monitoring
            log "Worker node confirmed. Proceeding with health monitoring setup..."
            break
        elif [ $result -eq 1 ]; then
            # This is a head node - exit cleanly
            log "This is a head node. Exiting."
            exit 0
        else
            # Neither service found yet (result == 2) - retry
            log "Slurm services not ready yet. Retrying in 10 seconds..."
            sleep 10
        fi
    done
    
    log "Worker node detected. Waiting for services to stabilize..."
    
    # Debug: Check slurmd status
    log "DEBUG: Checking slurmd.service status..."
    if systemctl is-enabled --quiet slurmd.service 2>/dev/null; then
        log "DEBUG: slurmd.service is enabled"
    else
        log "DEBUG: slurmd.service is NOT enabled"
    fi
    if systemctl is-active --quiet slurmd.service 2>/dev/null; then
        log "DEBUG: slurmd.service is active"
    else
        log "DEBUG: slurmd.service is NOT active yet"
    fi
    log "DEBUG: slurmd.service full status:"
    systemctl status slurmd.service --no-pager || true
    
    # Wait for slurmd to be fully started and stable
    local wait_time=30
    log "Waiting ${wait_time} seconds for slurmd to stabilize..."
    sleep $wait_time
    
    log "Starting health monitoring..."
    
    while true; do
        local needs_reboot=false
        local needs_replacement=false
        
        # Check slurmd health
        if ! is_slurmd_healthy; then
            log "WARNING: slurmd is not healthy"
            needs_reboot=true
        fi
        
        # Check disk space
        local disk_usage
        disk_usage=$(check_disk_space)
        
        if [ $disk_usage -ge $DISK_USAGE_THRESHOLD ]; then
            log "CRITICAL: Disk usage ($disk_usage%) exceeds threshold ($DISK_USAGE_THRESHOLD%)"
            needs_replacement=true
        fi
        
        # Take action based on health status
        if [ "$needs_replacement" = true ]; then
            log "Triggering instance replacement due to critical disk space issues..."
            
            if trigger_remediation "replace"; then
                log "Replacement triggered successfully. Service will exit."
                exit 0
            else
                log "ERROR: Failed to trigger replacement. Will retry on next check."
            fi
        elif [ "$needs_reboot" = true ]; then
            log "Triggering instance reboot due to service issues..."
            
            if trigger_remediation "reboot"; then
                log "Reboot triggered successfully. Service will exit."
                exit 0
            else
                log "ERROR: Failed to trigger reboot. Will retry on next check."
            fi
        else
            log "All health checks passed (disk usage: ${disk_usage}%)"
        fi
        
        sleep $CHECK_INTERVAL
    done
}

# Run main function
main
