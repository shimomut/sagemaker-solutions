#!/usr/bin/env python3
"""
Diagnostic script to investigate TCP connection issues with specific interfaces
"""

import socket
import subprocess
import json
import sys
import time
from typing import Dict, List, Tuple


def run_command(command: str, timeout: int = 10) -> Tuple[int, str, str]:
    """Execute a shell command and return exit code, stdout, stderr"""
    try:
        result = subprocess.run(
            command, 
            shell=True, 
            capture_output=True, 
            text=True,
            timeout=timeout
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return 1, "", "Command timed out"
    except Exception as e:
        return 1, "", str(e)


def get_interface_info(interface_name: str = None) -> Dict:
    """Get detailed interface information"""
    print(f"=== Interface Information ===")
    
    # Get interface details using ip command
    if interface_name:
        cmd = f"ip -j addr show {interface_name}"
    else:
        cmd = "ip -j addr show"
    
    exit_code, stdout, stderr = run_command(cmd)
    
    if exit_code != 0:
        print(f"Error getting interface info: {stderr}")
        return {}
    
    try:
        interfaces = json.loads(stdout)
        for iface in interfaces:
            name = iface.get('ifname', 'unknown')
            if interface_name and name != interface_name:
                continue
                
            print(f"\nInterface: {name}")
            print(f"  State: {iface.get('operstate', 'unknown')}")
            print(f"  Flags: {iface.get('flags', [])}")
            
            addr_info = iface.get('addr_info', [])
            for addr in addr_info:
                if addr.get('family') == 'inet':
                    ip = addr.get('local')
                    prefix = addr.get('prefixlen')
                    print(f"  IPv4: {ip}/{prefix}")
                    
                    # Test if we can bind to this IP
                    test_bind_to_ip(ip, name)
        
        return {"interfaces": interfaces}
    except json.JSONDecodeError as e:
        print(f"Error parsing interface JSON: {e}")
        return {}


def test_bind_to_ip(ip_address: str, interface_name: str):
    """Test if we can bind a socket to the specific IP address"""
    print(f"    Testing socket bind to {ip_address}...")
    
    try:
        # Test TCP socket binding
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((ip_address, 0))  # Bind to any available port
        local_addr = sock.getsockname()
        sock.close()
        print(f"    ✓ TCP bind successful: {local_addr}")
        return True
    except Exception as e:
        print(f"    ✗ TCP bind failed: {e}")
        return False


def test_interface_routing(interface_name: str):
    """Test routing through specific interface"""
    print(f"\n=== Routing Information for {interface_name} ===")
    
    # Get routing table
    exit_code, stdout, stderr = run_command("ip route show")
    if exit_code == 0:
        print("Current routing table:")
        for line in stdout.strip().split('\n'):
            if interface_name in line:
                print(f"  → {line}")
    
    # Test if interface has a default route
    exit_code, stdout, stderr = run_command(f"ip route show dev {interface_name}")
    if exit_code == 0 and stdout.strip():
        print(f"\nRoutes via {interface_name}:")
        for line in stdout.strip().split('\n'):
            print(f"  → {line}")


def test_tcp_with_so_bindtodevice(interface_name: str, host: str, port: int):
    """Test TCP connection using SO_BINDTODEVICE socket option"""
    print(f"\n=== Testing SO_BINDTODEVICE for {interface_name} ===")
    
    try:
        # Create socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        
        # Try to bind to device (requires root privileges)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BINDTODEVICE, interface_name.encode())
            print(f"✓ SO_BINDTODEVICE set for {interface_name}")
        except PermissionError:
            print(f"✗ SO_BINDTODEVICE requires root privileges")
            sock.close()
            return False
        except Exception as e:
            print(f"✗ SO_BINDTODEVICE failed: {e}")
            sock.close()
            return False
        
        # Test connection
        start_time = time.time()
        result = sock.connect_ex((host, port))
        connect_time = (time.time() - start_time) * 1000
        
        sock.close()
        
        if result == 0:
            print(f"✓ TCP connection to {host}:{port} successful in {connect_time:.1f}ms")
            return True
        else:
            print(f"✗ TCP connection to {host}:{port} failed (error {result})")
            return False
            
    except Exception as e:
        print(f"✗ TCP test exception: {e}")
        return False


def test_tcp_with_ip_binding(interface_name: str, host: str, port: int):
    """Test TCP connection by binding to interface IP"""
    print(f"\n=== Testing IP binding for {interface_name} ===")
    
    # Get interface IP
    exit_code, stdout, stderr = run_command(f"ip -j addr show {interface_name}")
    if exit_code != 0:
        print(f"✗ Could not get interface IP: {stderr}")
        return False
    
    try:
        interfaces = json.loads(stdout)
        if not interfaces:
            print(f"✗ No interface data found")
            return False
        
        interface_ip = None
        for addr in interfaces[0].get('addr_info', []):
            if addr.get('family') == 'inet':
                interface_ip = addr.get('local')
                break
        
        if not interface_ip:
            print(f"✗ No IPv4 address found on {interface_name}")
            return False
        
        print(f"Interface IP: {interface_ip}")
        
        # Test TCP connection with IP binding
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        sock.bind((interface_ip, 0))
        
        start_time = time.time()
        result = sock.connect_ex((host, port))
        connect_time = (time.time() - start_time) * 1000
        
        sock.close()
        
        if result == 0:
            print(f"✓ TCP connection to {host}:{port} via {interface_ip} successful in {connect_time:.1f}ms")
            return True
        else:
            print(f"✗ TCP connection to {host}:{port} via {interface_ip} failed (error {result})")
            return False
            
    except Exception as e:
        print(f"✗ TCP test exception: {e}")
        return False


def test_curl_with_interface(interface_name: str, url: str):
    """Test HTTP connectivity using curl with interface binding"""
    print(f"\n=== Testing curl with interface {interface_name} ===")
    
    command = f"curl --interface {interface_name} --connect-timeout 5 --max-time 10 -s -o /dev/null -w '%{{http_code}},%{{time_total}}' {url}"
    exit_code, stdout, stderr = run_command(command, timeout=15)
    
    if exit_code == 0 and stdout:
        try:
            parts = stdout.strip().split(',')
            http_code = int(parts[0])
            total_time = float(parts[1]) * 1000
            
            if 200 <= http_code < 400:
                print(f"✓ HTTP {url}: {http_code} in {total_time:.1f}ms")
                return True
            else:
                print(f"✗ HTTP {url}: {http_code} in {total_time:.1f}ms")
                return False
        except (ValueError, IndexError):
            pass
    
    print(f"✗ HTTP {url}: Request failed - {stderr}")
    return False


def main():
    """Main diagnostic function"""
    if len(sys.argv) > 1:
        interface_name = sys.argv[1]
    else:
        interface_name = "enp75s0"  # Default to the problematic interface
    
    print(f"Diagnosing TCP connectivity issues for interface: {interface_name}")
    print("=" * 60)
    
    # Get interface information
    get_interface_info(interface_name)
    
    # Test routing
    test_interface_routing(interface_name)
    
    # Test different TCP connection methods
    test_hosts = [
        ("8.8.8.8", 53),
        ("google.com", 80),
        ("amazon.com", 443)
    ]
    
    for host, port in test_hosts:
        print(f"\n{'='*60}")
        print(f"Testing connectivity to {host}:{port}")
        print(f"{'='*60}")
        
        # Method 1: SO_BINDTODEVICE (requires root)
        test_tcp_with_so_bindtodevice(interface_name, host, port)
        
        # Method 2: IP binding
        test_tcp_with_ip_binding(interface_name, host, port)
    
    # Test HTTP with curl
    test_curl_with_interface(interface_name, "http://google.com")
    
    print(f"\n{'='*60}")
    print("Diagnostic complete")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()