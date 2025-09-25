#!/usr/bin/env python3
"""
HyperPod EKS Network Interface Manager

This script manages network interfaces between namespaces on AL2023,
specifically moving interfaces from sagemaker_agent_namespace to default
namespace and configuring them properly.
"""

import subprocess
import json
import re
import sys
import boto3
from typing import List, Dict, Optional, Tuple


class NetworkInterfaceManager:
    def __init__(self):
        self.ec2_client = boto3.client('ec2')
        self.default_interfaces = []
        self.sagemaker_interfaces = []
        self.route_table = []

    def run_command(self, command: str, capture_output: bool = True) -> Tuple[int, str, str]:
        """Execute a shell command and return exit code, stdout, stderr"""
        try:
            result = subprocess.run(
                command, 
                shell=True, 
                capture_output=capture_output, 
                text=True,
                timeout=30
            )
            return result.returncode, result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            return 1, "", "Command timed out"
        except Exception as e:
            return 1, "", str(e)

    def parse_ip_link_output(self, output: str) -> List[Dict[str, str]]:
        """Parse 'ip link' command output and extract interface information"""
        interfaces = []
        lines = output.strip().split('\n')
        
        for line in lines:
            # Match lines like: "2: eth0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 9000 qdisc mq state UP mode DEFAULT group default qlen 1000"
            match = re.match(r'^\d+:\s+([^:]+):\s+<([^>]+)>.*state\s+(\w+)', line)
            if match:
                interface_name = match.group(1).strip()
                flags = match.group(2)
                state = match.group(3)
                
                # Extract MAC address from the next line if available
                mac_address = ""
                next_line_idx = lines.index(line) + 1
                if next_line_idx < len(lines):
                    mac_match = re.search(r'link/ether\s+([a-f0-9:]{17})', lines[next_line_idx])
                    if mac_match:
                        mac_address = mac_match.group(1)
                
                interfaces.append({
                    'name': interface_name,
                    'flags': flags,
                    'state': state,
                    'mac': mac_address
                })
        
        return interfaces

    def parse_ip_route_output(self, output: str) -> List[Dict[str, str]]:
        """Parse 'ip route' command output"""
        routes = []
        for line in output.strip().split('\n'):
            if line.strip():
                routes.append({'route': line.strip()})
        return routes

    def get_default_namespace_interfaces(self) -> bool:
        """Get network interfaces in default namespace"""
        print("Getting network interfaces in default namespace...")
        exit_code, stdout, stderr = self.run_command("sudo ip netns exec default ip link")
        
        if exit_code != 0:
            print(f"Error getting default namespace interfaces: {stderr}")
            return False
        
        self.default_interfaces = self.parse_ip_link_output(stdout)
        print(f"Found {len(self.default_interfaces)} interfaces in default namespace")
        return True

    def get_sagemaker_namespace_interfaces(self) -> bool:
        """Get network interfaces in sagemaker_agent_namespace"""
        print("Getting network interfaces in sagemaker_agent_namespace...")
        exit_code, stdout, stderr = self.run_command("sudo ip netns exec sagemaker_agent_namespace ip link")
        
        if exit_code != 0:
            print(f"Error getting sagemaker namespace interfaces: {stderr}")
            return False
        
        self.sagemaker_interfaces = self.parse_ip_link_output(stdout)
        print(f"Found {len(self.sagemaker_interfaces)} interfaces in sagemaker_agent_namespace")
        return True

    def get_route_table(self) -> bool:
        """Get current IP route table"""
        print("Getting current IP route table...")
        exit_code, stdout, stderr = self.run_command("ip route")
        
        if exit_code != 0:
            print(f"Error getting route table: {stderr}")
            return False
        
        self.route_table = self.parse_ip_route_output(stdout)
        print(f"Found {len(self.route_table)} routes in route table")
        return True

    def find_down_interface(self) -> Optional[Dict[str, str]]:
        """Find the first DOWN interface in sagemaker_agent_namespace"""
        for interface in self.sagemaker_interfaces:
            if interface['state'] == 'DOWN':
                return interface
        return None

    def get_eni_by_mac(self, mac_address: str) -> Optional[Dict]:
        """Get ENI details using MAC address"""
        try:
            response = self.ec2_client.describe_network_interfaces(
                Filters=[
                    {
                        'Name': 'mac-address',
                        'Values': [mac_address]
                    }
                ]
            )
            
            if response['NetworkInterfaces']:
                return response['NetworkInterfaces'][0]
            return None
        except Exception as e:
            print(f"Error getting ENI by MAC {mac_address}: {e}")
            return None

    def ask_user_confirmation(self, interface: Dict[str, str], eni_details: Dict) -> bool:
        """Ask user for confirmation before proceeding"""
        print("\n" + "="*60)
        print("NETWORK INTERFACE DETAILS")
        print("="*60)
        print(f"Interface Name: {interface['name']}")
        print(f"MAC Address: {interface['mac']}")
        print(f"Current State: {interface['state']}")
        print("\nENI Details:")
        print(f"  ENI ID: {eni_details.get('NetworkInterfaceId', 'N/A')}")
        print(f"  Private IP: {eni_details.get('PrivateIpAddress', 'N/A')}")
        print(f"  Subnet ID: {eni_details.get('SubnetId', 'N/A')}")
        print(f"  VPC ID: {eni_details.get('VpcId', 'N/A')}")
        print("="*60)
        
        while True:
            response = input("\nDo you want to proceed with moving this interface? (yes/no): ").lower().strip()
            if response in ['yes', 'y']:
                return True
            elif response in ['no', 'n']:
                return False
            else:
                print("Please answer 'yes' or 'no'")

    def move_interface_to_default(self, interface_name: str) -> bool:
        """Move interface from sagemaker_agent_namespace to default namespace"""
        print(f"Moving interface {interface_name} to default namespace...")
        command = f"sudo ip netns exec sagemaker_agent_namespace ip link set {interface_name} netns default"
        exit_code, stdout, stderr = self.run_command(command)
        
        if exit_code != 0:
            print(f"Error moving interface: {stderr}")
            return False
        
        print(f"Successfully moved {interface_name} to default namespace")
        return True

    def assign_ip_address(self, interface_name: str, ip_address: str) -> bool:
        """Assign IP address to the interface"""
        print(f"Assigning IP address {ip_address}/16 to {interface_name}...")
        command = f"sudo ip addr add {ip_address}/16 brd 10.1.255.255 dev {interface_name}"
        exit_code, stdout, stderr = self.run_command(command)
        
        if exit_code != 0:
            print(f"Error assigning IP address: {stderr}")
            return False
        
        print(f"Successfully assigned IP address to {interface_name}")
        return True

    def bring_interface_up(self, interface_name: str) -> bool:
        """Bring the network interface up"""
        print(f"Bringing interface {interface_name} up...")
        command = f"sudo ip link set {interface_name} up"
        exit_code, stdout, stderr = self.run_command(command)
        
        if exit_code != 0:
            print(f"Error bringing interface up: {stderr}")
            return False
        
        print(f"Successfully brought {interface_name} up")
        return True

    def add_default_route(self, interface_name: str) -> bool:
        """Add default route via the interface"""
        print(f"Adding default route via {interface_name}...")
        command = f"sudo ip route add default via 10.1.0.1 dev {interface_name} metric 400"
        exit_code, stdout, stderr = self.run_command(command)
        
        if exit_code != 0:
            print(f"Error adding default route: {stderr}")
            return False
        
        print(f"Successfully added default route via {interface_name}")
        return True

    def verify_configuration(self) -> bool:
        """Verify the final configuration"""
        print("\n" + "="*60)
        print("VERIFICATION - Final Configuration")
        print("="*60)
        
        # Check ip addr
        print("\n--- IP Addresses ---")
        exit_code, stdout, stderr = self.run_command("ip addr")
        if exit_code == 0:
            print(stdout)
        else:
            print(f"Error getting IP addresses: {stderr}")
        
        # Check ip link
        print("\n--- Network Interfaces ---")
        exit_code, stdout, stderr = self.run_command("ip link")
        if exit_code == 0:
            print(stdout)
        else:
            print(f"Error getting network interfaces: {stderr}")
        
        # Check ip route
        print("\n--- Routing Table ---")
        exit_code, stdout, stderr = self.run_command("ip route")
        if exit_code == 0:
            print(stdout)
        else:
            print(f"Error getting routing table: {stderr}")
        
        print("="*60)
        return True

    def run(self) -> bool:
        """Main execution flow"""
        print("HyperPod EKS Network Interface Manager")
        print("="*50)
        
        # Step 1: Get default namespace interfaces
        if not self.get_default_namespace_interfaces():
            return False
        
        # Step 2: Get sagemaker namespace interfaces
        if not self.get_sagemaker_namespace_interfaces():
            return False
        
        # Step 3: Get route table
        if not self.get_route_table():
            return False
        
        # Step 4: Find first DOWN interface in sagemaker namespace
        down_interface = self.find_down_interface()
        if not down_interface:
            print("No DOWN interfaces found in sagemaker_agent_namespace")
            return False
        
        print(f"Found DOWN interface: {down_interface['name']}")
        
        # Step 5: Get ENI details using MAC address
        if not down_interface['mac']:
            print("No MAC address found for the interface")
            return False
        
        eni_details = self.get_eni_by_mac(down_interface['mac'])
        if not eni_details:
            print(f"No ENI found for MAC address: {down_interface['mac']}")
            return False
        
        # Step 6: Ask for user confirmation
        if not self.ask_user_confirmation(down_interface, eni_details):
            print("Operation cancelled by user")
            return False
        
        # Step 7: Move interface to default namespace
        if not self.move_interface_to_default(down_interface['name']):
            return False
        
        # Step 8: Assign IP address
        private_ip = eni_details.get('PrivateIpAddress')
        if not private_ip:
            print("No private IP address found in ENI details")
            return False
        
        if not self.assign_ip_address(down_interface['name'], private_ip):
            return False
        
        # Step 9: Bring interface up
        if not self.bring_interface_up(down_interface['name']):
            return False
        
        # Step 10: Add default route
        if not self.add_default_route(down_interface['name']):
            return False
        
        # Step 11: Verify configuration
        self.verify_configuration()
        
        print("\nNetwork interface management completed successfully!")
        return True


def main():
    """Main entry point"""
    try:
        manager = NetworkInterfaceManager()
        success = manager.run()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\nOperation cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()