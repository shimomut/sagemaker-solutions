import os
import subprocess
import tempfile
import socket
import re

# ---

# Configurations

ad_domain = "cluster-test.amazonaws.com"

# If this script is executed by root already, this variable can be empty
sudo_command = ["sudo"]
#sudo_command = []

packages_to_install = [
    "ldap-utils", "realmd", "sssd-tools", "adcli", "sssd", "libnss-sss", "libpam-sss"
]

netplan_filename_for_custom_dns = "/etc/netplan/99-custom-dns.yaml"
network_interface_name = "ens6"
dns_server_addresses = [ "10.3.73.85", "10.2.82.19" ]

sshd_config_filename = "/etc/ssh/sshd_config"

exit_on_failure = True

# ---

def on_failure(message):
    print(message)
    if exit_on_failure:
        sys.exit(1)

def install_apt_packages():

    print("---")
    print("Updating apt package index")
    subprocess.run( [ *sudo_command, "apt", "update" ] )

    print("---")
    print("Installing packages - ", packages_to_install)
    subprocess.run( [ *sudo_command, "apt", "install", "-y", *packages_to_install ] )


netplan_custom_dns_yaml = f"""
network:
    version: 2
    ethernets:
        {network_interface_name}:
            nameservers:
                addresses: [{", ".join(dns_server_addresses)}]
            dhcp4-overrides:
                use-dns: false
"""

def configure_custom_dns():

    print("---")
    print("Creating netplan config file for custom DNS server addresses")

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_yaml_filename = os.path.join(tmp_dir,"99-custom-dns.yaml")
        with open(tmp_yaml_filename,"w") as fd:
            fd.write( netplan_custom_dns_yaml.strip() )

        subprocess.run( [ *sudo_command, "chmod", "644", tmp_yaml_filename ] )
        subprocess.run( [ *sudo_command, "chown", "root:root", tmp_yaml_filename ] )
        subprocess.run( [ *sudo_command, "cp", tmp_yaml_filename, netplan_filename_for_custom_dns ] )

    print("---")
    print("Applying netplan change (warning about ens6 can be ignored)")
    subprocess.run( [ *sudo_command, "netplan", "apply" ] )

    print("---")
    print("Confirming AD domain is reachable")
    try:
        address = socket.gethostbyname(ad_domain)
        print( f"{ad_domain} -> {address}" )
    except gaierror:
        on_failure(f"Warning : {ad_domain} cannot be resolved")


def enable_password_authentication():

    print("---")
    print(f"Enabling password authentication in {sshd_config_filename}")

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_sshd_config_filename = os.path.join(tmp_dir,"sshd_config")

        with open(sshd_config_filename) as fd_src:
            d = fd_src.read()

        d = re.sub( r"PasswordAuthentication[ \t]+no", "PasswordAuthentication yes", d )

        with open(tmp_sshd_config_filename,"w") as fd_dst:
            fd_dst.write(d)

        subprocess.run( [ *sudo_command, "chmod", "644", tmp_sshd_config_filename ] )
        subprocess.run( [ *sudo_command, "chown", "root:root", tmp_sshd_config_filename ] )
        subprocess.run( [ *sudo_command, "cp", tmp_sshd_config_filename, sshd_config_filename ] )



print("Starting SSSD configuration steps")

#install_apt_packages()
#configure_custom_dns()
enable_password_authentication()

print("---")
print("Finished SSSD configuration steps")
