import os
import subprocess
import tempfile
import re
import getpass

# ---------------------------------
# Configurations you need to modify

ec2_test_env = True

ad_domain = "default"

ldap_uri = "ldaps://ldap-lb-69fea12ccf01759e.elb.us-west-2.amazonaws.com"

packages_to_install = [
    "sssd",
    "ldap-utils",
    "sssd-tools",
]

packages_to_uninstall = [
    "ec2-instance-connect",
]

sshd_config_filename = "/etc/ssh/sshd_config"
sssd_config_filename = "/etc/sssd/sssd.conf"
cert_filename = "/etc/ldap/ldap-cert1.pem"

ldap_default_authtok_type = "obfuscated_password"
ldap_default_authtok = "placeholder"

assert ldap_default_authtok != "placeholder", "You need to configure ldap_default_authtok. You can use tools/obfuscate_password.py to get obfuscated password"

ssh_auth_method = "publickey" # "password" or "publickey"

assert ssh_auth_method in ["password", "publickey"]

# ---------------------------------
# Templates for configuration files

sssd_conf = f"""
[domain/{ad_domain}]
id_provider = ldap
cache_credentials = True
ldap_uri = {ldap_uri}
ldap_search_base = dc=cluster-test,dc=amazonaws,dc=com
ldap_schema = AD
ldap_default_bind_dn = cn=Admin,ou=Users,ou=cluster-test,dc=cluster-test,dc=amazonaws,dc=com
ldap_default_authtok_type = {ldap_default_authtok_type}
ldap_default_authtok = {ldap_default_authtok}
ldap_tls_cacert = {cert_filename}
ldap_tls_reqcert = hard
ldap_id_mapping = True
ldap_referrals = False
ldap_user_extra_attrs = altSecurityIdentities:altSecurityIdentities
ldap_user_ssh_public_key = altSecurityIdentities
ldap_use_tokengroups = True
enumerate = False
fallback_homedir = /home/%u
default_shell = /bin/bash
#use_fully_qualified_names = True
#debug_level = 6

[sssd]
config_file_version = 2
domains = {ad_domain}
services = nss, pam, ssh
#debug_level = 6

[pam]
offline_credentials_expiration = 14
#debug_level = 6

[nss]
filter_users = nobody,root
filter_groups = nobody,root
#debug_level = 6
"""

# ---

if getpass.getuser() == "root":
    sudo_command = []
else:
    sudo_command = ["sudo","-E"]

# ---

def install_apt_packages():

    print("---")
    print("Updating apt package index")
    subprocess.run( [ *sudo_command, "apt", "update" ] )

    print("---")
    print("Installing packages - ", packages_to_install)
    subprocess.run( [ *sudo_command, "DEBIAN_FRONTEND=noninteractive", "apt", "install", "-y", *packages_to_install ] )


def uninstall_apt_packages():

    print("---")
    print("Uninstalling packages - ", packages_to_uninstall)
    subprocess.run( [ *sudo_command, "apt", "remove", "-y", *packages_to_uninstall ] )


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


def configure_ssh_auth_method():

    print("---")
    print(f"Configuring SSH authentication method to {ssh_auth_method}")

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_sshd_config_filename = os.path.join(tmp_dir,"sshd_config")

        with open(sshd_config_filename) as fd_src:
            d = fd_src.read()

        if ssh_auth_method=="password":
            d = re.sub( r"[#\t ]*PasswordAuthentication[ \t]+.*$", "PasswordAuthentication yes", d, flags=re.MULTILINE )
        elif ssh_auth_method=="publickey":
            d = re.sub( r"[#\t ]*AuthorizedKeysCommand[ \t]+.*$", "AuthorizedKeysCommand /usr/bin/sss_ssh_authorizedkeys", d, flags=re.MULTILINE )
            d = re.sub( r"[#\t ]*AuthorizedKeysCommandUser[ \t]+.*$", "AuthorizedKeysCommandUser root", d, flags=re.MULTILINE )
    
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


def restart_services():

    print("---")
    print("Restarting services")

    subprocess.run( [ *sudo_command, "systemctl", "restart", "ssh.service" ] )
    subprocess.run( [ *sudo_command, "systemctl", "restart", "sssd.service" ] )


print("Starting SSSD configuration steps")

install_apt_packages()
uninstall_apt_packages()
configure_sssd()
configure_ssh_auth_method()
enable_automatic_homedir_creation()
restart_services()

print("---")
print("Finished SSSD configuration steps")
