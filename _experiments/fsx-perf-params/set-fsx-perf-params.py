# https://docs.aws.amazon.com/fsx/latest/LustreGuide/performance.html#performance-tips

# How to use:
#   1. Copy this script to /tmp
#       srun -N 16 cp ./set-fsx-perf-params.py /tmp
#   2. Change directory to /tmp
#       cd /tmp
#   2. Run script
#       srun -N 16 sudo python3.9 /tmp/set-fsx-perf-params.py

import sys
import io
import re
import subprocess


def run_subprocess_wrap(cmd, print_output=True, to_file=None, raise_non_zero_retcode=True):

    print(f"Running {cmd}")

    captured_stdout = io.StringIO()

    p = subprocess.Popen( cmd, bufsize=1, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT )
    for line in iter(p.stdout.readline, ""):
        captured_stdout.write(line)
        if print_output:
            print( line, end="", flush=True )
    p.wait()

    if to_file:
        with open(to_file,"w") as fd:
            fd.write(captured_stdout.getvalue())

    if raise_non_zero_retcode and p.returncode != 0:
        raise ChildProcessError(f"Subprocess {cmd} returned non-zero exit code {p.returncode}.")
    
    return captured_stdout.getvalue()


def list_network_interfaces(namespace):

    interfaces = []
    interface = {}

    cmd = ["ip", "netns", "exec", namespace, "ip", "link"]
    captured_output = run_subprocess_wrap(cmd, print_output=False)
    for line in captured_output.splitlines():

        # sample format
        """
        4: ens65: <BROADCAST,MULTICAST> mtu 9001 qdisc noop state DOWN mode DEFAULT group default qlen 1000
            link/ether 0e:1b:62:45:6a:0f brd ff:ff:ff:ff:ff:ff
            altname enp32s1
        """

        re_result = re.match(r"[0-9]+: ([^:]+).*: <.*> .*", line)
        if re_result:
            if interface:
                interfaces.append(interface)
                interface = {}
            interface["name"] = re_result.group(1)
            continue

        re_result = re.match(r"[ ]+ link/ether ([0-9a-f:]+) brd ([0-9a-f:]+)", line)
        if re_result:
            interface["mac_addr"] = re_result.group(1)
            continue

    if interface:
        interfaces.append(interface)
        interface = {}

    return interfaces


for nic in list_network_interfaces("default"):
    if nic["name"].startswith("enp"):
        break


run_subprocess_wrap(["lctl", "set_param", "osc.*.max_dirty_mb=64"])
run_subprocess_wrap(["lctl", "set_param", "ldlm.namespaces.*.lru_max_age=600000"])
run_subprocess_wrap(["lctl", "set_param", "ldlm.namespaces.*.lru_size=9600"])

with open("/etc/modprobe.d/modprobe.conf", "a") as fd:
    fd.write("options ptlrpc ptlrpcd_per_cpt_max=32\n")
    fd.write("options ksocklnd credits=2560\n")

# reload all kernel modules to apply the above two settings
# Instead of rebooting, do this:
run_subprocess_wrap(["umount", "/fsx"])
run_subprocess_wrap(["umount", "/fsx2"])
run_subprocess_wrap(["lustre_rmmod"])
run_subprocess_wrap(["modprobe", "lustre"])
run_subprocess_wrap(["mount", "/fsx"])
run_subprocess_wrap(["mount", "/fsx2"])

run_subprocess_wrap(["lctl", "set_param", "osc.*OST*.max_rpcs_in_flight=32"])
run_subprocess_wrap(["lctl", "set_param", "mdc.*.max_rpcs_in_flight=64"])
run_subprocess_wrap(["lctl", "set_param", "mdc.*.max_mod_rpcs_in_flight=50"])

run_subprocess_wrap(["lnetctl", "lnet", "configure"])
run_subprocess_wrap(["lnetctl", "net", "del", "--net", "tcp"])
run_subprocess_wrap(["lnetctl", "net", "add", "--net", "tcp", "--if", nic["name"], "--cpt", "0"])
run_subprocess_wrap(["ethtool", "-G", nic["name"], "rx", "8192"])
