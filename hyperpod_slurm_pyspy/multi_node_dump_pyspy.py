#!/usr/bin/env python3
"""
Multi-node runner script to execute dump_pyspy.py on all cluster nodes in parallel.
"""

import subprocess
import sys
import argparse
from datetime import datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock


# Thread-safe print lock
print_lock = Lock()


def safe_print(*args, **kwargs):
    """Thread-safe print function."""
    with print_lock:
        print(*args, **kwargs)


def get_node_list(nodes_spec):
    """Convert node specification to list of hostnames using scontrol."""
    try:
        result = subprocess.run(
            ['scontrol', 'show', 'hostnames', nodes_spec],
            capture_output=True,
            text=True,
            check=True
        )
        nodes = [line.strip() for line in result.stdout.strip().split('\n') if line.strip()]
        return nodes
    except subprocess.CalledProcessError as e:
        safe_print(f"ERROR: Failed to get node list: {e}", file=sys.stderr)
        return []


def run_on_node(node, command):
    """Execute command on a single node via SSH."""
    safe_print(f"[{node}] Starting...")
    
    try:
        result = subprocess.run(
            ['ssh', node, command],
            capture_output=True,
            text=True,
            timeout=300  # 5 minute timeout
        )
        
        success = result.returncode == 0
        
        if success:
            safe_print(f"[{node}] SUCCESS")
        else:
            safe_print(f"[{node}] FAILED (exit code: {result.returncode})")
        
        return {
            'node': node,
            'success': success,
            'returncode': result.returncode,
            'stdout': result.stdout,
            'stderr': result.stderr
        }
        
    except subprocess.TimeoutExpired:
        safe_print(f"[{node}] TIMEOUT")
        return {
            'node': node,
            'success': False,
            'returncode': -1,
            'stdout': '',
            'stderr': 'Command timed out'
        }
    except Exception as e:
        safe_print(f"[{node}] ERROR: {e}")
        return {
            'node': node,
            'success': False,
            'returncode': -1,
            'stdout': '',
            'stderr': str(e)
        }


def main():
    parser = argparse.ArgumentParser(
        description='Run dump_pyspy.py on multiple cluster nodes in parallel'
    )
    parser.add_argument(
        '--nodes',
        type=str,
        required=True,
        help='Node specification (e.g., "ip-10-1-1-[1-10],ip-10-1-2-5")'
    )
    parser.add_argument(
        '-p', '--process-pattern',
        type=str,
        default=None,
        help='Regex pattern to match process command line (default: python)'
    )
    parser.add_argument(
        '--max-workers',
        type=int,
        default=10,
        help='Maximum number of parallel SSH connections (default: 10)'
    )
    parser.add_argument(
        '--script-dir',
        type=str,
        default=None,
        help='Directory containing dump_pyspy.py (default: script directory)'
    )
    
    args = parser.parse_args()
    
    # Determine script directory
    if args.script_dir:
        script_dir = Path(args.script_dir).absolute()
    else:
        script_dir = Path(__file__).parent.absolute()
    
    # Generate timestamp for output directory
    timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    output_dir = script_dir / f"pyspy-{timestamp}"
    dump_script = script_dir / "dump_pyspy.py"
    
    safe_print(f"Script directory: {script_dir}")
    safe_print(f"Output directory: {output_dir}")
    safe_print(f"Dump script: {dump_script}")
    
    # Get list of nodes
    safe_print(f"\nResolving node list from: {args.nodes}")
    nodes = get_node_list(args.nodes)
    
    if not nodes:
        safe_print("ERROR: No nodes found", file=sys.stderr)
        return 1
    
    safe_print(f"Found {len(nodes)} node(s): {', '.join(nodes)}")
    
    # Build command
    command = f"python3 {dump_script} -o {output_dir} --py-spy /fsx/ubuntu/.local/bin/py-spy"
    if args.process_pattern:
        # Escape single quotes in the pattern for shell safety
        escaped_pattern = args.process_pattern.replace("'", "'\\''")
        command += f" -p '{escaped_pattern}'"
    
    safe_print(f"\nCommand: {command}")
    safe_print(f"Max parallel workers: {args.max_workers}")
    safe_print("\n" + "=" * 80)
    safe_print("Starting parallel execution...\n")
    
    # Execute on all nodes in parallel
    results = []
    with ThreadPoolExecutor(max_workers=args.max_workers) as executor:
        # Submit all tasks
        future_to_node = {
            executor.submit(run_on_node, node, command): node 
            for node in nodes
        }
        
        # Collect results as they complete
        for future in as_completed(future_to_node):
            result = future.result()
            results.append(result)
    
    # Print summary
    safe_print("\n" + "=" * 80)
    safe_print("EXECUTION SUMMARY")
    safe_print("=" * 80)
    
    success_count = sum(1 for r in results if r['success'])
    failed_count = len(results) - success_count
    
    safe_print(f"Total nodes: {len(results)}")
    safe_print(f"Successful:  {success_count}")
    safe_print(f"Failed:      {failed_count}")
    
    if failed_count > 0:
        safe_print("\nFailed nodes:")
        for result in results:
            if not result['success']:
                safe_print(f"  - {result['node']} (exit code: {result['returncode']})")
                if result['stderr']:
                    safe_print(f"    Error: {result['stderr'][:200]}")
    
    safe_print(f"\nOutput directory: {output_dir}")
    
    return 0 if failed_count == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
