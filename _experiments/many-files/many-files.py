import os
import time
import glob
import concurrent.futures

if 0:
    pool_executor = concurrent.futures.ThreadPoolExecutor
else:
    pool_executor = concurrent.futures.ProcessPoolExecutor

if 0:
    dir = "/fsx2/many-files"
    src = "./dataset.json"
    dst_pattern = "dataset_%08d.json"
    dst_glob_pattern = "dataset_*.json"
    num_dup = 1000 * 1000
    num_workers = 1024

if 1:
    dir = "/mnt/weka/many-files"
    src = "./dataset.json"
    dst_pattern = "dataset_%08d.json"
    dst_glob_pattern = "dataset_*.json"
    num_dup = 1000 * 1000
    num_workers = 1024



with open( os.path.join(src), "rb" ) as fd:
    d = fd.read()


class TimeMeasure:
    def __init__(self, name):
        self.name = name
        print(f"Starting {self.name}")
        self.t0 = time.time()

    def end(self):
        self.t1 = time.time()
        print(f"Ended {self.name}")

    def print_elapsed_time(self):
        print(f"Elapsed time {self.name}: {self.t1 - self.t0}")


def trace(s):
    #print(s)
    pass


# -----

thread_pool = concurrent.futures.ThreadPoolExecutor(max_workers=num_workers)

def warmup(i):
    trace(f"Warming up {i}")

for result in thread_pool.map(warmup, range(num_dup)):
    pass


# -----

t_create = TimeMeasure("Creating many files")

def create_dst_file(i):
    dst = os.path.join(dir, dst_pattern % i)
    trace(f"Writing {dst}")
    with open( dst, "wb" ) as fd:
        fd.write(d)

for result in thread_pool.map(create_dst_file, range(num_dup)):
    pass

t_create.end()


# -----

t_list = TimeMeasure("Listing all files")

filenames = glob.glob( os.path.join(dir, dst_glob_pattern))

t_list.end()


# -----

t_stat = TimeMeasure("Getting stats of all files")

def get_stat(filename):
    st = os.stat(filename)
    trace(f"Timestamp of {filename}: {st.st_mtime}")

for result in thread_pool.map(get_stat, filenames):
    pass

t_stat.end()


# -----

t_read = TimeMeasure("Reading all files")

def read_file(filename):
    with open(filename) as fd:
        d = fd.read()
        trace(f"Length of {filename}: {len(d)}")

for result in thread_pool.map(read_file, filenames):
    pass

t_read.end()


# -----

t_delete = TimeMeasure("Deleting all files")

def delete_file(i):
    dst = os.path.join(dir, dst_pattern % i)
    if os.path.exists(dst):
        trace(f"Deleting {dst}")
        os.unlink(dst)

for result in thread_pool.map(delete_file, range(num_dup)):
    pass

t_delete.end()


# -----

t_create.print_elapsed_time()
t_list.print_elapsed_time()
t_stat.print_elapsed_time()
t_read.print_elapsed_time()
t_delete.print_elapsed_time()
