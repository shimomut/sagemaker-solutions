import os
import subprocess
import tempfile
import socket
import re

import pexpect.popen_spawn

# ---

# Configurations

ad_domain = "cluster-test.amazonaws.com"

# If this script is executed by root already, this variable can be empty
sudo_command = ["sudo","-E"]
#sudo_command = []

packages_to_install = [
    "ldap-utils", "realmd", "sssd-tools", "adcli", "sssd", "libnss-sss", "libpam-sss",
    "sssd-ldap",
    "sssd-krb5", "krb5-user" # not needed ?
]

netplan_filename_for_custom_dns = "/etc/netplan/99-custom-dns.yaml"
network_interface_name = "ens6"
dns_server_addresses = [ "10.3.73.85", "10.2.82.19" ]

sshd_config_filename = "/etc/ssh/sshd_config"

sssd_config_filename = "/etc/sssd/sssd.conf"

krb5_config_filename = "/etc/krb5.conf"

ad_admin_password = "xyz" # FIXME : read from Secrets Manager?

# ---

def install_apt_packages():

    print("---")
    print("Updating apt package index")
    subprocess.run( [ *sudo_command, "apt", "update" ] )

    print("---")
    print("Installing packages - ", packages_to_install)
    subprocess.run( [ *sudo_command, "DEBIAN_FRONTEND=noninteractive", "apt", "install", "-y", *packages_to_install ] )


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
        tmp_yaml_filename = os.path.join(tmp_dir, os.path.basename(netplan_filename_for_custom_dns))
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
    address = socket.gethostbyname(ad_domain)
    print( f"{ad_domain} -> {address}" )


def realm_join():
    # FIXME : should print stdout/stderr
    p = pexpect.popen_spawn.PopenSpawn([*sudo_command, "realm", "join", "-U", "Admin", ad_domain])
    p.expect(":")
    p.sendline(ad_admin_password)
    result = p.wait()
    print(result)
    assert result==0, "realm join failed."


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


def enable_automatic_homedir_creation():

    print("---")
    print(f"Enabling automatic home directory creation")

    subprocess.run( [ *sudo_command, "pam-auth-update", "--enable", "mkhomedir" ] )


sssd_conf = f"""
[sssd]
domains = {ad_domain}
config_file_version = 2
services = nss, pam

[domain/{ad_domain}]
default_shell = /bin/bash
krb5_store_password_if_offline = True
cache_credentials = True
krb5_realm = {ad_domain.upper()}
realmd_tags = manages-system joined-with-adcli
id_provider = ad
fallback_homedir = /home/%u@%d
ad_domain = {ad_domain}
use_fully_qualified_names = True
ldap_id_mapping = True
access_provider = ad
"""

# FIXME : not needed if what realm join generated is sufficient
def configure_sssd():

    print("---")
    print("Configuring SSSD")

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_sssd_config_filename = os.path.join(tmp_dir, os.path.basename(sssd_config_filename))
        with open(tmp_sssd_config_filename,"w") as fd:
            fd.write( sssd_conf.strip() )

        subprocess.run( [ *sudo_command, "chmod", "600", tmp_sssd_config_filename ] )
        subprocess.run( [ *sudo_command, "chown", "root:root", tmp_sssd_config_filename ] )
        subprocess.run( [ *sudo_command, "cp", tmp_sssd_config_filename, sssd_config_filename ] )


# FIXME : not needed ?
def configure_krb5():

    print("---")
    print("Configuring Kerberos")

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_config_filename = os.path.join(tmp_dir,os.path.basename(krb5_config_filename))

        with open(krb5_config_filename) as fd_src:
            d = fd_src.read()

        d = re.sub( r"default_realm = .*", f"default_realm = {ad_domain.upper()}", d )
        print(d)

        with open(tmp_config_filename,"w") as fd_dst:
            fd_dst.write(d)

        subprocess.run( [ *sudo_command, "chmod", "644", tmp_config_filename ] )
        subprocess.run( [ *sudo_command, "chown", "root:root", tmp_config_filename ] )
        subprocess.run( [ *sudo_command, "cp", tmp_config_filename, krb5_config_filename ] )


def restart_services():

    print("---")
    print("Restarting services")

    subprocess.run( [ *sudo_command, "systemctl", "restart", "ssh.service" ] )
    subprocess.run( [ *sudo_command, "systemctl", "restart", "sssd.service" ] )


print("Starting SSSD configuration steps")

install_apt_packages()
configure_custom_dns()
realm_join()
enable_password_authentication()
enable_automatic_homedir_creation()
restart_services()

if 0:
    configure_sssd()
    configure_krb5()

print("---")
print("Finished SSSD configuration steps")
