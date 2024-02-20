import os
import time
import re
import subprocess

import boto3


def split_s3_path( s3_path ):
    re_pattern_s3_path = "s3://([^/]+)/(.*)"
    re_result = re.match( re_pattern_s3_path, s3_path )
    bucket = re_result.group(1)
    key = re_result.group(2)
    key = key.rstrip("/")
    return bucket, key


def create_random_big_file(filename, size):

    with open(filename,"wb") as fd:
        fd.truncate(size)


def upload_by_awscli_s3_cp( filename, s3_path ):

    print(f"Uploading {filename} to {s3_path} by `aws s3 cp` command")

    t0 = time.time()
    subprocess.run(["aws", "s3", "cp", filename, s3_path], check=True )
    t1 = time.time()

    print(f"Time spent : {t1-t0}")


def upload_by_boto3_client( filename, s3_path ):

    print(f"Uploading {filename} to {s3_path} by boto3 s3 client")

    s3_client = boto3.client("s3")
    bucket, key = split_s3_path(s3_path)

    t0 = time.time()
    s3_client.upload_file( filename, bucket, key )
    t1 = time.time()

    print(f"Time spent : {t1-t0}")


def upload_by_boto3_resource( filename, s3_path ):

    print(f"Uploading {filename} to {s3_path} by boto3 s3 client")

    s3_resource = boto3.resource("s3")
    bucket_name, key = split_s3_path(s3_path)

    t0 = time.time()
    s3_resource.Bucket(bucket_name).upload_file(filename, key)
    t1 = time.time()

    print(f"Time spent : {t1-t0}")


def main():

    local_filename = "./large.bin"
    s3_path = "s3://shimomut-files-us-east-2-842413447717/tmp/" + os.path.basename(local_filename)
    file_size = 1024 * 1024 * 1024 # 1GB

    create_random_big_file("./large.bin", file_size)

    upload_by_awscli_s3_cp( local_filename, s3_path )
    upload_by_boto3_client(local_filename, s3_path)
    upload_by_boto3_resource(local_filename, s3_path)


if __name__ == "__main__":
    main()
