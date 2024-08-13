import time
import subprocess
import re
import argparse
import getpass
import io


if getpass.getuser() == "root":
    sudo_command = []
else:
    sudo_command = ["sudo","-E"]


#node_status_to_trigger_replacement = "fail"
node_status_to_trigger_replacement = "down"


class ProgressDots:

    def __init__(self):
        self.status = None

    def tick(self,status):

        if self.status != status:

            # first line doesn't require line break
            if self.status is not None:
                print()

            self.status = status

            # print new status if not ending
            if self.status is not None:
                print(self.status, end=" ", flush=True)

            return

        # print dots if status didn't change
        if self.status is not None:
            print(".", end="", flush=True)


def run_subprocess_wrap(cmd, print_output=True):

    captured_stdout = io.StringIO()

    p = subprocess.Popen( cmd, bufsize=1, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT )
    for line in iter(p.stdout.readline, ""):
        captured_stdout.write(line)
        if print_output:
            print( line, end="", flush=True )
    p.wait()

    if p.returncode != 0:
        raise ChildProcessError(f"Subprocess {cmd} returned non-zero exit code {p.returncode}.")
    
    return captured_stdout.getvalue()    


def trigger_replacement(hostname):

    print(f"Triggering instance replacement")

    run_subprocess_wrap([*sudo_command, "scontrol", "update", f"node={hostname}", f"state={node_status_to_trigger_replacement}", 'reason="Action:Replace"'], print_output=False)


def wait_for_replacement_completion(hostname):

    status_message = "Instance replacement in-progress"

    progress_dots = ProgressDots()

    while True:
        
        status = None
        captured_output = run_subprocess_wrap(["sinfo", "--node", hostname], print_output=False)
        for line in captured_output.splitlines():
            re_result = re.match(r"([^\s]+)\s+([^\s]+)\s+([^\s]+)\s+([^\s]+)\s+([^\s]+)\s+([^\s]+)", line)
            if re_result and re_result.group(6)==hostname:
                status = re_result.group(5)

        if status=="idle":
            break

        progress_dots.tick(status_message)

        time.sleep(10)

    progress_dots.tick(None)


def drain_node(hostname):

    print(f"Changing the node to drain status")

    run_subprocess_wrap([*sudo_command, "scontrol", "update", f"node={hostname}", "state=drain", 'reason="Replaced"'], print_output=False)


def replace_and_drain(hostname):

    trigger_replacement(hostname)
    wait_for_replacement_completion(hostname)
    drain_node(hostname)

    print("Done.")



if __name__ == "__main__":

    argparser = argparse.ArgumentParser( description = 'Replace an instance and set it to drain status' )
    argparser.add_argument('hostname', metavar="HOSTNAME", action="store", help="Hostname to replace (e.g. ip-10.0.12.34)")
    args = argparser.parse_args()
    replace_and_drain(args.hostname)


