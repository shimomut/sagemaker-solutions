import os
import time
import re
import io
import random
import tempfile
import subprocess
import concurrent.futures

import boto3
from boto3.s3.transfer import TransferConfig


class Config:

    s3_location = "s3://shimomut-files-vpce-us-east-2-842413447717/tmp/"
    fsx_location = "/fsx/ubuntu/tmp"
    tmp_location = "/opt/dlami/nvme"

    #concurrent_executor = "thread"
    concurrent_executor = "process"

    #s5cmd_concurrency = 10
    s5cmd_concurrency = 100

    if 0:
        file_size = 10 * 1024 * 1024 # 100 MB
        num_files = 10
        max_workers = 4
        s3_transfer_config = None
    elif 0:
        file_size = 100 * 1024 * 1024 # 100 MB
        num_files = 10
        max_workers = 10
        s3_transfer_config = None
    elif 0:
        file_size = 1024 * 1024 * 1024 # 1 GB
        num_files = 10
        max_workers = 1
        s3_transfer_config = None
    elif 0:
        file_size = 1024 * 1024 * 1024 # 1 GB
        num_files = 10
        max_workers = 10
        s3_transfer_config = None
    elif 0:
        file_size = 100 * 1024 * 1024 # 100 MB
        num_files = 100
        max_workers = 10
        s3_transfer_config = None
    elif 0:
        file_size = 1024 * 1024 * 1024 # 1 GB
        num_files = 100
        max_workers = 1
        s3_transfer_config = None
    elif 0:
        file_size = 1024 * 1024 * 1024 # 1 GB
        num_files = 100
        max_workers = 10
        s3_transfer_config = None
    elif 0:
        file_size = 1024 * 1024 * 1024 # 1 GB
        num_files = 100
        max_workers = 20
        s3_transfer_config = None
    elif 0:
        file_size = 1024 * 1024 * 1024 # 1 GB
        num_files = 100
        max_workers = 30
        s3_transfer_config = None
    elif 0:
        file_size = 100 * 1024 * 1024 # 100 MB
        num_files = 100
        max_workers = 30
        s3_transfer_config = None
    elif 0:
        file_size = 100 * 1024 * 1024 # 100 MB
        num_files = 100
        max_workers = 10
        s3_transfer_config = TransferConfig(
            max_concurrency = 10,
            multipart_threshold = 10 * 1024 * 1024,
            multipart_chunksize = 10 * 1024 * 1024
            )
    elif 1:
        file_size = 50 * 1024 * 1024 * 1024 # 50 GB
        num_files = 1
        max_workers = 1
        s3_transfer_config = None

    @staticmethod
    def print():

        print(f"s3_location : {Config.s3_location}")
        print(f"fsx_location : {Config.fsx_location}")
        print(f"tmp_location : {Config.tmp_location}")
        print(f"concurrent_executor : {Config.concurrent_executor}")
        print(f"s5cmd_concurrency : {Config.s5cmd_concurrency}")
        print(f"file_size : {Config.file_size}")
        print(f"num_files : {Config.num_files}")
        print(f"max_workers : {Config.max_workers}")
        print(f"s3_transfer_config : {Config.s3_transfer_config}")


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

        s3_resource.Bucket(bucket_name).upload_fileobj(**params)

        return s3_path


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

        s3_resource.Bucket(bucket_name).download_fileobj(key,buffer,Config=Config.s3_transfer_config)

        return s3_path


    @staticmethod
    def download_single_file_with_awscli_crt(s3_path):

        print(f"Downloading {s3_path} with AWSCLI(CRT)")

        with tempfile.TemporaryDirectory(dir=Config.tmp_location) as tmp_dir:
            tmp_filename = os.path.join(tmp_dir, os.path.basename(s3_path))
            subprocess.run(["aws", "s3", "cp", s3_path, tmp_filename ])


    @staticmethod
    def download_single_file_with_s5cmd(s3_path):

        print(f"Downloading {s3_path} with s5cmd")

        with tempfile.TemporaryDirectory(dir=Config.tmp_location) as tmp_dir:
            tmp_filename = os.path.join(tmp_dir, os.path.basename(s3_path))
            subprocess.run(["s5cmd", "cp", "--concurrency", f"{Config.s5cmd_concurrency}", s3_path, tmp_filename ])

        return s3_path


    @staticmethod
    def write_single_file(fsx_path):

        print(f"Writing to {fsx_path}")

        with open( fsx_path, "wb" ) as fd:
            fd.write(App.get_src_buffer())

        return fsx_path


    @staticmethod
    def read_single_file(fsx_path):

        print(f"Reading {fsx_path}")

        with open( fsx_path, "rb" ) as fd:
            d = fd.read()

        assert len(d)==Config.file_size

        return fsx_path


    def main(self):

        Config.print()

        print("Creating random bytes")
        src_buffer = io.BytesIO()
        size_wrote = 0
        while size_wrote < Config.file_size:
            size_left = Config.file_size-size_wrote
            size_to_write = min(size_left, 100 * 1024 * 1024)
            size_wrote += src_buffer.write( random.randbytes(size_to_write) )

    
        prefix_file_size = get_file_size_string(Config.file_size)
        s3_paths = [ Config.s3_location + f"{prefix_file_size}_{i:04d}.bin" for i in range(Config.num_files) ]
        fsx_paths = [ os.path.join( Config.fsx_location, f"{prefix_file_size}_{i:04d}.bin" ) for i in range(Config.num_files) ]

        os.makedirs(Config.fsx_location, exist_ok=True)


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

            print(f"{subject} : Time spent : {t1-t0}")
            print(f"{subject} : Bandwidth  : {(Config.file_size * Config.num_files) /(t1-t0) / (1024*1024)} MB/s")


        run_and_measure("Upload to S3 with Boto3", App.upload_single_file, s3_paths)
        run_and_measure("Download from S3 with Boto3", App.download_single_file, s3_paths)
        run_and_measure("Download from S3 with AWSCLI(CRT)", App.download_single_file_with_awscli_crt, s3_paths)
        run_and_measure("Download from S3 with s5cmd", App.download_single_file_with_s5cmd, s3_paths)
        run_and_measure("Write to FSx", App.write_single_file, fsx_paths)
        run_and_measure("Read from FSx", App.read_single_file, fsx_paths)


if __name__ == "__main__":
    app = App()
    app.main()
    