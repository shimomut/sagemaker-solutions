#!/usr/bin/env python3
"""
Script to dump py-spy output for Python processes matching a pattern.
Finds all processes matching the specified regex pattern and dumps their stack traces.
"""

import subprocess
import re
import sys
import socket
import argparse
from pathlib import Path


def get_process_info(pid):
    """Get process information including parent process details."""
    try:
        # Get process info using ps
        result = subprocess.run(
            ['ps', '-o', 'pid,ppid,comm,cmd', '-p', pid],
            capture_output=True,
            text=True,
            check=True
        )
        
        lines = result.stdout.strip().split('\n')
        if len(lines) < 2:
            return None
        
        # Parse the process line (skip header)
        proc_line = lines[1].split(None, 3)
        if len(proc_line) < 4:
            return None
        
        pid_val, ppid, comm, cmd = proc_line
        
        # Get parent process info
        parent_result = subprocess.run(
            ['ps', '-o', 'pid,ppid,comm,cmd', '-p', ppid],
            capture_output=True,
            text=True,
            check=True
        )
        
        parent_lines = parent_result.stdout.strip().split('\n')
        parent_info = None
        if len(parent_lines) >= 2:
            parent_line = parent_lines[1].split(None, 3)
            if len(parent_line) >= 4:
                parent_info = {
                    'pid': parent_line[0],
                    'ppid': parent_line[1],
                    'comm': parent_line[2],
                    'cmd': parent_line[3]
                }
        
        return {
            'pid': pid_val,
            'ppid': ppid,
            'comm': comm,
            'cmd': cmd,
            'parent': parent_info
        }
        
    except Exception as e:
        print(f"Warning: Could not get process info for PID {pid}: {e}", file=sys.stderr)
        return None


def get_matching_pids(process_pattern):
    """Find PIDs of processes matching the target command pattern."""
    try:
        # Get process list with full command
        result = subprocess.run(
            ['ps', 'aux'],
            capture_output=True,
            text=True,
            check=True
        )
        
        pids = []
        
        for line in result.stdout.splitlines():
            if re.search(process_pattern, line):
                # Extract PID (second column in ps aux output)
                parts = line.split()
                if len(parts) >= 2:
                    pid = parts[1]
                    pids.append(pid)
                    print(f"Found matching process: PID {pid}")
        
        return pids
    
    except subprocess.CalledProcessError as e:
        print(f"Error running ps command: {e}", file=sys.stderr)
        return []


def dump_pyspy(pid, output_file, py_spy_path='py-spy'):
    """Run py-spy dump for a given PID and save to file."""
    try:
        print(f"Dumping py-spy output for PID {pid} to {output_file}...")
        
        # Get process information first
        proc_info = get_process_info(pid)
        
        result = subprocess.run(
            [py_spy_path, 'dump', '--pid', pid],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        # Write output (both stdout and stderr) to file
        with open(output_file, 'w') as f:
            f.write(f"{py_spy_path} dump --pid {pid}\n")
            f.write("=" * 80 + "\n\n")
            
            # Write process information
            if proc_info:
                f.write("PROCESS INFORMATION:\n")
                f.write("-" * 80 + "\n")
                f.write(f"PID:     {proc_info['pid']}\n")
                f.write(f"PPID:    {proc_info['ppid']}\n")
                f.write(f"Command: {proc_info['comm']}\n")
                f.write(f"Full:    {proc_info['cmd']}\n")
                f.write("\n")
                
                if proc_info['parent']:
                    f.write("PARENT PROCESS:\n")
                    f.write("-" * 80 + "\n")
                    f.write(f"PID:     {proc_info['parent']['pid']}\n")
                    f.write(f"PPID:    {proc_info['parent']['ppid']}\n")
                    f.write(f"Command: {proc_info['parent']['comm']}\n")
                    f.write(f"Full:    {proc_info['parent']['cmd']}\n")
                
                f.write("\n" + "=" * 80 + "\n\n")
            
            # Write py-spy output
            f.write("PY-SPY STACK TRACE:\n")
            f.write("-" * 80 + "\n")
            if result.stdout:
                f.write(result.stdout)
            if result.stderr:
                f.write("\n--- stderr ---\n")
                f.write(result.stderr)
            if result.returncode != 0:
                f.write(f"\n--- Return code: {result.returncode} ---\n")
        
        if result.returncode != 0:
            print(f"ERROR: py-spy failed for PID {pid} with return code {result.returncode}", file=sys.stderr)
            if result.stderr:
                print(f"  stderr: {result.stderr.strip()}", file=sys.stderr)
            return False
        
        print(f"Successfully dumped to {output_file}")
        return True
        
    except subprocess.TimeoutExpired:
        print(f"ERROR: Timeout while dumping PID {pid}", file=sys.stderr)
        return False
    except Exception as e:
        print(f"ERROR: Exception while dumping PID {pid}: {e}", file=sys.stderr)
        return False


def dump_top(output_file):
    """Run top command once and save to file."""
    try:
        print(f"Dumping top output to {output_file}...")
        
        # Run top in batch mode with 1 iteration
        result = subprocess.run(
            ['top', '-b', '-n', '1'],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        with open(output_file, 'w') as f:
            f.write("top -b -n 1\n")
            f.write("=" * 80 + "\n\n")
            f.write(result.stdout)
        
        print(f"Successfully dumped top output to {output_file}")
        return True
        
    except Exception as e:
        print(f"Error dumping top output: {e}", file=sys.stderr)
        return False


def main():
    """Main function to find processes and dump py-spy output."""
    parser = argparse.ArgumentParser(
        description='Dump py-spy and top output for Python processes'
    )
    parser.add_argument(
        '-p', '--process-pattern',
        type=str,
        default=r'python',
        help='Regex pattern to match process command line (default: python)'
    )
    parser.add_argument(
        '-o', '--output-dir',
        type=str,
        default='.',
        help='Output directory for dump files (default: current directory)'
    )
    parser.add_argument(
        '--py-spy',
        type=str,
        default='py-spy',
        help='Path to py-spy executable (default: py-spy)'
    )
    args = parser.parse_args()
    
    # Get hostname
    hostname = socket.gethostname()
    print(f"Running on host: {hostname}")
    
    # Create output directory if it doesn't exist
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"Output directory: {output_dir.absolute()}")
    print(f"Using py-spy: {args.py_spy}")
    print(f"Process pattern: {args.process_pattern}")
    
    # Dump top output first
    top_file = output_dir / f"{hostname}_top.txt"
    dump_top(top_file)
    
    print("\nSearching for matching processes...")
    
    pids = get_matching_pids(args.process_pattern)
    
    if not pids:
        print("No matching processes found.")
        return 1
    
    print(f"\nFound {len(pids)} matching process(es)")
    
    success_count = 0
    for pid in pids:
        output_file = output_dir / f"{hostname}_{pid}.py-spy"
        if dump_pyspy(pid, output_file, args.py_spy):
            success_count += 1
    
    print(f"\nCompleted: {success_count}/{len(pids)} dumps successful")
    return 0 if success_count == len(pids) else 1


if __name__ == '__main__':
    sys.exit(main())
