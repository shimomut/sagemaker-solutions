
import sys
import os
import io
import re
import argparse
import subprocess
import socket
import concurrent.futures

def run_subprocess_wrap(cmd, print_output=True, to_file=None):

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

    if p.returncode != 0:
        raise ChildProcessError(f"Subprocess {cmd} returned non-zero exit code {p.returncode}.")
    
    return captured_stdout.getvalue()


def list_all_nodes():

    node_names = set()

    captured_output = run_subprocess_wrap(["sinfo", "-N", "-o", "%N"], print_output=False)
    for line in captured_output.splitlines():
        re_result = re.match(r"(ip\-[0-9]+\-[0-9]+\-[0-9]+\-[0-9]+)", line)
        if re_result:
            node_name = re_result.group(1)
            node_names.add(node_name)

    return node_names


def main(args):

    node_names = list_all_nodes()

    output_path_top = os.path.abspath(args.output_path)

    cmd = [
        sys.executable,
        os.path.abspath(sys.argv[0]),
        "--capture-single-node",
        "--head-node",
        "--output-path", os.path.join(output_path_top, f"control"),
    ]

    # Capture report data from current node (head node)
    run_subprocess_wrap([*cmd], print_output=True)

    # Capture report data from worker nodes
    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as thread_pool:
            
        def _capture(node_name):

            cmd = [
                sys.executable,
                os.path.abspath(sys.argv[0]),
                "--capture-single-node",
                "--output-path", os.path.join(output_path_top, f"worker"),
            ]

            run_subprocess_wrap(["ssh", node_name, *cmd], print_output=True)
            return node_name, True

        for node_name, result in thread_pool.map(_capture, node_names ):
            pass


def capture(args):

    hostname = socket.gethostname()

    print(f"Capturing report data from {hostname}")

    output_path = os.path.join(args.output_path, hostname)

    os.makedirs( output_path, exist_ok=True )

    run_subprocess_wrap([ "touch", os.path.join(output_path, "some_data.txt") ], print_output=False)

    if args.head_node:

        cmd = ["sudo", "cp", "/opt/ml/config/resource_config.json", output_path]
        run_subprocess_wrap(cmd, print_output=False)

        cmd = ["sudo", "cp", "-R", "/var/log/aws/clusters", os.path.join(output_path,"var_log_aws_clusters")]
        run_subprocess_wrap(cmd, print_output=False)

        cmd = ["sinfo"]
        run_subprocess_wrap(cmd, print_output=False, to_file=os.path.join(output_path, "sinfo.log"))

        cmd = ["sinfo", "-R"]
        run_subprocess_wrap(cmd, print_output=False, to_file=os.path.join(output_path, "sinfo-R.log"))

        cmd = ["systemctl", "status", "slurmctld"]
        run_subprocess_wrap(cmd, print_output=False, to_file=os.path.join(output_path, "slurmctld_status.log"))

    else:

        cmd = ["systemctl", "status", "slurmd"]
        run_subprocess_wrap(cmd, print_output=False, to_file=os.path.join(output_path, "slurmd_status.log"))



    cmd = ["cp", "/var/log/syslog", os.path.join(output_path,"var_log")]
    run_subprocess_wrap(cmd, print_output=False)

    cmd = ["cp", "/var/log/kern.log", os.path.join(output_path,"var_log")]
    run_subprocess_wrap(cmd, print_output=False)

    cmd = ["sudo", "cp", "-R", "/var/log/slurm", os.path.join(output_path,"var_log_slurm")]
    run_subprocess_wrap(cmd, print_output=False)


if __name__ == "__main__":

    argparser = argparse.ArgumentParser( description="HyperPod issue report data capturing tool" )
    argparser.add_argument('--capture-single-node', action="store_true", help="Capture reporting data from a current single node")
    argparser.add_argument('--head-node', action="store_true", help="Capture head node specific data")
    argparser.add_argument('--output-path', action="store", required=True, help="Directory path for output files")

    args = argparser.parse_args()
    if args.capture_single_node:
        capture(args)
    else:
        main(args)
