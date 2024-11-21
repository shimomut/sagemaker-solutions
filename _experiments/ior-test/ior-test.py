import os
import io
import csv
import datetime
import re
import subprocess


nodes = ["ip-10-1-28-215", "ip-10-1-96-7", "ip-10-1-103-173", "ip-10-1-124-115"]

timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
output_dirname = f"./output-{timestamp}"

os.makedirs(output_dirname)


class TestConfig:
    def __init__(self, filesystem_type, file_size, transfer_size, num_nodes, num_processes ):

        self.filesystem_type = filesystem_type
        
        if filesystem_type=="fsx":
            self.datadir = "/fsx_p2/shimomut/fio-test"
        elif filesystem_type=="weka":
            self.datadir = "/mnt/weka/shimomut/fio-test"
        else:
            assert False

        self.file_size = file_size
        self.transfer_size = transfer_size
        self.num_nodes = num_nodes
        self.num_processes = num_processes

        self.result_filename = f"result-{filesystem_type}-{file_size}-{transfer_size}-{num_nodes}-{num_processes}.txt"


tests = []
for file_size, transfer_size in [ ("128M", "4K"), ("512M", "1M"), ("2G", "256M") ]:
    for num_nodes, num_processes in [ 
            (1, 1), (2, 2), (4, 4), (4, 8), (4, 16), (4, 32), (4, 64), (4, 128), (4, 256)
        ]:
        for filesystem_type in [ "fsx", "weka" ]:
            tests.append( TestConfig(filesystem_type, file_size, transfer_size, num_nodes, num_processes) )


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
            "num_processes",
            "read_bw_mean",
            "write_bw_mean"
        ]
    )

    for test_config in tests:

        hosts = ",".join(nodes[:test_config.num_nodes])

        cmd = [
            "mpirun", "--oversubscribe", "-np", str(test_config.num_processes),
            "--host", hosts,
            "ior", 
            "-a", "POSIX",
            "-F", "-w", "-r", "-k", "-C",
            "-t", test_config.transfer_size, 
            "-b", test_config.file_size, 
            "-O", "useO_DIRECT=1", 
            "-i", "3", 
            "-d", "1", 
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
                test_config.file_size,
                test_config.transfer_size,
                test_config.num_nodes,
                test_config.num_processes,
                read_bw_mean,
                write_bw_mean
            ]
        )

        csvfile.flush()
