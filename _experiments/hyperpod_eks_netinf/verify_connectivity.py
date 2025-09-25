#!/usr/bin/env python3
"""
Network Interface Connectivity Verifier

This script verifies internet connectivity for network interfaces that have been
moved and configured by the HyperPod EKS Network Interface Manager.
"""

import subprocess
import socket
import time
import sys
import argparse
from typing import List, Dict, Optional, Tuple
import json


class Colors:
    """ANSI color codes for terminal output"""
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    MAGENTA = '\033[95m'
    CYAN = '\033[96m'
    WHITE = '\033[97m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
    RESET = '\033[0m'
    
    @staticmethod
    def is_tty():
        """Check if output is to a terminal (supports colors)"""
        return sys.stdout.isatty()
    
    @staticmethod
    def colorize(text: str, color: str) -> str:
        """Apply color to text if terminal supports it"""
        if Colors.is_tty():
            return f"{color}{text}{Colors.RESET}"
        return text
    
    @staticmethod
    def error(text: str) -> str:
        """Red text for errors"""
        return Colors.colorize(text, Colors.RED)
    
    @staticmethod
    def success(text: str) -> str:
        """Green text for success"""
        return Colors.colorize(text, Colors.GREEN)
    
    @staticmethod
    def warning(text: str) -> str:
        """Yellow text for warnings"""
        return Colors.colorize(text, Colors.YELLOW)
    
    @staticmethod
    def info(text: str) -> str:
        """Blue text for info"""
        return Colors.colorize(text, Colors.BLUE)
    
    @staticmethod
    def bold(text: str) -> str:
        """Bold text"""
        return Colors.colorize(text, Colors.BOLD)


