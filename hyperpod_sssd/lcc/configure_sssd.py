import sys
import os
import time
import subprocess
import tempfile
import socket
import re

import pexpect.popen_spawn

# ---

# Configurations

ec2_test_env = True

ad_domain = "cluster-test3.amazonaws.com"

# If this script is executed by root already, this variable can be empty
sudo_command = ["sudo","-E"]
#sudo_command = []

packages_to_install = [
    "sssd",
    "ldap-utils",
    "sssd-tools",
    "sssd-krb5",
    "krb5-user",
    "realmd",
    "adcli",
]

netplan_filename_for_custom_dns = "/etc/netplan/99-custom-dns.yaml"

if ec2_test_env:
    network_interface_name = "eth0"
else:
    network_interface_name = "ens6"

dns_server_addresses = [ 
    #"10.3.73.85", "10.2.82.19" # for cluster-test.amazonaws.com
    "10.3.24.253", "10.2.5.177" # for cluster-test3.amazonaws.com
]

sshd_config_filename = "/etc/ssh/sshd_config"

sssd_config_filename = "/etc/sssd/sssd.conf"

krb5_config_filename = "/etc/krb5.conf"

ad_admin_password = "placeholder" # FIXME : read from Secrets Manager?

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

        d = netplan_custom_dns_yaml.strip()
        print(d)

        with open(tmp_yaml_filename,"w") as fd:
            fd.write(d)

        subprocess.run( [ *sudo_command, "chmod", "644", tmp_yaml_filename ] )
        subprocess.run( [ *sudo_command, "chown", "root:root", tmp_yaml_filename ] )
        subprocess.run( [ *sudo_command, "cp", tmp_yaml_filename, netplan_filename_for_custom_dns ] )

    print("---")
    print("Applying netplan change (warning about ens5 can be ignored)")
    subprocess.run( [ *sudo_command, "netplan", "apply" ] )

    # It takes some time until when host name can be resolved
    time.sleep(10)

    print("---")
    print("Confirming AD domain is reachable")
    max_retries = 10
    for i in range(max_retries):
        try:
            print(f"Attempt {i+1} / {max_retries}")
            address_info = socket.getaddrinfo(ad_domain,0,0,0,0)
            break
        except socket.gaierror as e:
            print(e)
            time.sleep(10)
    else:
        assert False, f"{ad_domain} cannot be resolved"
    print(address_info)


def enable_password_authentication():

    print("---")
    print(f"Enabling password authentication in {sshd_config_filename}")

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_sshd_config_filename = os.path.join(tmp_dir,"sshd_config")

        with open(sshd_config_filename) as fd_src:
            d = fd_src.read()

        d = re.sub( r"PasswordAuthentication[ \t]+no", "PasswordAuthentication yes", d )
        print(d)

        with open(tmp_sshd_config_filename,"w") as fd_dst:
            fd_dst.write(d)

        subprocess.run( [ *sudo_command, "chmod", "644", tmp_sshd_config_filename ] )
        subprocess.run( [ *sudo_command, "chown", "root:root", tmp_sshd_config_filename ] )
        subprocess.run( [ *sudo_command, "cp", tmp_sshd_config_filename, sshd_config_filename ] )


def enable_automatic_homedir_creation():

    print("---")
    print(f"Enabling automatic home directory creation")

    subprocess.run( [ *sudo_command, "pam-auth-update", "--enable", "mkhomedir" ] )


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


def realm_join():

    print("---")
    print("Joining AD")

    max_retries = 10
    for i in range(max_retries):

        print(f"Attempt {i+1} / {max_retries}")

        p = pexpect.popen_spawn.PopenSpawn([*sudo_command, "realm", "join", "-U", "Admin", ad_domain])
        p.expect(":", timeout=30)
        print(p.before.decode("utf-8") + p.after.decode("utf-8"), end="")
        p.sendline(ad_admin_password)
        p.expect(pexpect.EOF, timeout=30)
        print(p.before.decode("utf-8"), end="")
        result = p.wait()
        if result==0: break

        time.sleep(10)
    else:
        assert result==0, f"Joining AD domain failed with return code {result}"


sssd_conf_with_join = f"""
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

sssd_conf = f"""
[domain/{ad_domain}]
id_provider = ldap
auth_provider = krb5
cache_credentials = True
ldap_uri = ldap://{ad_domain}
ldap_search_base = dc=cluster-test3,dc=amazonaws,dc=com
ldap_schema = AD
ldap_default_bind_dn = cn=Admin,ou=Users,ou=cluster-test3,dc=cluster-test3,dc=amazonaws,dc=com
ldap_default_authtok = {ad_admin_password}
ldap_tls_reqcert = never
ldap_id_mapping = True
ldap_referrals = True
#ldap_user_extra_attrs = altSecurityIdentities:altSecurityIdentities
ldap_use_tokengroups = True
krb5_realm = {ad_domain.upper()}
krb5_canonicalize = True
enumerate = False
fallback_homedir = /home/%u@%d
default_shell = /bin/bash
use_fully_qualified_names = True
#debug_level = 6

[sssd]
domains = {ad_domain}
config_file_version = 2
services = nss, pam
#debug_level = 6

[pam]
offline_credentials_expiration = 14
#debug_level = 6

[nss]
filter_users = nobody,root
filter_groups = nobody,root
#debug_level = 6
"""

def configure_sssd():

    print("---")
    print("Configuring SSSD")

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_sssd_config_filename = os.path.join(tmp_dir, os.path.basename(sssd_config_filename))

        d = sssd_conf.strip()
        print(d)

        with open(tmp_sssd_config_filename,"w") as fd:
            fd.write(d)

        subprocess.run( [ *sudo_command, "chmod", "600", tmp_sssd_config_filename ] )
        subprocess.run( [ *sudo_command, "chown", "root:root", tmp_sssd_config_filename ] )
        subprocess.run( [ *sudo_command, "cp", tmp_sssd_config_filename, sssd_config_filename ] )


def restart_services():

    print("---")
    print("Restarting services")

    subprocess.run( [ *sudo_command, "systemctl", "restart", "ssh.service" ] )
    subprocess.run( [ *sudo_command, "systemctl", "restart", "sssd.service" ] )


print("Starting SSSD configuration steps")

#install_apt_packages()
#configure_custom_dns()
#enable_password_authentication()
#enable_automatic_homedir_creation()
#configure_krb5()
configure_sssd()
restart_services()

print("---")
print("Finished SSSD configuration steps")
