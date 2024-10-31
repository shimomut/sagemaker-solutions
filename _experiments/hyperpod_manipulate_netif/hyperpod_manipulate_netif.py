import re
import io
import subprocess
import boto3



class Config:
    region = ""
    hyperpod_cluster_arn = "arn:aws:sagemaker:us-west-2:842413447717:cluster/3lzmwykd980e"
    primary_network_interface_name = "ens33"


def extract_components_from_cluster_arn():
    re_result = re.match(r"arn:aws:sagemaker:([^:]+):([0-9]+):cluster/([a-z0-9]+)", Config.hyperpod_cluster_arn)

    if re_result is None:
        print( f"Error: malformed Cluster ARN: {Config.hyperpod_cluster_arn}" )
        sys.exit(1)

    Config.region = re_result.group(1)
    Config.account = re_result.group(2)
    Config.cluster_id = re_result.group(3)


def run_subprocess_wrap(cmd, print_output=True, to_file=None, raise_non_zero_retcode=True):

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


def list_efa_backed_enis():
    
    ec2_client = boto3.client("ec2", region_name=Config.region)

    def _describe_network_interfaces_all():
        
        network_interfaces = []
        next_token = None

        while True:

            params = {
                "MaxResults": 100
            }

            if next_token:
                params["NextToken"] = next_token

            response = ec2_client.describe_network_interfaces( **params )

            network_interfaces += response["NetworkInterfaces"]

            if "NextToken" in response:
                next_token = response["NextToken"]
            else:
                break

        return network_interfaces

    eni_table = {}
    enis = _describe_network_interfaces_all()
    for eni in enis:
        if eni["Description"].startswith(Config.hyperpod_cluster_arn):
            if eni["InterfaceType"]=="efa":
                eni_table[eni["Description"]] = eni

    return eni_table


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


def move_network_interface_namespace( name, current_namespace, new_namespace ):
    cmd = ["ip", "netns", "exec", current_namespace, "ip", "link", "set", name, "netns", new_namespace]
    run_subprocess_wrap(cmd, print_output=True)


def move_efa_to_default_namespace():

    extract_components_from_cluster_arn()

    mac_addresses_for_efas = set()
    for eni in list_efa_backed_enis().values():
        mac_addresses_for_efas.add(eni["MacAddress"])

    print(mac_addresses_for_efas)

    network_interfaces = list_network_interfaces("sagemaker_agent_namespace")

    print(network_interfaces)

    for network_interface in network_interfaces:
        if "mac_addr" in network_interface and network_interface["mac_addr"] in mac_addresses_for_efas:
            move_network_interface_namespace( network_interface["name"], "sagemaker_agent_namespace", "default")



def move_efa_to_agent_namespace():

    extract_components_from_cluster_arn()

    mac_addresses_for_efas = set()
    for eni in list_efa_backed_enis().values():
        mac_addresses_for_efas.add(eni["MacAddress"])

    print(mac_addresses_for_efas)

    network_interfaces = list_network_interfaces("default")

    print(network_interfaces)

    for network_interface in network_interfaces:
        if "mac_addr" in network_interface and network_interface["mac_addr"] in mac_addresses_for_efas:
            if network_interface["name"] == Config.primary_network_interface_name:
                continue
            move_network_interface_namespace( network_interface["name"], "default", "sagemaker_agent_namespace")



#move_efa_to_default_namespace()
move_efa_to_agent_namespace()


