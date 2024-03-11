import sys
import os
import subprocess
import tempfile
import re
import getpass


# ---------------------------------
# Configurations you need to modify

class Config:

    # Name of domain. Can be default if you are not sure.
    domain = "default"

    # Comma separated list of LDAP server URIs
    ldap_uri = "ldaps://nlb-ds-97c6de9ec6862771.elb.us-west-2.amazonaws.com"

    # The default base DN to use for performing LDAP user operations
    ldap_search_base = "dc=hyperpod,dc=abc123,dc=com"

    # The default bind DN to use for performing LDAP operations
    ldap_default_bind_dn = "CN=Admin,OU=Users,OU=hyperpod,DC=hyperpod,DC=abc123,DC=com"
    
    # "password" or "obfuscated_password"
    ldap_default_authtok_type = "obfuscated_password"

    # You need to modify this parameter with the obfuscated password you got with obfuscate_password.py
    ldap_default_authtok = "placeholder"

    # SSH authentication method - "password" or "publickey"
    ssh_auth_method = "publickey"

    # Home directory
    override_homedir = "/home/%u"
    #override_homedir = "/fsx/%u"


# ---------------------------------

if getpass.getuser() == "root":
    sudo_command = []
else:
    sudo_command = ["sudo","-E"]

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
ldap_config_filename = "/etc/ldap/ldap.conf"

cert_filename = "/etc/ldap/ldaps_cert.pem"
cert_filename_src = os.path.join( os.path.dirname(__file__), os.path.basename(cert_filename) )

assert os.path.exists(cert_filename_src), f"Certificate file not found - {cert_filename_src}"
assert Config.ldap_default_authtok != "placeholder", "You need to configure Config.ldap_default_authtok. You can use tools/obfuscate_password.py to get obfuscated password"
assert Config.ssh_auth_method in ["password", "publickey"], f"Config.ssh_auth_method has to be either 'password' or 'publickey'"


# ---------------------------------
# Templates for configuration files

sssd_conf = f"""
[domain/{Config.domain}]
id_provider = ldap
cache_credentials = True
ldap_uri = {Config.ldap_uri}
ldap_search_base = {Config.ldap_search_base}
ldap_schema = AD
ldap_default_bind_dn = {Config.ldap_default_bind_dn}
ldap_default_authtok_type = {Config.ldap_default_authtok_type}
ldap_default_authtok = {Config.ldap_default_authtok}
ldap_tls_cacert = {cert_filename}
ldap_tls_reqcert = hard
ldap_id_mapping = True
ldap_referrals = False
ldap_user_extra_attrs = altSecurityIdentities:altSecurityIdentities
ldap_user_ssh_public_key = altSecurityIdentities
ldap_use_tokengroups = True
enumerate = False
fallback_homedir = /home/%u
override_homedir = {Config.override_homedir}
default_shell = /bin/bash
#use_fully_qualified_names = True
#debug_level = 6

[sssd]
config_file_version = 2
domains = {Config.domain}
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

def install_apt_packages():

    print("---")
    print("Updating apt package index")
    subprocess.run( [ *sudo_command, "apt", "update" ] )

    print("---")
    print("Installing packages - ", packages_to_install)
    subprocess.run( [ *sudo_command, "apt", "install", "-y", *packages_to_install ] )


def uninstall_apt_packages():

    print("---")
    print("Uninstalling packages - ", packages_to_uninstall)
    subprocess.run( [ *sudo_command, "apt", "remove", "-y", *packages_to_uninstall ] )


def install_ldaps_cert():

    print("---")
    print("Installing cert for LDAPS - ", cert_filename)
    subprocess.run( [ *sudo_command, "cp", cert_filename_src, cert_filename ] )
    subprocess.run( [ *sudo_command, "chmod", "644", cert_filename ] )

    print("---")
    print(f"Updating {ldap_config_filename} ldap utility commands")
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_ldap_config_filename = os.path.join(tmp_dir, os.path.basename(ldap_config_filename))

        with open(ldap_config_filename) as fd_src:
            d = fd_src.read()

        d = re.sub( r"[#\t ]*TLS_CACERT[ \t]+.*$", f"TLS_CACERT {cert_filename}", d, flags=re.MULTILINE )    
        print(d)

        with open(tmp_ldap_config_filename,"w") as fd_dst:
            fd_dst.write(d)

        subprocess.run( [ *sudo_command, "chmod", "644", tmp_ldap_config_filename ] )
        subprocess.run( [ *sudo_command, "chown", "root:root", tmp_ldap_config_filename ] )
        subprocess.run( [ *sudo_command, "cp", tmp_ldap_config_filename, ldap_config_filename ] )


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
    print(f"Configuring SSH authentication method to {Config.ssh_auth_method}")

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_sshd_config_filename = os.path.join(tmp_dir, os.path.basename(sshd_config_filename))

        with open(sshd_config_filename) as fd_src:
            d = fd_src.read()

        if Config.ssh_auth_method=="password":
            d = re.sub( r"[#\t ]*PasswordAuthentication[ \t]+.*$", "PasswordAuthentication yes", d, flags=re.MULTILINE )
        elif Config.ssh_auth_method=="publickey":
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
install_ldaps_cert()
configure_sssd()
configure_ssh_auth_method()
enable_automatic_homedir_creation()
restart_services()

print("---")
print("Finished SSSD configuration steps")
