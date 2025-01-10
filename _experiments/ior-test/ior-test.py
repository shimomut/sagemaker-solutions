import os
import io
import csv
import datetime
import re
import subprocess


nodes = [
    "ip-10-1-55-75",
    "ip-10-1-68-117",
    "ip-10-1-25-103",
    "ip-10-1-72-156",
    "ip-10-1-31-185",
    "ip-10-1-88-72",
    "ip-10-1-44-46",
    "ip-10-1-83-196",
    "ip-10-1-16-196",
    "ip-10-1-110-202",
    "ip-10-1-120-107",
    "ip-10-1-99-177",
    "ip-10-1-32-137",
    "ip-10-1-85-65",
    "ip-10-1-114-7",
    "ip-10-1-0-54",
    "ip-10-1-46-185",
    "ip-10-1-112-132",
    "ip-10-1-79-100",
    "ip-10-1-82-226",
    "ip-10-1-83-72",
    "ip-10-1-103-172",
    "ip-10-1-116-190",
    "ip-10-1-9-64",
    "ip-10-1-45-95",
    "ip-10-1-84-168",
    "ip-10-1-3-222",
    "ip-10-1-98-135",
    "ip-10-1-64-88",
    "ip-10-1-30-165",
    "ip-10-1-88-5",
    "ip-10-1-47-248",
]

timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
output_dirname = f"./output-{timestamp}"

os.makedirs(output_dirname)


class TestConfig:
    def __init__(self, filesystem_type, block_size, transfer_size, num_nodes, num_processes ):

        self.filesystem_type = filesystem_type
        
        if filesystem_type=="fsx":
            self.datadir = "/fsx/ubuntu/fio-test-data/"
        elif filesystem_type=="weka":
            self.datadir = "/mnt/weka/fio-test-data/"
        else:
            assert False

        self.block_size = block_size
        self.transfer_size = transfer_size
        self.num_nodes = num_nodes
        self.num_processes = num_processes

        self.result_filename = f"result-{filesystem_type}-{block_size}-{transfer_size}-{num_nodes}-{num_processes}.txt"


tests = []

# test-1: granularity x 3 variations, number of processes x 9 variations
if 1:
    for block_size, transfer_size in [ ("16M", "4K"), ("32M", "64K"), ("64M", "1M"), ("128M", "16M"), ("256M", "256M") ]:
        for num_nodes, num_processes in [ 
                (1, 1), (2, 2), (4, 4), (8, 8), (16, 16), (32, 32), (32, 64), (32, 128), (32, 256), (32, 512), (32, 1024)
            ]:
            for filesystem_type in [ "fsx", "weka" ]:
                tests.append( TestConfig(filesystem_type, block_size, transfer_size, num_nodes, num_processes) )


# test-2: number of processes x variations, granularity x 17, variations
if 0:
    for block_size, transfer_size in [ 
            ("128M", "4K"),  ("128M", "8K"),   ("128M", "16K"),  ("128M", "32K"),
            ("256M", "64K"), ("256M", "128K"), ("256M", "256K"), ("256M", "512K"),
            ("512M", "1M"),  ("512M", "2M"),   ("512M", "4M"),   ("512M", "8M"), 
            ("1G",   "16M"), ("1G", "32M"),    ("1G", "64M"),    ("1G", "128M"), 
        ]:
        for num_nodes, num_processes in [ 
                (8, 8), (8, 32), (8, 128)
            ]:
            for filesystem_type in [ "fsx", "weka" ]:
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

        # recommendation from the partner team, minus "-v" options
        # "--posix.odirect" didn't work, so replaced with "-a POSIX -O useO_DIRECT=1"
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
