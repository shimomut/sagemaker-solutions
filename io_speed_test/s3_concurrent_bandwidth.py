import os
import time
import re
import io
import random
import statistics
import tempfile
import subprocess
import concurrent.futures

import boto3
from boto3.s3.transfer import TransferConfig


class Config:

    #region = "us-west-2"
    region = "ap-southeast-2"

    if region=="us-west-2":
        s3_location = "s3://shimomut-files/tmp/"
    elif region=="ap-southeast-2":
        s3_location = "s3://shimomut-files-ap-southeast-2/tmp/"
    else:
        assert False

    #concurrent_executor = "thread"
    concurrent_executor = "process"

    if 0:
        file_size = 10 * 1024 * 1024 # 10 MB
        num_files = 10
        max_workers = 4
        s3_transfer_config = None
    elif 0:
        file_size = 1024 * 1024 * 1024 # 1 GB
        num_files = 4
        max_workers = 1
        s3_transfer_config = None
    elif 0:
        file_size = 1024 * 1024 * 1024 # 1 GB
        num_files = 10
        max_workers = 4
        s3_transfer_config = None
    elif 0:
        file_size = 100 * 1024 * 1024 # 100 MB
        num_files = 100
        max_workers = 64
        s3_transfer_config = None
        # -> 4MB/s
    elif 0:
        file_size = 100 * 1024 * 1024 # 100 MB
        num_files = 100
        max_workers = 32
        s3_transfer_config = None
        # -> 10.9MB/s
    elif 0:
        file_size = 100 * 1024 * 1024 # 100 MB
        num_files = 100
        max_workers = 16
        s3_transfer_config = None
        # -> 31 MB/s
    elif 0:
        file_size = 100 * 1024 * 1024 # 100 MB
        num_files = 100
        max_workers = 8
        s3_transfer_config = None
        # -> 60 ~ 65 MB/s
    elif 0:
        file_size = 1024 * 1024 * 1024 # 1 GB
        num_files = 8
        max_workers = 8
        s3_transfer_config = None
        # -> 64 MB/s
    elif 1:
        file_size = 1024 * 1024 * 1024 # 1 GB
        num_files = 8
        max_workers = 4
        s3_transfer_config = None
        # -> 94~132 MB/s
        # なぜか -N 2 の時の方が速い

    @staticmethod
    def print():

        print(f"region : {Config.region}")
        print(f"s3_location : {Config.s3_location}")
        print(f"concurrent_executor : {Config.concurrent_executor}")
        print(f"file_size : {Config.file_size}")
        print(f"num_files : {Config.num_files}")
        print(f"max_workers : {Config.max_workers}")
        print(f"s3_transfer_config : {Config.s3_transfer_config}")
        print("SLURM_NODEID:",os.environ["SLURM_NODEID"])


def split_s3_path( s3_path ):
    re_pattern_s3_path = "s3://([^/]+)/(.*)"
    re_result = re.match( re_pattern_s3_path, s3_path )
    bucket = re_result.group(1)
    key = re_result.group(2)
    key = key.rstrip("/")
    return bucket, key


def get_file_size_string(size):

    for unit in ['B', 'KB', 'MB', 'GB', 'TB', 'PB']:
        if size < 1024 or unit=='PB':
            break
        size //= 1024
    return f"{size}{unit}"


class App:

    _s3_resoruce = None
    _src_buffer = None

    @staticmethod
    def init_worker(src_buffer):
        print("Initializing worker thread/process")
        assert isinstance(src_buffer,bytes)
        App._src_buffer = src_buffer
        App._s3_resoruce = boto3.resource("s3")


    @staticmethod
    def get_s3_resource():
        assert App._s3_resoruce
        return App._s3_resoruce


    @staticmethod
    def get_src_buffer():
        assert App._src_buffer
        return App._src_buffer


    @staticmethod
    def upload_single_file(s3_path):

        print(f"Uploading to {s3_path}")

        s3_resource = App.get_s3_resource()

        buffer = io.BytesIO(App.get_src_buffer())
        bucket_name, key = split_s3_path(s3_path)

        params = {
            "Fileobj" : buffer,
            "Key" : key,
        }

        if Config.s3_transfer_config:
            params["Config"] = Config.s3_transfer_config

        t0 = time.time()

        s3_resource.Bucket(bucket_name).upload_fileobj(**params)

        t1 = time.time()

        single_speed = Config.file_size / (t1-t0)

        return single_speed


    @staticmethod
    def download_single_file(s3_path):

        print(f"Downloading {s3_path}")

        s3_resource = App.get_s3_resource()

        buffer = io.BytesIO()
        bucket_name, key = split_s3_path(s3_path)

        params = {
            "Key" : key,
            "Fileobj" : buffer,
        }

        if Config.s3_transfer_config:
            params["Config"] = Config.s3_transfer_config

        t0 = time.time()

        s3_resource.Bucket(bucket_name).download_fileobj(key,buffer,Config=Config.s3_transfer_config)

        t1 = time.time()

        single_speed = Config.file_size / (t1-t0)

        return single_speed


    def main(self):

        Config.print()

        if 1:
            print("Creating random bytes")
            src_buffer = io.BytesIO()
            size_wrote = 0
            while size_wrote < Config.file_size:
                size_left = Config.file_size-size_wrote
                size_to_write = min(size_left, 100 * 1024 * 1024)
                size_wrote += src_buffer.write( random.randbytes(size_to_write) )
        else:
            src_buffer = io.BytesIO()

    
        prefix_file_size = get_file_size_string(Config.file_size)
        node_id = int(os.environ["SLURM_NODEID"])

        s3_paths = [ Config.s3_location + f"{prefix_file_size}_{node_id:03d}_{i:04d}.bin" for i in range(Config.num_files) ]


        def run_and_measure( subject, func, input ):

            if Config.concurrent_executor=="thread":
                PoolExecuterClass = concurrent.futures.ThreadPoolExecutor
            elif Config.concurrent_executor=="process":
                PoolExecuterClass = concurrent.futures.ProcessPoolExecutor

            t0 = time.time()

            with PoolExecuterClass(max_workers=Config.max_workers, initializer=App.init_worker, initargs=[src_buffer.getvalue()]) as pool_executer:
                map_result = pool_executer.map(
                    func,
                    input
                )

                map_result = list(map_result)
                assert len(map_result)==len(input)

            t1 = time.time()

            quantiles = statistics.quantiles(map_result, n=10)
            print(f"{subject} : bandwidth p10 : {quantiles[0] / (1024*1024)} MB/s")
            print(f"{subject} : bandwidth p50 : {quantiles[4] / (1024*1024)} MB/s")
            print(f"{subject} : bandwidth p90 : {quantiles[-1] / (1024*1024)} MB/s")


        #run_and_measure("Upload to S3 with Boto3", App.upload_single_file, s3_paths)
        run_and_measure("Download from S3 with Boto3", App.download_single_file, s3_paths)


if __name__ == "__main__":
    app = App()
    app.main()
    