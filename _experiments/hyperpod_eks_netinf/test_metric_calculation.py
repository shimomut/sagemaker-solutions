#!/usr/bin/env python3
"""
Test script for route metric calculation logic
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from hyperpod_eks_netinf import NetworkInterfaceManager


def test_metric_calculation():
    """Test the metric calculation with various routing scenarios"""
    
    # Create manager without initializing boto3 client
    manager = NetworkInterfaceManager.__new__(NetworkInterfaceManager)
    manager.default_interfaces = []
    manager.sagemaker_interfaces = []
    manager.route_table = []
    
    # Mock the run_command method to simulate different routing table scenarios
    original_run_command = manager.run_command
    
    def mock_run_command_scenario_1(command, capture_output=True):
        """No existing routes"""
        if "ip route show" in command:
            return 0, "", ""
        return original_run_command(command, capture_output)
    
    def mock_run_command_scenario_2(command, capture_output=True):
        """Single default route with metric 0"""
        if "ip route show" in command:
            return 0, "default via 192.168.1.1 dev eth0", ""
        return original_run_command(command, capture_output)
    
    def mock_run_command_scenario_3(command, capture_output=True):
        """Multiple routes with various metrics"""
        if "ip route show" in command:
            routes = [
                "default via 192.168.1.1 dev eth0",
                "default via 10.0.0.1 dev eth1 metric 200",
                "10.1.0.0/16 dev eth2 metric 300",
                "192.168.1.0/24 dev eth0 proto kernel scope link src 192.168.1.100"
            ]
            return 0, "\n".join(routes), ""
        return original_run_command(command, capture_output)
    
    def mock_run_command_scenario_4(command, capture_output=True):
        """High existing metrics"""
        if "ip route show" in command:
            routes = [
                "default via 192.168.1.1 dev eth0 metric 950",
                "10.1.0.0/16 dev eth1 metric 800"
            ]
            return 0, "\n".join(routes), ""
        return original_run_command(command, capture_output)
    
    # Test scenarios
    test_cases = [
        ("No existing routes", mock_run_command_scenario_1, 100),
        ("Single default route (metric 0)", mock_run_command_scenario_2, 100),
        ("Multiple routes with metrics", mock_run_command_scenario_3, 400),  # 300 + 100
        ("High existing metrics", mock_run_command_scenario_4, 1000),  # Capped at 1000
    ]
    
    print("Testing Route Metric Calculation")
    print("=" * 50)
    
    all_passed = True
    
    for scenario_name, mock_function, expected_metric in test_cases:
        print(f"\nTesting: {scenario_name}")
        print("-" * 30)
        
        # Replace the run_command method
        manager.run_command = mock_function
        
        # Calculate metric
        calculated_metric = manager.calculate_route_metric()
        
        # Check result
        if calculated_metric == expected_metric:
            print(f"✓ PASS: Expected {expected_metric}, got {calculated_metric}")
        else:
            print(f"✗ FAIL: Expected {expected_metric}, got {calculated_metric}")
            all_passed = False
    
    # Restore original method
    manager.run_command = original_run_command
    
    print("\n" + "=" * 50)
    if all_passed:
        print("✓ All metric calculation tests PASSED")
        return True
    else:
        print("✗ Some metric calculation tests FAILED")
        return False


if __name__ == "__main__":
    success = test_metric_calculation()
    sys.exit(0 if success else 1)