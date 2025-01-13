import os
import io
import csv
import datetime
import re
import time
import subprocess


nodes = [
    "ip-10-1-66-116",
    "ip-10-1-43-172",
    "ip-10-1-0-197",
    "ip-10-1-33-157",
    "ip-10-1-56-126",
    "ip-10-1-7-212",
    "ip-10-1-102-222",
    "ip-10-1-56-240",
    "ip-10-1-23-33",
    "ip-10-1-16-175",
    "ip-10-1-43-100",
    "ip-10-1-44-81",
    "ip-10-1-122-103",
    "ip-10-1-52-114",
    "ip-10-1-109-147",
    "ip-10-1-49-94",
    "ip-10-1-2-183",
    "ip-10-1-125-148",
    "ip-10-1-99-136",
    "ip-10-1-115-248",
    "ip-10-1-91-201",
    "ip-10-1-72-74",
    "ip-10-1-32-120",
    "ip-10-1-81-188",
    "ip-10-1-42-92",
    "ip-10-1-40-230",
    "ip-10-1-54-8",
    "ip-10-1-91-206",
    "ip-10-1-6-101",
    "ip-10-1-111-115",
    "ip-10-1-4-109",
    "ip-10-1-94-104",
]

timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
output_dirname = f"./output-{timestamp}"

os.makedirs(output_dirname)

fsx_suffix = "-48TB"
weka_suffix = "-i3en.6xlarge_x24"

class TestConfig:
    def __init__(self, filesystem_type, block_size, transfer_size, num_nodes, num_processes ):

        self.filesystem_type = filesystem_type
        
        if filesystem_type=="fsx-250MB" + fsx_suffix:
            self.datadir = "/fsx1/ubuntu/ior-data/"
        elif filesystem_type=="fsx-500MB" + fsx_suffix:
            self.datadir = "/fsx2/ubuntu/ior-data/"
        elif filesystem_type=="fsx-1000MB" + fsx_suffix:
            self.datadir = "/fsx3/ubuntu/ior-data/"
        elif filesystem_type=="weka" + weka_suffix:
            self.datadir = "/mnt/weka/ior-data/"
        else:
            assert False

        self.block_size = block_size
        self.transfer_size = transfer_size
        self.num_nodes = num_nodes
        self.num_processes = num_processes

        self.result_filename = f"result-{filesystem_type}-{block_size}-{transfer_size}-{num_nodes}-{num_processes}.txt"


tests = []

if 1:
    for filesystem_type in [ 
        "fsx-250MB" + fsx_suffix,
        "fsx-500MB" + fsx_suffix,
        "fsx-1000MB" + fsx_suffix,
        "weka" + weka_suffix,
    ]:
        for block_size, transfer_size in [
            ("16M", "4K"),
            ("32M", "64K"),
            ("64M", "1M"),
            ("128M", "16M"),
        ]:
            for num_nodes, num_processes in [ 
                    (1, 1), (2, 2), (4, 4), (8, 8),
                    (16, 16), (32, 32), (32, 64), (32, 128),
                    (32, 256), (32, 512),
            ]:
                tests.append( TestConfig(filesystem_type, block_size, transfer_size, num_nodes, num_processes) )


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



with open( f"result-{timestamp}.csv", "w", newline="" ) as csvfile:

    csv_writer = csv.writer(csvfile)

    csv_writer.writerow(
        [
            "filesystem_type",
            "block_size",
            "transfer_size",
            "num_nodes",
            "num_processes",
            "read_bw_mean",
            "write_bw_mean"
        ]
    )

    for test_config in tests:

        hosts = ",".join(nodes[:test_config.num_nodes])


        # My options
        cmd = [
            "mpirun", "--oversubscribe", "-np", str(test_config.num_processes),
            "--host", hosts,
            "ior", 
            "-a", "POSIX",
            "-F", "-w", "-r", "-k", "-C",
            "-t", test_config.transfer_size, 
            "-b", test_config.block_size, 
            "-O", "useO_DIRECT=1", 
            "-i", "3", 
            "-d", "1", 
            "-o", test_config.datadir
        ]

        """
        # recommendation from the partner team, minus "-v" options
        # "--posix.odirect" didn't work, so replaced with "-a POSIX -O useO_DIRECT=1"
        # See also: https://ior.readthedocs.io/en/latest/userDoc/options.html
        cmd = [
            "mpirun", "--oversubscribe", "-np", str(test_config.num_processes),
            "--host", hosts,
            "ior",
            "-a", "POSIX",
            "-O", "useO_DIRECT=1", 
            "-t", test_config.transfer_size, 
            "-b", test_config.block_size, 
            "-F", "-g", "-w", "-r", "-i", "3", "-e", "-C", "-D", "0",
            "-o", test_config.datadir
        ]
        """

        print("Running command:", cmd)

        output_filename = os.path.join(output_dirname, test_config.result_filename)

        output = run_subprocess_wrap(cmd, print_output=True, to_file=output_filename, raise_non_zero_retcode=True )

        found_summary = False
        for line in output.splitlines():
            
            if not found_summary:
                if "Summary of all tests:" in line:
                    found_summary = True
                continue

            else:
                re_result = re.match(r"write[ ]+([0-9.]+)[ ]+([0-9.]+)[ ]+([0-9.]+).*", line)
                if re_result:
                    write_bw_mean = re_result.group(3)
                    continue

                re_result = re.match(r"read[ ]+([0-9.]+)[ ]+([0-9.]+)[ ]+([0-9.]+).*", line)
                if re_result:
                    read_bw_mean = re_result.group(3)

        csv_writer.writerow(
            [
                test_config.filesystem_type,
                test_config.block_size,
                test_config.transfer_size,
                test_config.num_nodes,
                test_config.num_processes,
                read_bw_mean,
                write_bw_mean
            ]
        )

        csvfile.flush()
