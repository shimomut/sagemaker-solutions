import os
import time
import re
import io
import random
import concurrent.futures

import boto3
from boto3.s3.transfer import TransferConfig


class Config:

    s3_location = "s3://shimomut-files-vpce-us-east-2-842413447717/tmp/"
    fsx_location = "/fsx/ubuntu/tmp"

    if 1:
        file_size = 100 * 1024 * 1024 # 100 MB
        num_files = 10
        max_workers = 10
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


def split_s3_path( s3_path ):
    re_pattern_s3_path = "s3://([^/]+)/(.*)"
    re_result = re.match( re_pattern_s3_path, s3_path )
    bucket = re_result.group(1)
    key = re_result.group(2)
    key = key.rstrip("/")
    return bucket, key


def main():

    print("Creating random bytes")
    src_buffer = io.BytesIO()
    size_wrote = 0
    while size_wrote < Config.file_size:
        size_left = Config.file_size-size_wrote
        size_to_write = min(size_left, 100 * 1024 * 1024)
        size_wrote += src_buffer.write( random.randbytes(size_to_write) )
    
    s3_paths = [ Config.s3_location + "large_%04d.bin" % i for i in range(Config.num_files) ]
    fsx_paths = [ os.path.join( Config.fsx_location, ("large_%04d.bin" % i) ) for i in range(Config.num_files) ]

    os.makedirs(Config.fsx_location, exist_ok=True)

    #s3_client = boto3.client("s3")
    s3_resource = boto3.resource("s3")


    def run_and_measure( subject, func, input ):

        t0 = time.time()

        thread_pool = concurrent.futures.ThreadPoolExecutor(max_workers=Config.max_workers)
        map_result = thread_pool.map(
            func,
            input
        )

        map_result = list(map_result)
        assert len(map_result)==len(input)

        t1 = time.time()

        print(f"{subject} : Time spent : {t1-t0}")
        print(f"{subject} : Bandwidth  : {(Config.file_size * Config.num_files) /(t1-t0) / (1024*1024)} MB/s")


    # --------------
    # Upload to S3

    def upload_single_file(s3_path):

        print(f"Uploading to {s3_path}")

        buffer = io.BytesIO(src_buffer.getvalue())
        bucket_name, key = split_s3_path(s3_path)

        params = {
            "Fileobj" : buffer,
            "Key" : key,
        }

        if Config.s3_transfer_config:
            params["Config"] = Config.s3_transfer_config

        s3_resource.Bucket(bucket_name).upload_fileobj(**params)

        return s3_path

    run_and_measure("Upload to S3", upload_single_file, s3_paths)

    # -----------------
    # Download from S3

    def download_single_file(s3_path):

        print(f"Downloading {s3_path}")

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

    run_and_measure("Download from S3", download_single_file, s3_paths)


    # --------------
    # Write to FSx

    def write_single_file(fsx_path):

        print(f"Writing to {fsx_path}")

        with open( os.path.join(Config.fsx_location, fsx_path), "wb" ) as fd:
            fd.write(src_buffer.getvalue())

        return fsx_path

    run_and_measure("Write to FSx", write_single_file, fsx_paths)


    # --------------
    # Read from FSx

    def read_single_file(fsx_path):

        print(f"Reading {fsx_path}")

        with open( os.path.join(Config.fsx_location, fsx_path), "rb" ) as fd:
            d = fd.read()

        assert len(d)==Config.file_size

        return fsx_path

    run_and_measure("Read from FSx", read_single_file, fsx_paths)



if __name__ == "__main__":
    main()
    