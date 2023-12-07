import subprocess

# ---

# If this script is executed by root already, this variable can be empty
sudo_command = ["sudo"]
#sudo_command = []

packages_to_install = [
    "ldap-utils", "realmd", "sssd-tools", "adcli", "sssd", "libnss-sss", "libpam-sss"
]

# ---

print("Starting SSSD configuration steps")

print("Updating apt package index")
subprocess.run( [ *sudo_command, "apt", "update" ] )

print("---")
print("Installing packages - ", packages_to_install)
subprocess.run( [ *sudo_command, "apt", "install", "-y", *packages_to_install ] )



print("---")
print("Finished SSSD configuration steps")
