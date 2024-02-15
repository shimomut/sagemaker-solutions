import os
import time
import json
import pprint
import subprocess
import signal

import pexpect
import pexpect.popen_spawn
import cmd2
from cmd2 import Bg, Fg, style
import boto3

import logs
from misc import *


# TODO:
# - Improve output from create/delete commands
# - Allow using instance group names to specify instance, for ssm command, log command, etc

cmd_aws = ["aws"]


class HyperPodShellApp(cmd2.Cmd):

    CATEGORY_HYPERPOD = "HyperPod operations"

    def __init__(self):
        super().__init__(
            multiline_commands=["echo"],
            persistent_history_file="cmd2_history.dat",
            startup_script="scripts/startup.txt",
            include_ipy=True,
        )

        self.intro = style("Welcome to HyperPod Shell", fg=Fg.RED, bg=Bg.WHITE, bold=True)
        self.prompt = style("HyperPod $ ", fg=Fg.GREEN, bg=None, bold=False)

        # Allow access to your application in py and ipy via self
        self.self_in_py = True

        # Set the default category name
        self.default_category = "cmd2 Built-in Commands"


    # -------------
    # boto3 clients

    _sagemaker_client = None
    @staticmethod
    def get_sagemaker_client():
        if not HyperPodShellApp._sagemaker_client:
            HyperPodShellApp._sagemaker_client = boto3.client("sagemaker")
        return HyperPodShellApp._sagemaker_client

    _logs_client = None
    @staticmethod
    def get_logs_client():
        if not HyperPodShellApp._logs_client:
            HyperPodShellApp._logs_client = boto3.client("logs")
        return HyperPodShellApp._logs_client


    # ----------
    # completers

    def choices_cluster_names(self, arg_tokens):

        choices = []

        sagemaker_client = self.get_sagemaker_client()
        clusters = list_clusters_all(sagemaker_client)
        for cluster in clusters:
            choices.append( cluster["ClusterName"] )

        return choices


    def choices_node_ids(self, arg_tokens):

        cluster_name = None
        cluster_names = arg_tokens["cluster_name"]
        if len(cluster_names)==1:
            cluster_name = cluster_names[0]

        choices = []

        sagemaker_client = self.get_sagemaker_client()

        try:
            nodes = list_cluster_nodes_all( sagemaker_client, cluster_name )
        except sagemaker_client.exceptions.ResourceNotFound:
            raise cmd2.CompletionError(f"Cluster [{cluster_name}] not found.")

        for node in nodes:
            choices.append( node["InstanceId"] )

        return choices


    def choices_node_ids_from_log_streams(self, arg_tokens):

        cluster_name = None
        cluster_names = arg_tokens["cluster_name"]
        if len(cluster_names)==1:
            cluster_name = cluster_names[0]

        choices = []

        sagemaker_client = self.get_sagemaker_client()
        logs_client = self.get_logs_client()

        try:
            cluster = sagemaker_client.describe_cluster(
                ClusterName = cluster_name
            )
        except sagemaker_client.exceptions.ResourceNotFound:
            raise cmd2.CompletionError(f"Cluster [{cluster_name}] not found.")

        cluster_id = cluster["ClusterArn"].split("/")[-1]
        log_group = f"/aws/sagemaker/Clusters/{cluster_name}/{cluster_id}"

        try:
            streams = list_log_streams_all(logs_client, log_group)
        except logs_client.exceptions.ResourceNotFoundException:
            raise cmd2.CompletionError(f"Log group [{log_group}] not found.")

        for stream in streams:
            stream_name = stream["logStreamName"]
            node_id = stream_name.split("/")[-1]
            choices.append(node_id)

        return choices


    # --------
    # commands

    argparser = cmd2.Cmd2ArgumentParser(description="Create a cluster with JSON file")
    argparser.add_argument("cluster_name", metavar="CLUSTER_NAME", action="store", help="Name of cluster")
    argparser.add_argument("--instances", action="store", required=True, completer=cmd2.Cmd.path_complete, help="JSON formatted config file path for instance groups")
    argparser.add_argument("--vpc", action="store", required=False, completer=cmd2.Cmd.path_complete, help="JSON formatted config file path for VPC")

    @cmd2.with_category(CATEGORY_HYPERPOD)
    @cmd2.with_argparser(argparser)
    def do_create(self, args):

        params = {
            "ClusterName" : args.cluster_name,
        }

        with open(args.instances) as fd:
            params["InstanceGroups"] = json.loads(fd.read())

        if args.vpc:
            with open(args.vpc) as fd:
                params["VpcConfig"] = json.loads(fd.read())

        sagemaker_client = self.get_sagemaker_client()
        response = sagemaker_client.create_cluster(**params)

        self.poutput(pprint.pformat(response))


    argparser = cmd2.Cmd2ArgumentParser(description="Delete a cluster")
    argparser.add_argument("cluster_name", metavar="CLUSTER_NAME", action="store", choices_provider=choices_cluster_names, help="Name of cluster")
    argparser.add_argument("-y", "--yes", action="store_true", default=False, help="Skip confirmation")

    @cmd2.with_category(CATEGORY_HYPERPOD)
    @cmd2.with_argparser(argparser)
    def do_delete(self, args):

        if not args.yes:
            answer = input(f"Are you sure deleting the cluster [{args.cluster_name}]? [y/N] : ")
            if answer.lower() not in ["y","yes"]:
                return

        sagemaker_client = self.get_sagemaker_client()

        try:
            response = sagemaker_client.delete_cluster(
                ClusterName = args.cluster_name,
            )
        except sagemaker_client.exceptions.ResourceNotFound:
            self.poutput(f"Cluster [{args.cluster_name}] not found.")
            return

        self.poutput(pprint.pformat(response))


    argparser = cmd2.Cmd2ArgumentParser(description="List clusters in human readable format")
    argparser.add_argument("--details", action="store_true", default=False, help="Show details" )

    @cmd2.with_category(CATEGORY_HYPERPOD)
    @cmd2.with_argparser(argparser)
    def do_list(self, args):

        sagemaker_client = self.get_sagemaker_client()

        clusters = list_clusters_all(sagemaker_client)

        format_string = "{:<%d} : {:<%d} : {} : {}" % (get_max_len(clusters,"ClusterName"), get_max_len(clusters,"ClusterStatus"))

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


    argparser = cmd2.Cmd2ArgumentParser(description="Describe cluster and its nodes in depth")
    argparser.add_argument("cluster_name", metavar="CLUSTER_NAME", action="store", choices_provider=choices_cluster_names, help="Name of cluster")
    argparser.add_argument("--details", action="store_true", default=False, help="Show details" )

    @cmd2.with_category(CATEGORY_HYPERPOD)
    @cmd2.with_argparser(argparser)
    def do_describe(self, args):

        sagemaker_client = self.get_sagemaker_client()

        try:
            cluster = sagemaker_client.describe_cluster(
                ClusterName = args.cluster_name
            )
        except sagemaker_client.exceptions.ResourceNotFound:
            self.poutput(f"Cluster [{args.cluster_name}] not found.")
            return
        
        nodes = list_cluster_nodes_all( sagemaker_client, args.cluster_name )

        self.poutput(f"Cluster name : {cluster['ClusterName']}")
        self.poutput(f"Cluster Arn : {cluster['ClusterArn']}")
        self.poutput(f"Cluster status : {cluster['ClusterStatus']}")

        if cluster["ClusterStatus"] in ["Failed"]:
            self.poutput(f"Failure message : {cluster['FailureMessage']}")

        self.poutput("")

        format_string = "{:<%d} : {} : {:<%d} : {} : {}" % (get_max_len(nodes,"InstanceGroupName"), get_max_len(nodes,("InstanceStatus","Status"))+1)

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

                    self.poutput(format_string.format( instance_group_name, node_id, node_status, node["LaunchTime"].strftime("%Y/%m/%d %H:%M:%S"), ssm_target ))

                    if "Message" in node["InstanceStatus"]:
                        message = node["InstanceStatus"]["Message"]
                        self.poutput("")
                        for line in message.splitlines():
                            self.poutput(line)
                        self.poutput("")
                        self.poutput("---")


    argparser = cmd2.Cmd2ArgumentParser(description="Wait asynchronous cluster operations")
    argparser.add_argument("cluster_name", metavar="CLUSTER_NAME", action="store", choices_provider=choices_cluster_names, nargs='?', default=None, help="Name of cluster. Wait instance level operations when specified.")

    @cmd2.with_category(CATEGORY_HYPERPOD)
    @cmd2.with_argparser(argparser)
    def do_wait(self, args):

        sagemaker_client = self.get_sagemaker_client()

        progress_dots = ProgressDots()

        if args.cluster_name is None:

            # Wait cluster creation/deletion
            while True:
                status_list = []
                clusters = list_clusters_all(sagemaker_client)
                for cluster in clusters:
                    if cluster["ClusterStatus"] not in ["InService","Failed"]:
                        status_list.append( cluster["ClusterName"] + ":" + cluster["ClusterStatus"] )

                progress_dots.tick(", ".join(status_list))

                if not status_list:
                    progress_dots.tick(None)
                    break

                time.sleep(5)

        else:

            # Wait instance creation/deletion
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


    argparser = cmd2.Cmd2ArgumentParser(description="Print log from a cluster node")
    argparser.add_argument("cluster_name", metavar="CLUSTER_NAME", action="store", choices_provider=choices_cluster_names, help="Name of cluster")
    argparser.add_argument("node_id", metavar="NODE_ID", action="store", choices_provider=choices_node_ids_from_log_streams, help="Id of node")

    @cmd2.with_category(CATEGORY_HYPERPOD)
    @cmd2.with_argparser(argparser)
    def do_log(self, args):

        sagemaker_client = self.get_sagemaker_client()
        logs_client = self.get_logs_client()

        try:
            cluster = sagemaker_client.describe_cluster(
                ClusterName = args.cluster_name
            )
        except sagemaker_client.exceptions.ResourceNotFound:
            self.poutput(f"Cluster [{args.cluster_name}] not found.")
            return

        cluster_id = cluster["ClusterArn"].split("/")[-1]
        log_group = f"/aws/sagemaker/Clusters/{args.cluster_name}/{cluster_id}"

        try:
            streams = list_log_streams_all(logs_client, log_group)
        except logs_client.exceptions.ResourceNotFoundException:
            self.poutput(f"Log group [{log_group}] not found.")
            return

        if args.node_id=="*":
            for stream in streams:
                stream = stream["logStreamName"]
                
                header = f"--- {log_group} {stream} ---"
                self.poutput("-" * len(header))
                self.poutput(header)
                self.poutput("-" * len(header))
                logs.print_log(logs_client, log_group, stream)
                self.poutput(f"")
        else:
            for stream in streams:
                if stream["logStreamName"].endswith(args.node_id):
                    stream = stream["logStreamName"]
                    break
            else:
                self.poutput(f"Log stream for [{args.node_id}] not found.")
                return

            logs.print_log(logs_client, log_group, stream)
            self.poutput(f"")


    argparser = cmd2.Cmd2ArgumentParser(description="Login to a cluster node with SSM")
    argparser.add_argument("cluster_name", metavar="CLUSTER_NAME", action="store", choices_provider=choices_cluster_names, help="Name of cluster")
    argparser.add_argument("node_id", metavar="NODE_ID", action="store", choices_provider=choices_node_ids, help="Id of node")

    @cmd2.with_category(CATEGORY_HYPERPOD)
    @cmd2.with_argparser(argparser)
    def do_ssm(self, args):

        sagemaker_client = self.get_sagemaker_client()

        try:
            cluster = sagemaker_client.describe_cluster(
                ClusterName = args.cluster_name
            )
        except sagemaker_client.exceptions.ResourceNotFound:
            self.poutput(f"Cluster [{args.cluster_name}] not found.")
            return

        nodes = list_cluster_nodes_all( sagemaker_client, args.cluster_name )

        cluster_id = cluster["ClusterArn"].split("/")[-1]

        for node in nodes:
            instance_group_name = node["InstanceGroupName"]
            node_id = node["InstanceId"]
            if node_id==args.node_id:
                break
        else:
            self.poutput(f"Node ID [{args.node_id}] not found.")
            return

        ssm_target = f"sagemaker-cluster:{cluster_id}_{instance_group_name}-{node_id}"

        if 1:
            with self.sigint_protection:
                cmd = ["aws", "ssm", "start-session", "--target", ssm_target]
                subprocess.run(cmd)

        # use pexpect to automatically switch to ubuntu user
        elif 0:
            cmd = f"aws ssm start-session --target {ssm_target}"
            self.poutput(cmd)
            p = pexpect.spawn(cmd)
            p.expect("#")
            self.poutput(p.before.decode("utf-8") + p.after.decode("utf-8"), end="")

            def run_single_command(cmd):
                p.sendline(cmd)
                p.expect( ["#","$"] )
                self.poutput(p.before.decode("utf-8") + p.after.decode("utf-8"), end="")

            run_single_command(f"sudo su ubuntu")
            run_single_command(f"cd && bash")

            p.interact()

            p.terminate(force=True)





    argparser = cmd2.Cmd2ArgumentParser(description="Set up SSH acccess to all cluster nodes")
    subparsers = argparser.add_subparsers(title="sub-commands")

    @cmd2.with_category(CATEGORY_HYPERPOD)
    @cmd2.with_argparser(argparser)
    def do_ssh(self, args):
        func = getattr(args, "func", None)
        if func is not None:
            func(self, args)
        else:
            self.do_help("ssh")


    subparser_print_config = subparsers.add_parser('print-config', help='Print SSH config for cluster nodes')
    subparser_print_config.add_argument("cluster_name", metavar="CLUSTER_NAME", action="store", choices_provider=choices_cluster_names, help="Name of cluster")

    def _do_ssh_print_config(self, args):

        sagemaker_client = self.get_sagemaker_client()

        try:
            cluster = sagemaker_client.describe_cluster(
                ClusterName = args.cluster_name
            )
        except sagemaker_client.exceptions.ResourceNotFound:
            self.poutput(f"Cluster [{args.cluster_name}] not found.")
            return
        
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

                    self.poutput("")                
                    self.poutput(
                        f"Host {args.cluster_name}-{instance_group_name}-{node_index}\n"
                        f"    HostName sagemaker-cluster:{cluster_id}_{instance_group_name}-{node_id}\n"
                        f"    User ubuntu\n"
                        f"    IdentityFile c:/Users/shimomut/Keys/842413447717-ec2.pem\n"
                        f"    ProxyCommand aws.cmd --profile {profile} --region {get_region()} ssm start-session --target %h --document-name AWS-StartSSHSession --parameters portNumber=%p"
                    )

                    node_index += 1

        self.poutput("")

    subparser_print_config.set_defaults(func=_do_ssh_print_config)


    subparser_install_key = subparsers.add_parser('install-key', help='Install SSH public key to all cluster nodes')
    subparser_install_key.add_argument("cluster_name", metavar="CLUSTER_NAME", action="store", choices_provider=choices_cluster_names, help="Name of cluster")
    subparser_install_key.add_argument("public_key_file", metavar="PUBLIC_KEY_FILE", action="store", completer=cmd2.Cmd.path_complete, help="SSH public key file")
    
    def _do_ssh_install_key(self, args):

        sagemaker_client = self.get_sagemaker_client()

        try:
            cluster = sagemaker_client.describe_cluster(
                ClusterName = args.cluster_name
            )
        except sagemaker_client.exceptions.ResourceNotFound:
            self.poutput(f"Cluster [{args.cluster_name}] not found.")
            return
        
        nodes = list_cluster_nodes_all( sagemaker_client, args.cluster_name )

        cluster_id = cluster["ClusterArn"].split("/")[-1]

        public_key_file = os.path.expanduser(args.public_key_file)

        with open(public_key_file) as fd:
            public_key = fd.read().strip()

        for node in nodes:
            instance_group_name = node["InstanceGroupName"]
            node_id = node["InstanceId"]
            ssm_target = f"sagemaker-cluster:{cluster_id}_{instance_group_name}-{node_id}"

            self.poutput(f"Installing ssh public key to {node_id}")

            p = pexpect.popen_spawn.PopenSpawn([*cmd_aws, "ssm", "start-session", "--target", ssm_target])
            p.expect("#")
            cmd = f"cat /home/ubuntu/.ssh/authorized_keys"
            p.sendline(cmd)
            p.expect("#")

            if public_key in p.before.decode("utf-8"):
                self.poutput("Already installed")
            else:
                cmd = f"echo {public_key} >> /home/ubuntu/.ssh/authorized_keys"
                p.sendline(cmd)
                p.expect("#")
                self.poutput("Done")

            p.kill(signal.SIGINT)

    subparser_install_key.set_defaults(func=_do_ssh_install_key)


    argparser = cmd2.Cmd2ArgumentParser(description="Run single line command in all nodes of specified instance group")
    argparser.add_argument("cluster_name", metavar="CLUSTER_NAME", action="store", choices_provider=choices_cluster_names, help="Name of cluster")
    argparser.add_argument("--instance-group-name", action="store", required=True, help="Instance group name")
    argparser.add_argument("--command", action="store", required=True, help="Single line of command to run")

    @cmd2.with_category(CATEGORY_HYPERPOD)
    @cmd2.with_argparser(argparser)
    def do_bulk_run_command(self, args):

        sagemaker_client = self.get_sagemaker_client()

        try:
            cluster = sagemaker_client.describe_cluster(
                ClusterName = args.cluster_name
            )
        except sagemaker_client.exceptions.ResourceNotFound:
            self.poutput(f"Cluster [{args.cluster_name}] not found.")
            return
        
        nodes = list_cluster_nodes_all( sagemaker_client, args.cluster_name )

        cluster_id = cluster["ClusterArn"].split("/")[-1]

        for node in nodes:
            instance_group_name = node["InstanceGroupName"]

            if instance_group_name==args.instance_group_name:

                node_id = node["InstanceId"]
                ssm_target = f"sagemaker-cluster:{cluster_id}_{instance_group_name}-{node_id}"

                self.poutput(f"Running command in {node_id}")
                self.poutput("")

                p = pexpect.popen_spawn.PopenSpawn([*cmd_aws, "ssm", "start-session", "--target", ssm_target])
                p.expect("#")
                self.poutput(p.after.decode("utf-8"),end="")
                p.sendline(args.command)
                p.expect("#")
                self.poutput(p.before.decode("utf-8"),end="")
                p.kill(signal.SIGINT)

                self.poutput("-----")


if __name__ == "__main__":
    app = HyperPodShellApp()
    app.cmdloop()