class ConnectivityVerifier:
    def __init__(self, interface_name: Optional[str] = None, verbose: bool = False):
        self.interface_name = interface_name
        self.verbose = verbose
        self.test_hosts = [
            "8.8.8.8",          # Google DNS
            "1.1.1.1",          # Cloudflare DNS
            "amazon.com",       # Amazon
            "google.com",       # Google
            "github.com"        # GitHub
        ]
        self.test_ports = [80, 443, 53]  # HTTP, HTTPS, DNS

    def log(self, message: str, level: str = "INFO"):
        """Log message with timestamp and color coding"""
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        if self.verbose or level in ["ERROR", "SUCCESS"]:
            # Apply color coding based on level
            if level == "ERROR":
                colored_message = Colors.error(message)
                colored_level = Colors.error(level)
            elif level == "SUCCESS":
                colored_message = Colors.success(message)
                colored_level = Colors.success(level)
            elif level == "WARNING":
                colored_message = Colors.warning(message)
                colored_level = Colors.warning(level)
            elif level == "DEBUG":
                colored_message = Colors.info(message)
                colored_level = Colors.info(level)
            else:
                colored_message = message
                colored_level = level
            
            print(f"[{timestamp}] {colored_level}: {colored_message}")

    def run_command(self, command: str, capture_output: bool = True, timeout: int = 10) -> Tuple[int, str, str]:
        """Execute a shell command and return exit code, stdout, stderr"""
        try:
            self.log(f"Executing: {command}", "DEBUG")
            result = subprocess.run(
                command, 
                shell=True, 
                capture_output=capture_output, 
                text=True,
                timeout=timeout
            )
            return result.returncode, result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            return 1, "", f"Command timed out after {timeout} seconds"
        except Exception as e:
            return 1, "", str(e)

    def get_interface_info(self) -> Dict[str, List[Dict]]:
        """Get information about all network interfaces"""
        self.log("Getting network interface information...")
        
        # Get interface list
        exit_code, stdout, stderr = self.run_command("ip -j addr show")
        if exit_code != 0:
            self.log(f"Error getting interface info: {stderr}", "ERROR")
            return {}
        
        try:
            interfaces = json.loads(stdout)
            return {"interfaces": interfaces}
        except json.JSONDecodeError:
            # Fallback to text parsing
            return self.parse_ip_addr_text(stdout)

    def parse_ip_addr_text(self, output: str) -> Dict[str, List[Dict]]:
        """Parse text output from ip addr command"""
        interfaces = []
        current_interface = None
        
        for line in output.split('\n'):
            line = line.strip()
            if not line:
                continue
                
            # Interface line: "2: eth0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 9000"
            if line[0].isdigit() and ':' in line:
                if current_interface:
                    interfaces.append(current_interface)
                
                parts = line.split(':')
                if len(parts) >= 2:
                    interface_name = parts[1].strip()
                    current_interface = {
                        'ifname': interface_name,
                        'flags': [],
                        'addr_info': []
                    }
                    
                    # Extract flags
                    if '<' in line and '>' in line:
                        flags_str = line[line.find('<')+1:line.find('>')]
                        current_interface['flags'] = flags_str.split(',')
            
            # IP address line: "inet 10.1.45.123/16 brd 10.1.255.255 scope global eth0"
            elif 'inet ' in line and current_interface:
                parts = line.split()
                for i, part in enumerate(parts):
                    if part == 'inet' and i + 1 < len(parts):
                        ip_with_prefix = parts[i + 1]
                        current_interface['addr_info'].append({
                            'family': 'inet',
                            'local': ip_with_prefix.split('/')[0],
                            'prefixlen': int(ip_with_prefix.split('/')[1]) if '/' in ip_with_prefix else 32
                        })
                        break
        
        if current_interface:
            interfaces.append(current_interface)
        
        return {"interfaces": interfaces}

    def find_target_interface(self, interfaces_data: Dict) -> Optional[Dict]:
        """Find the target interface to test"""
        interfaces = interfaces_data.get("interfaces", [])
        
        if self.interface_name:
            # Look for specific interface
            for interface in interfaces:
                if interface.get('ifname') == self.interface_name:
                    return interface
            self.log(f"Interface {self.interface_name} not found", "ERROR")
            return None
        else:
            # Look for recently configured interfaces (non-loopback, has IP, is UP)
            candidates = []
            for interface in interfaces:
                name = interface.get('ifname', '')
                flags = interface.get('flags', [])
                addr_info = interface.get('addr_info', [])
                
                # Skip loopback and interfaces without IP
                if name == 'lo' or not addr_info:
                    continue
                
                # Check if interface is UP and has IPv4 address
                is_up = 'UP' in flags
                has_ipv4 = any(addr.get('family') == 'inet' for addr in addr_info)
                
                if is_up and has_ipv4:
                    # Prefer interfaces with 10.1.x.x addresses (typical for moved interfaces)
                    for addr in addr_info:
                        if addr.get('family') == 'inet':
                            ip = addr.get('local', '')
                            if ip.startswith('10.1.'):
                                candidates.insert(0, interface)  # Prioritize
                                break
                    else:
                        candidates.append(interface)
            
            if candidates:
                return candidates[0]
            
        return None

    def ping_test(self, interface: Dict, host: str, count: int = 3) -> Dict[str, any]:
        """Test ping connectivity through specific interface"""
        interface_name = interface.get('ifname')
        self.log(f"Testing ping to {host} via {interface_name}...")
        
        # Use ping with specific interface
        command = f"ping -I {interface_name} -c {count} -W 5 {host}"
        exit_code, stdout, stderr = self.run_command(command, timeout=30)
        
        success = exit_code == 0
        
        # Parse ping statistics
        packet_loss = 100
        avg_time = None
        
        if success and stdout:
            # Extract packet loss percentage
            for line in stdout.split('\n'):
                if '% packet loss' in line:
                    try:
                        packet_loss = float(line.split('%')[0].split()[-1])
                    except (ValueError, IndexError):
                        pass
                
                # Extract average time
                if 'avg' in line and 'ms' in line:
                    try:
                        # Format: "rtt min/avg/max/mdev = 1.234/5.678/9.012/1.345 ms"
                        times = line.split('=')[1].strip().split()[0]
                        avg_time = float(times.split('/')[1])
                    except (ValueError, IndexError):
                        pass
        
        result = {
            'host': host,
            'interface': interface_name,
            'success': success,
            'packet_loss': packet_loss,
            'avg_time_ms': avg_time,
            'error': stderr if not success else None
        }
        
        if success:
            self.log(f"✓ Ping to {host}: {packet_loss}% loss, avg {avg_time}ms", "SUCCESS")
        else:
            self.log(f"✗ Ping to {host} failed: {stderr}", "ERROR")
        
        return result

    def tcp_connect_test(self, interface: Dict, host: str, port: int, timeout: int = 5) -> Dict[str, any]:
        """Test TCP connectivity to specific host:port through interface"""
        interface_name = interface.get('ifname')
        
        # Get interface IP for display purposes
        interface_ip = None
        for addr in interface.get('addr_info', []):
            if addr.get('family') == 'inet':
                interface_ip = addr.get('local')
                break
        
        if not interface_ip:
            return {
                'host': host,
                'port': port,
                'interface': interface_name,
                'success': False,
                'error': 'No IPv4 address found on interface'
            }
        
        self.log(f"Testing TCP connection to {host}:{port} via {interface_name} ({interface_ip})...")
        
        try:
            # Create socket and bind to interface using SO_BINDTODEVICE
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            
            # Use SO_BINDTODEVICE to bind to specific interface (more reliable than IP binding)
            try:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_BINDTODEVICE, interface_name.encode())
            except PermissionError:
                # Fall back to IP binding if SO_BINDTODEVICE requires root
                self.log(f"SO_BINDTODEVICE requires root, falling back to IP binding", "DEBUG")
                sock.bind((interface_ip, 0))
            except OSError as e:
                # If SO_BINDTODEVICE fails, try IP binding
                self.log(f"SO_BINDTODEVICE failed ({e}), falling back to IP binding", "DEBUG")
                sock.bind((interface_ip, 0))
            
            start_time = time.time()
            result = sock.connect_ex((host, port))
            connect_time = (time.time() - start_time) * 1000  # Convert to ms
            
            sock.close()
            
            success = result == 0
            
            if success:
                self.log(f"✓ TCP {host}:{port}: Connected in {connect_time:.1f}ms", "SUCCESS")
            else:
                # Provide more detailed error information
                error_msg = self._get_socket_error_message(result)
                self.log(f"✗ TCP {host}:{port}: Connection failed - {error_msg}", "ERROR")
            
            return {
                'host': host,
                'port': port,
                'interface': interface_name,
                'success': success,
                'connect_time_ms': connect_time if success else None,
                'error': f"Connection error {result}: {self._get_socket_error_message(result)}" if not success else None
            }
            
        except Exception as e:
            self.log(f"✗ TCP {host}:{port}: Exception - {str(e)}", "ERROR")
            return {
                'host': host,
                'port': port,
                'interface': interface_name,
                'success': False,
                'error': str(e)
            }

    def _get_socket_error_message(self, error_code: int) -> str:
        """Get human-readable error message for socket error codes"""
        error_messages = {
            0: "Success",
            11: "Resource temporarily unavailable (EAGAIN/EWOULDBLOCK)",
            101: "Network unreachable",
            110: "Connection timed out",
            111: "Connection refused",
            113: "No route to host",
            115: "Operation now in progress"
        }
        return error_messages.get(error_code, f"Unknown error {error_code}")

    def dns_resolution_test(self, hostname: str) -> Dict[str, any]:
        """Test DNS resolution"""
        self.log(f"Testing DNS resolution for {hostname}...")
        
        try:
            start_time = time.time()
            ip_addresses = socket.gethostbyname_ex(hostname)[2]
            resolution_time = (time.time() - start_time) * 1000
            
            self.log(f"✓ DNS {hostname}: Resolved to {ip_addresses} in {resolution_time:.1f}ms", "SUCCESS")
            
            return {
                'hostname': hostname,
                'success': True,
                'ip_addresses': ip_addresses,
                'resolution_time_ms': resolution_time
            }
            
        except Exception as e:
            self.log(f"✗ DNS {hostname}: Resolution failed - {str(e)}", "ERROR")
            return {
                'hostname': hostname,
                'success': False,
                'error': str(e)
            }

    def http_test(self, interface: Dict, url: str, timeout: int = 10) -> Dict[str, any]:
        """Test HTTP connectivity using curl through specific interface"""
        interface_name = interface.get('ifname')
        self.log(f"Testing HTTP request to {url} via {interface_name}...")
        
        # Use curl with interface binding
        command = f"curl --interface {interface_name} --connect-timeout {timeout} --max-time {timeout} -s -o /dev/null -w '%{{http_code}},%{{time_total}}' {url}"
        exit_code, stdout, stderr = self.run_command(command, timeout=timeout + 5)
        
        if exit_code == 0 and stdout:
            try:
                parts = stdout.strip().split(',')
                http_code = int(parts[0])
                total_time = float(parts[1]) * 1000  # Convert to ms
                
                success = 200 <= http_code < 400
                
                if success:
                    self.log(f"✓ HTTP {url}: {http_code} in {total_time:.1f}ms", "SUCCESS")
                else:
                    self.log(f"✗ HTTP {url}: {http_code} in {total_time:.1f}ms", "ERROR")
                
                return {
                    'url': url,
                    'interface': interface_name,
                    'success': success,
                    'http_code': http_code,
                    'total_time_ms': total_time
                }
                
            except (ValueError, IndexError):
                pass
        
        self.log(f"✗ HTTP {url}: Request failed - {stderr}", "ERROR")
        return {
            'url': url,
            'interface': interface_name,
            'success': False,
            'error': stderr
        }

    def run_comprehensive_test(self) -> Dict[str, any]:
        """Run comprehensive connectivity tests"""
        print("HyperPod EKS Network Interface Connectivity Verifier")
        print("=" * 60)
        
        # Get interface information
        interfaces_data = self.get_interface_info()
        if not interfaces_data:
            return {'success': False, 'error': 'Failed to get interface information'}
        
        # Find target interface
        target_interface = self.find_target_interface(interfaces_data)
        if not target_interface:
            return {'success': False, 'error': 'No suitable interface found for testing'}
        
        interface_name = target_interface.get('ifname')
        print(f"\nTesting connectivity for interface: {interface_name}")
        
        # Get interface IP
        interface_ip = None
        for addr in target_interface.get('addr_info', []):
            if addr.get('family') == 'inet':
                interface_ip = addr.get('local')
                break
        
        print(f"Interface IP: {interface_ip}")
        print("-" * 60)
        
        results = {
            'interface': interface_name,
            'interface_ip': interface_ip,
            'timestamp': time.strftime("%Y-%m-%d %H:%M:%S"),
            'tests': {
                'ping': [],
                'tcp': [],
                'dns': [],
                'http': []
            },
            'summary': {
                'total_tests': 0,
                'passed_tests': 0,
                'failed_tests': 0
            }
        }
        
        # DNS Resolution Tests
        print("\n1. DNS Resolution Tests")
        print("-" * 30)
        for host in ['google.com', 'amazon.com', 'github.com']:
            dns_result = self.dns_resolution_test(host)
            results['tests']['dns'].append(dns_result)
            results['summary']['total_tests'] += 1
            if dns_result['success']:
                results['summary']['passed_tests'] += 1
            else:
                results['summary']['failed_tests'] += 1
        
        # Ping Tests
        print("\n2. Ping Connectivity Tests")
        print("-" * 30)
        for host in self.test_hosts:
            ping_result = self.ping_test(target_interface, host)
            results['tests']['ping'].append(ping_result)
            results['summary']['total_tests'] += 1
            if ping_result['success']:
                results['summary']['passed_tests'] += 1
            else:
                results['summary']['failed_tests'] += 1
        
        # TCP Connection Tests
        print("\n3. TCP Connection Tests")
        print("-" * 30)
        tcp_hosts = ['8.8.8.8', 'google.com', 'amazon.com']
        for host in tcp_hosts:
            for port in self.test_ports:
                tcp_result = self.tcp_connect_test(target_interface, host, port)
                results['tests']['tcp'].append(tcp_result)
                results['summary']['total_tests'] += 1
                if tcp_result['success']:
                    results['summary']['passed_tests'] += 1
                else:
                    results['summary']['failed_tests'] += 1
        
        # HTTP Tests
        print("\n4. HTTP Connectivity Tests")
        print("-" * 30)
        http_urls = ['http://google.com', 'https://amazon.com', 'https://github.com']
        for url in http_urls:
            http_result = self.http_test(target_interface, url)
            results['tests']['http'].append(http_result)
            results['summary']['total_tests'] += 1
            if http_result['success']:
                results['summary']['passed_tests'] += 1
            else:
                results['summary']['failed_tests'] += 1
        
        # Calculate success rate
        total = results['summary']['total_tests']
        passed = results['summary']['passed_tests']
        success_rate = (passed / total * 100) if total > 0 else 0
        
        results['summary']['success_rate'] = success_rate
        results['success'] = success_rate >= 70  # Consider 70% success rate as overall success
        
        # Print summary
        print("\n" + "=" * 60)
        print("CONNECTIVITY TEST SUMMARY")
        print("=" * 60)
        print(f"Interface: {interface_name} ({interface_ip})")
        print(f"Total Tests: {total}")
        print(f"Passed: {passed}")
        print(f"Failed: {results['summary']['failed_tests']}")
        print(f"Success Rate: {success_rate:.1f}%")
        print(f"Overall Result: {'✓ PASS' if results['success'] else '✗ FAIL'}")
        print("=" * 60)
        
        return results

    def save_results(self, results: Dict, filename: str = None):
        """Save test results to JSON file"""
        if not filename:
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            interface = results.get('interface', 'unknown')
            filename = f"connectivity_test_{interface}_{timestamp}.json"
        
        try:
            with open(filename, 'w') as f:
                json.dump(results, f, indent=2)
            self.log(f"Results saved to {filename}", "SUCCESS")
        except Exception as e:
            self.log(f"Failed to save results: {e}", "ERROR")


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description='Verify network interface connectivity')
    parser.add_argument('-i', '--interface', help='Specific interface to test (auto-detect if not specified)')
    parser.add_argument('-v', '--verbose', action='store_true', help='Enable verbose logging')
    parser.add_argument('-o', '--output', help='Output file for results (JSON format)')
    parser.add_argument('--save-results', action='store_true', help='Save results to timestamped JSON file')
    
    args = parser.parse_args()
    
    try:
        verifier = ConnectivityVerifier(
            interface_name=args.interface,
            verbose=args.verbose
        )
        
        results = verifier.run_comprehensive_test()
        
        # Save results if requested
        if args.save_results or args.output:
            verifier.save_results(results, args.output)
        
        # Exit with appropriate code
        sys.exit(0 if results.get('success', False) else 1)
        
    except KeyboardInterrupt:
        print("\nOperation cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()