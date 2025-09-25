#!/usr/bin/env python3
"""
Test script to demonstrate interface DOWN detection and failure handling

This script tests the behavior of the connectivity verifier when an interface
is disabled (set to DOWN status).
"""

import subprocess
import sys
import time
from verify_connectivity import ConnectivityVerifier, Colors


def run_command(command: str, timeout: int = 10):
    """Execute a shell command"""
    try:
        result = subprocess.run(
            command, 
            shell=True, 
            capture_output=True, 
            text=True,
            timeout=timeout
        )
        return result.returncode, result.stdout, result.stderr
    except Exception as e:
        return 1, "", str(e)


def test_interface_down_behavior(interface_name: str = "enp74s0"):
    """Test interface behavior when set to DOWN"""
    
    print(f"{Colors.bold('Interface DOWN Test')}")
    print(f"{Colors.bold('='*50)}")
    print(f"Testing interface: {interface_name}")
    print()
    
    # Step 1: Test interface when UP
    print(f"{Colors.info('Step 1: Testing interface when UP')}")
    print("-" * 40)
    
    verifier = ConnectivityVerifier(interface_name=interface_name, verbose=False)
    results_up = verifier.run_comprehensive_test()
    
    success_rate_up = results_up.get('summary', {}).get('success_rate', 0)
    print(f"Success rate when UP: {Colors.success(f'{success_rate_up:.1f}%') if success_rate_up >= 70 else Colors.error(f'{success_rate_up:.1f}%')}")
    
    # Step 2: Disable interface
    print(f"\n{Colors.info('Step 2: Disabling interface')}")
    print("-" * 40)
    
    print(f"Setting {interface_name} to DOWN...")
    exit_code, stdout, stderr = run_command(f"sudo ip link set {interface_name} down")
    
    if exit_code != 0:
        print(f"{Colors.error('Failed to disable interface:')} {stderr}")
        return False
    
    print(f"{Colors.success('Interface disabled successfully')}")
    
    # Verify interface is down
    exit_code, stdout, stderr = run_command(f"ip link show {interface_name}")
    if "state DOWN" in stdout:
        print(f"{Colors.success('Confirmed: Interface is DOWN')}")
    else:
        print(f"{Colors.warning('Warning: Interface state unclear')}")
    
    # Step 3: Test interface when DOWN
    print(f"\n{Colors.info('Step 3: Testing interface when DOWN')}")
    print("-" * 40)
    
    verifier_down = ConnectivityVerifier(interface_name=interface_name, verbose=False)
    results_down = verifier_down.run_comprehensive_test()
    
    success_rate_down = results_down.get('summary', {}).get('success_rate', 0)
    print(f"Success rate when DOWN: {Colors.error(f'{success_rate_down:.1f}%')}")
    
    # Step 4: Re-enable interface
    print(f"\n{Colors.info('Step 4: Re-enabling interface')}")
    print("-" * 40)
    
    print(f"Setting {interface_name} to UP...")
    exit_code, stdout, stderr = run_command(f"sudo ip link set {interface_name} up")
    
    if exit_code != 0:
        print(f"{Colors.error('Failed to enable interface:')} {stderr}")
        return False
    
    # Add back the default route (this is typically needed after bringing interface up)
    print("Restoring default route...")
    exit_code, stdout, stderr = run_command(f"sudo ip route add default via 10.1.0.1 dev {interface_name} metric 500")
    
    if exit_code != 0 and "File exists" not in stderr:
        print(f"{Colors.warning('Warning: Could not add default route:')} {stderr}")
    
    print(f"{Colors.success('Interface re-enabled successfully')}")
    
    # Step 5: Test interface when UP again
    print(f"\n{Colors.info('Step 5: Testing interface when UP again')}")
    print("-" * 40)
    
    # Wait a moment for interface to stabilize
    time.sleep(2)
    
    verifier_restored = ConnectivityVerifier(interface_name=interface_name, verbose=False)
    results_restored = verifier_restored.run_comprehensive_test()
    
    success_rate_restored = results_restored.get('summary', {}).get('success_rate', 0)
    print(f"Success rate when restored: {Colors.success(f'{success_rate_restored:.1f}%') if success_rate_restored >= 70 else Colors.error(f'{success_rate_restored:.1f}%')}")
    
    # Summary
    print(f"\n{Colors.bold('='*50)}")
    print(f"{Colors.bold('TEST SUMMARY')}")
    print(f"{Colors.bold('='*50)}")
    print(f"Interface: {interface_name}")
    print(f"UP (initial):   {success_rate_up:.1f}%")
    print(f"DOWN:           {success_rate_down:.1f}%")
    print(f"UP (restored):  {success_rate_restored:.1f}%")
    
    # Validate expected behavior
    expected_behavior = (
        success_rate_up >= 70 and          # Should work when UP
        success_rate_down < 30 and         # Should fail when DOWN
        success_rate_restored >= 70        # Should work when restored
    )
    
    if expected_behavior:
        print(f"\n{Colors.success('✓ Test PASSED: Interface DOWN detection working correctly')}")
        return True
    else:
        print(f"\n{Colors.error('✗ Test FAILED: Unexpected behavior detected')}")
        return False


def main():
    """Main entry point"""
    interface_name = sys.argv[1] if len(sys.argv) > 1 else "enp74s0"
    
    try:
        success = test_interface_down_behavior(interface_name)
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print(f"\n{Colors.warning('Test interrupted by user')}")
        sys.exit(1)
    except Exception as e:
        print(f"\n{Colors.error(f'Test failed with error: {e}')}")
        sys.exit(1)


if __name__ == "__main__":
    main()