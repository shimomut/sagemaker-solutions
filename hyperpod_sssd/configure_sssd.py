import os
import subprocess
import tempfile

# ---

# If this script is executed by root already, this variable can be empty
sudo_command = ["sudo"]
#sudo_command = []

packages_to_install = [
    "ldap-utils", "realmd", "sssd-tools", "adcli", "sssd", "libnss-sss", "libpam-sss"
]

netplan_filename_for_custom_dns = "/etc/netplan/99-custom-dns.yaml"
network_interface_name = "ens6"
dns_server_addresses = [ "10.3.73.85", "10.2.82.19" ]


# ---

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

# ---

def install_apt_packages():

    print("Updating apt package index")
    subprocess.run( [ *sudo_command, "apt", "update" ] )

    print("---")
    print("Installing packages - ", packages_to_install)
    subprocess.run( [ *sudo_command, "apt", "install", "-y", *packages_to_install ] )


def configure_custom_dns():

    print("Creating netplan config file for custom DNS server addresses")

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_yaml_filename = os.path.join(tmp_dir,"99-custom-dns.yaml")
        with open(tmp_yaml_filename,"w") as fd:
            fd.write( netplan_custom_dns_yaml.strip() )

        subprocess.run( [ *sudo_command, "chmod", "644", tmp_yaml_filename ] )
        subprocess.run( [ *sudo_command, "chown", "root:root", tmp_yaml_filename ] )
        subprocess.run( [ *sudo_command, "mv", tmp_yaml_filename, netplan_filename_for_custom_dns ] )


print("Starting SSSD configuration steps")

install_apt_packages()
configure_custom_dns()

print("---")
print("Finished SSSD configuration steps")
