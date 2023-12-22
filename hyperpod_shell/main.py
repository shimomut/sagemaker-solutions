import os

import cmd2
from cmd2 import Bg, Fg, style

import boto3

import tree
from misc import *


class HyperPodShellApp(cmd2.Cmd):

    CATEGORY_HYPERPOD = 'HyperPod operations'
    CATEGORY_TEST = 'Test commands'

    def __init__(self):
        super().__init__(
            multiline_commands=['echo'],
            persistent_history_file='cmd2_history.dat',
            startup_script='scripts/startup.txt',
            include_ipy=True,
        )

        self.intro = style('Welcome to HyperPod Shell', fg=Fg.RED, bg=Bg.WHITE, bold=True)
        self.prompt = 'HyperPod $ '

        # Allow access to your application in py and ipy via self
        self.self_in_py = True

        # Set the default category name
        self.default_category = 'cmd2 Built-in Commands'

    @cmd2.with_category(CATEGORY_TEST)
    def do_intro(self, _):
        """Display the intro banner"""
        self.poutput(self.intro)

    @cmd2.with_category(CATEGORY_TEST)
    def do_echo(self, arg):
        """Example of a multiline command"""
        self.poutput(arg)

    @cmd2.with_category(CATEGORY_TEST)
    def do_rich(self, arg):
        """Test rich text library"""
        print("Hello")
        self.poutput("Hello2")
        tree.print_tree()

    # ----

    argparser = cmd2.Cmd2ArgumentParser(description='Create a cluster with JSON file')
    argparser.add_argument('--cluster-name', action='store', required=True, help='Name of cluster')
    argparser.add_argument('--instance-groups-config-file', action='store', required=True, completer=cmd2.Cmd.path_complete, help='JSON formatted config file path for instance groups')
    argparser.add_argument('--vpc-config-file', action='store', required=False, completer=cmd2.Cmd.path_complete, help='JSON formatted config file path for VPC')

    @cmd2.with_category(CATEGORY_HYPERPOD)
    @cmd2.with_argparser(argparser)
    def do_create(self, args):

        params = {
            "ClusterName" : args.cluster_name,
        }

        with open(args.instance_groups_config_file) as fd:
            params["InstanceGroups"] = json.loads(fd.read())

        if args.vpc_config_file:
            with open(args.vpc_config_file) as fd:
                params["VpcConfig"] = json.loads(fd.read())

        sagemaker_client = boto3.client("sagemaker")
        response = sagemaker_client.create_cluster(**params)

        pprint.pprint(response)


    argparser = cmd2.Cmd2ArgumentParser(description='Delete a cluster')
    argparser.add_argument('--cluster-name', action='store', required=True, help='Name of cluster')
    argparser.add_argument('--yes', action='store_true', default=False, help='Skip confirmation')

    @cmd2.with_category(CATEGORY_HYPERPOD)
    @cmd2.with_argparser(argparser)
    def do_delete(self, args):

        if not args.yes:
            answer = input(f"Are you sure deleting the cluster [{args.cluster_name}]? [y/N] : ")
            if answer.lower() not in ["y","yes"]:
                return

        sagemaker_client = boto3.client("sagemaker")

        try:
            response = sagemaker_client.delete_cluster(
                ClusterName = args.cluster_name,
            )
        except sagemaker_client.exceptions.ResourceNotFound:
            print(f"Cluster [{args.cluster_name}] not found.")
            return

        pprint.pprint(response)


    argparser = cmd2.Cmd2ArgumentParser(description='List clusters in human readable format')
    argparser.add_argument('--details', action='store_true', default=False, help="Show details" )

    @cmd2.with_category(CATEGORY_HYPERPOD)
    @cmd2.with_argparser(argparser)
    def do_list(self, args):

        sagemaker_client = boto3.client("sagemaker")

        clusters = list_clusters_all(sagemaker_client)

        format_string = "{:<%d} : {:<%d} : {} : {}" % (get_max_len(clusters,'ClusterName'), get_max_len(clusters,"ClusterStatus"))

        for cluster in clusters:

            self.poutput( format_string.format( cluster["ClusterName"], cluster["ClusterStatus"], cluster["CreationTime"].strftime("%Y/%m/%d %H:%M:%S"), cluster["ClusterArn"] ) )

            if cluster["ClusterStatus"] in ["Failed"]:

                cluster_details = sagemaker_client.describe_cluster(
                    ClusterName = cluster["ClusterName"]
                )

                self.poutput("")
                for line in cluster_details["FailureMessage"].splitlines():
                    self.poutput(f"{line}")
                self.poutput("")
                self.poutput("---")


    argparser = cmd2.Cmd2ArgumentParser(description='Describe cluster and its nodes in depth')
    argparser.add_argument('--cluster-name', action='store', required=True, help='Name of cluster')
    argparser.add_argument('--details', action='store_true', default=False, help="Show details" )

    @cmd2.with_category(CATEGORY_HYPERPOD)
    @cmd2.with_argparser(argparser)
    def do_describe(self, args):

        sagemaker_client = boto3.client("sagemaker")

        try:
            cluster = sagemaker_client.describe_cluster(
                ClusterName = args.cluster_name
            )
        except sagemaker_client.exceptions.ResourceNotFound:
            print(f"Cluster [{args.cluster_name}] not found.")
            return
        
        nodes = list_cluster_nodes_all( sagemaker_client, args.cluster_name )

        print("Cluster name :", cluster["ClusterName"])
        print("Cluster Arn :", cluster["ClusterArn"])
        print("Cluster status :", cluster["ClusterStatus"])

        if cluster["ClusterStatus"] in ["Failed"]:
            print("Failure message :", cluster["FailureMessage"])

        print()

        format_string = "{:<%d} : {} : {:<%d} : {} : {}" % (get_max_len(nodes,'InstanceGroupName'), get_max_len(nodes,("InstanceStatus","Status"))+1)

        for instance_group in cluster["InstanceGroups"]:
            for node in nodes:
                if node["InstanceGroupName"]==instance_group["InstanceGroupName"]:

                    cluster_id = cluster["ClusterArn"].split("/")[-1]
                    instance_group_name = node["InstanceGroupName"]
                    node_id = node["InstanceId"]
                    node_status = node["InstanceStatus"]["Status"]
                    ssm_target = f"sagemaker-cluster:{cluster_id}_{instance_group_name}-{node_id}"

                    if node_status in ["Pending"]:
                        node_status = "*" + node_status

                    print( format_string.format( instance_group_name, node_id, node_status, node["LaunchTime"].strftime("%Y/%m/%d %H:%M:%S"), ssm_target ) )

                    if "Message" in node["InstanceStatus"]:
                        message = node["InstanceStatus"]["Message"]
                        print()
                        for line in message.splitlines():
                            print(f"{line}")
                        print()
                        print("---")


    argparser = cmd2.Cmd2ArgumentParser(description='Wait cluster creation / deletion')

    @cmd2.with_category(CATEGORY_HYPERPOD)
    @cmd2.with_argparser(argparser)
    def do_wait_clusters(self, args):

        sagemaker_client = boto3.client("sagemaker")

        progress_dots = ProgressDots()

        # list the clusters that are being created/deleted.
        cluster_names_to_watch = set()
        clusters = list_clusters_all(sagemaker_client)
        for cluster in clusters:
            if cluster["ClusterStatus"] not in ["InService","Failed"]:
                cluster_names_to_watch.add(cluster["ClusterName"])

        if not cluster_names_to_watch:
            print("Nothing to wait.")
            return

        # Monitor status until everything finishes
        while True:
            num_in_progress = 0
            status_list = []
            clusters = list_clusters_all(sagemaker_client)
            for cluster in clusters:
                if cluster["ClusterName"] in cluster_names_to_watch:
                    status_list.append( cluster["ClusterName"] + ":" + cluster["ClusterStatus"] )
                    if cluster["ClusterStatus"] not in ["InService","Failed"]:
                        num_in_progress += 1
            progress_dots.tick(", ".join(status_list))

            if num_in_progress==0:
                progress_dots.tick(None)
                break

            time.sleep(5)


    argparser = cmd2.Cmd2ArgumentParser(description='Wait node creation / deletion')
    argparser.add_argument('--cluster-name', action='store', required=True, help='Name of cluster')

    @cmd2.with_category(CATEGORY_HYPERPOD)
    @cmd2.with_argparser(argparser)
    def do_wait_nodes(self, args):

        sagemaker_client = boto3.client("sagemaker")

        progress_dots = ProgressDots()

        # Monitor status until everything finishes
        while True:
            num_in_progress = 0
            status_list = []

            nodes = list_cluster_nodes_all( sagemaker_client, args.cluster_name )

            for node in nodes:

                instance_group_name = node["InstanceGroupName"]
                node_id = node["InstanceId"]
                node_status = node["InstanceStatus"]["Status"]

                if node_status not in ["Running","Failed"]:
                    status_list.append(f"{instance_group_name}:{node_id}:{node_status}")
                    num_in_progress += 1

            progress_dots.tick(", ".join(status_list))

            if num_in_progress==0:
                progress_dots.tick(None)
                break

            time.sleep(5)


    argparser = cmd2.Cmd2ArgumentParser(description="Monitor log from a cluster node")
    argparser.add_argument('--cluster-name', action='store', required=True, help='Name of cluster')
    argparser.add_argument('--node-id', action='store', required=True, help='Id of node')
    argparser.add_argument('--freq', action='store', type=int, default=5, help='Polling frequency in seconds')
    argparser.add_argument('--lookback', action='store', type=int, default=60, help='Lookback window in minutes')

    @cmd2.with_category(CATEGORY_HYPERPOD)
    @cmd2.with_argparser(argparser)
    def do_monitor_log(self, args):

        sagemaker_client = boto3.client("sagemaker")

        try:
            cluster = sagemaker_client.describe_cluster(
                ClusterName = args.cluster_name
            )
        except sagemaker_client.exceptions.ResourceNotFound:
            print(f"Cluster [{args.cluster_name}] not found.")
            return

        cluster_id = cluster["ClusterArn"].split("/")[-1]
        args.log_group = f"/aws/sagemaker/Clusters/{args.cluster_name}/{cluster_id}"

        logs_client = boto3.client("logs")
        response = logs_client.describe_log_streams( logGroupName = args.log_group )
        for stream in response["logStreams"]:
            if stream["logStreamName"].endswith(args.node_id):
                args.stream = stream["logStreamName"]
                break
        else:
            print(f"Log stream for [{args.node_id}] not found.")
            return

        aws_toolbox_logs.monitor_log(args)


    argparser = cmd2.Cmd2ArgumentParser(description='Print SSH config for cluster nodes')
    argparser.add_argument('--cluster-name', action='store', required=True, help='Name of cluster')

    @cmd2.with_category(CATEGORY_HYPERPOD)
    @cmd2.with_argparser(argparser)
    def do_print_ssh_config(self, args):

        sagemaker_client = boto3.client("sagemaker")

        try:
            cluster = sagemaker_client.describe_cluster(
                ClusterName = args.cluster_name
            )
        except sagemaker_client.exceptions.ResourceNotFound:
            print(f"Cluster [{args.cluster_name}] not found.")
            return
        
        if debug:
            pprint.pprint(cluster)

        nodes = list_cluster_nodes_all( sagemaker_client, args.cluster_name )

        cluster_id = cluster["ClusterArn"].split("/")[-1]

        if "AWS_PROFILE" in os.environ:
            profile = os.environ["AWS_PROFILE"]
        else:
            profile = "default"

        for instance_group in cluster["InstanceGroups"]:
            node_index = 0
            for node in nodes:
                if node["InstanceGroupName"]==instance_group["InstanceGroupName"]:

                    instance_group_name = node["InstanceGroupName"]
                    node_id = node["InstanceId"]
                    region_arg = ""

                    print()                
                    print(
                        f"Host {args.cluster_name}-{instance_group_name}-{node_index}\n"
                        f"    HostName sagemaker-cluster:{cluster_id}_{instance_group_name}-{node_id}\n"
                        f"    User ubuntu\n"
                        f"    IdentityFile c:/Users/shimomut/Keys/842413447717-ec2.pem\n"
                        f"    ProxyCommand aws.cmd --profile {profile} --region {_get_region(args)} ssm start-session --target %h --document-name AWS-StartSSHSession --parameters portNumber=%p"
                    )

                    node_index += 1


    argparser = cmd2.Cmd2ArgumentParser(description='Install SSH public key to all cluster nodes')
    argparser.add_argument('--cluster-name', action='store', required=True, help='Name of cluster')
    argparser.add_argument('--public-key-file', action='store', required=True, help='SSH public key file')

    @cmd2.with_category(CATEGORY_HYPERPOD)
    @cmd2.with_argparser(argparser)
    def do_install_ssh_key(self, args):

        sagemaker_client = boto3.client("sagemaker")

        try:
            cluster = sagemaker_client.describe_cluster(
                ClusterName = args.cluster_name
            )
        except sagemaker_client.exceptions.ResourceNotFound:
            print(f"Cluster [{args.cluster_name}] not found.")
            return
        
        nodes = list_cluster_nodes_all( sagemaker_client, args.cluster_name )

        cluster_id = cluster["ClusterArn"].split("/")[-1]

        with open(args.public_key_file) as fd:
            public_key = fd.read().strip()

        for node in nodes:
            instance_group_name = node["InstanceGroupName"]
            node_id = node["InstanceId"]
            ssm_target = f"sagemaker-cluster:{cluster_id}_{instance_group_name}-{node_id}"

            print(f"Installing ssh public key to {node_id}")

            p = pexpect.popen_spawn.PopenSpawn([cmd_aws, "ssm", "start-session", "--target", ssm_target])
            p.expect("#")
            cmd = f"cat /home/ubuntu/.ssh/authorized_keys"
            p.sendline(cmd)
            p.expect("#")

            if public_key in p.before.decode("utf-8"):
                print("Already installed")
            else:
                cmd = f"echo {public_key} >> /home/ubuntu/.ssh/authorized_keys"
                p.sendline(cmd)
                p.expect("#")
                print("Done")

            p.kill(signal.SIGINT)


    argparser = cmd2.Cmd2ArgumentParser(description='Run single line command in all nodes of specified instance group')
    argparser.add_argument('--cluster-name', action='store', required=True, help='Name of cluster')
    argparser.add_argument('--instance-group-name', action='store', required=True, help='Instance group name')
    argparser.add_argument('--command', action='store', required=True, help='Single line of command to run')

    @cmd2.with_category(CATEGORY_HYPERPOD)
    @cmd2.with_argparser(argparser)
    def do_bulk_run_command(self, args):

        sagemaker_client = boto3.client("sagemaker")

        try:
            cluster = sagemaker_client.describe_cluster(
                ClusterName = args.cluster_name
            )
        except sagemaker_client.exceptions.ResourceNotFound:
            print(f"Cluster [{args.cluster_name}] not found.")
            return
        
        nodes = list_cluster_nodes_all( sagemaker_client, args.cluster_name )

        cluster_id = cluster["ClusterArn"].split("/")[-1]

        for node in nodes:
            instance_group_name = node["InstanceGroupName"]

            if instance_group_name==args.instance_group_name:

                node_id = node["InstanceId"]
                ssm_target = f"sagemaker-cluster:{cluster_id}_{instance_group_name}-{node_id}"

                print(f"Running command in {node_id}")
                print()

                p = pexpect.popen_spawn.PopenSpawn([cmd_aws, "ssm", "start-session", "--target", ssm_target])
                p.expect("#")
                print(p.after.decode("utf-8"),end="")
                p.sendline(args.command)
                p.expect("#")
                print(p.before.decode("utf-8"),end="")
                p.kill(signal.SIGINT)

                print("-----")


if __name__ == '__main__':
    app = HyperPodShellApp()
    app.cmdloop()
