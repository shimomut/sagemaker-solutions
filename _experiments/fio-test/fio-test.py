import os
import io
import csv
import json
import datetime
import re
import time
import subprocess


nodes = [
    "ip-10-1-73-241",
    "ip-10-1-29-243",
    "ip-10-1-71-41",
    "ip-10-1-49-119",
    "ip-10-1-107-100",
    "ip-10-1-49-102",
    "ip-10-1-40-105",
    "ip-10-1-89-252",
    "ip-10-1-62-160",
    "ip-10-1-35-152",
    "ip-10-1-112-207",
    "ip-10-1-39-138",
    "ip-10-1-43-136",
    "ip-10-1-24-128",
    "ip-10-1-9-228",
    "ip-10-1-16-36",
]

timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
config_dirname = f"./config-{timestamp}"
output_dirname = f"./output-{timestamp}"

os.makedirs(config_dirname)
os.makedirs(output_dirname)

class TestConfig:

    def __init__(self, filesystem_type, file_size, transfer_size, num_nodes, num_jobs ):

        self.filesystem_type = filesystem_type
        
        if filesystem_type=="fsx":
            self.datadir = "/fsx2/fio-data/"
        elif filesystem_type=="weka":
            self.datadir = "/mnt/weka/fio-data/"
        else:
            assert False

        self.file_size = file_size
        self.transfer_size = transfer_size
        self.num_nodes = num_nodes
        self.num_jobs = num_jobs

    def __str__(self):
        return f"{self.filesystem_type}-{self.file_size}-{self.transfer_size}-{self.num_nodes}-{self.num_jobs}"


tests = []

if 1:
    for filesystem_type in [ 
        "fsx",
        "weka",
    ]:
        for file_size, transfer_size in [
            ("2G", "4K"),
            ("2G", "64K"),
            ("2G", "1M"),
            ("2G", "16M"),
            ("2G", "256M"),
        ]:
            for num_nodes, num_jobs in [ 
                (1, 1), (2, 1), (4, 1), (8, 1), (16, 1), 
                (16, 2), (16, 4), (16, 8), (16, 16), (16, 32),
            ]:
                tests.append( TestConfig(filesystem_type, file_size, transfer_size, num_nodes, num_jobs) )


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
            "file_size",
            "transfer_size",
            "num_nodes",
            "num_jobs",
            "read_bw_mean",
            "write_bw_mean"
        ]
    )

    for test_config in tests:

        print(f"Running test - {test_config}")

        hosts_filename = os.path.join(config_dirname, f"hosts-{test_config}.txt")
        config_filename = os.path.join(config_dirname, f"config-{test_config}.txt")
        output_filename = os.path.join(output_dirname, f"result-{test_config}.json")

        with open(hosts_filename, "w") as fd:
            fd.write("\n".join(nodes[:test_config.num_nodes]))            

        with open(config_filename, "w") as fd:
            d = [
                f"[global]",
                f"time_based=1",
                f"runtime=60",
                f"startdelay=5",
                f"exitall_on_error=1",
                f"group_reporting",
                f"clocksource=gettimeofday",
                f"disk_util=0",
                f"ioengine=libaio",
                #f"ioengine=posixaio",
                f"iodepth=1",
                f"direct=1",
                f"stonewall",
                f"filesize={test_config.file_size}",
                f"blocksize={test_config.transfer_size}",
                f"directory={test_config.datadir}",

                f"[test1]",
                f"readwrite=randrw",
                f"numjobs={test_config.num_jobs}",
            ]
            fd.write("\n".join(d))

        time.sleep(1)

        cmd = [
            "fio",
            f"--client={hosts_filename}",
            "--output-format=json",
            config_filename,
        ]

        output = run_subprocess_wrap(cmd, print_output=True, to_file=output_filename, raise_non_zero_retcode=True )

        found_summary = False
        result = json.loads(output)
        
        if len(result["client_stats"])==1:
            stats = result["client_stats"][0]
        else:
            stats = result["client_stats"][-1]
            assert stats["jobname"] == "All clients"

        write_bw_mean = stats["write"]["bw"]
        read_bw_mean = stats["read"]["bw"]

        csv_writer.writerow(
            [
                test_config.filesystem_type,
                test_config.file_size,
                test_config.transfer_size,
                test_config.num_nodes,
                test_config.num_jobs,
                read_bw_mean,
                write_bw_mean
            ]
        )

        csvfile.flush()
