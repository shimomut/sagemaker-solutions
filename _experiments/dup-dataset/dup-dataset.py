import os
import concurrent.futures

dir = "/fsx2/dataset-loading-perf/datasets/train"
src = "dataset.json"
dst_pattern = "dataset_%08d.json"
num_dup = 1000 * 1000
num_workers = 16 * 16

with open( os.path.join(dir,src), "rb" ) as fd:
    d = fd.read()

with concurrent.futures.ThreadPoolExecutor(max_workers=num_workers) as thread_pool:

    def create_dst_file(i):
        dst = os.path.join(dir, dst_pattern % i)
        print(f"Writing {dst}")
        with open( dst, "wb" ) as fd:
            fd.write(d)

    for result in thread_pool.map(create_dst_file, range(num_dup)):
        pass

