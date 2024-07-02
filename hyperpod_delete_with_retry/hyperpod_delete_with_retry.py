import sys
import argparse
import time

import boto3


class ProgressDots:

    def __init__(self):
        self.status = None

    def tick(self,status):

        if self.status != status:

            # first line doesn't require line break
            if self.status is not None:
                print()

            self.status = status

            # print new status if not ending
            if self.status is not None:
                print(self.status, end=" ", flush=True)

            return

        # print dots if status didn't change
        if self.status is not None:
            print(".", end="", flush=True)


def delete_with_loop(cluster_name):
    
    sagemaker_client = boto3.client("sagemaker")
    
    def start_delete_attempt():

        sagemaker_client.delete_cluster(ClusterName=cluster_name)


    def wait_cluster_status():

        progress_dots = ProgressDots()

        while True:
            cluster_desc = sagemaker_client.describe_cluster(ClusterName=cluster_name)

            progress_dots.tick(cluster_desc["ClusterStatus"])

            if cluster_desc["ClusterStatus"] in ["InService","Failed"]:
                progress_dots.tick(None)
                break

            time.sleep(30)

        if "FailureMessage" in cluster_desc and cluster_desc["FailureMessage"]:

            failure_message = cluster_desc["FailureMessage"]

            print(f"Failure message : {failure_message}")

            if "DeleteNetworkInterface" not in failure_message:
                sys.exit(1)
            

    # ---

    try:
        wait_cluster_status()
        while True:
            start_delete_attempt()
            wait_cluster_status()
            time.sleep(60)
            
    except sagemaker_client.exceptions.ResourceNotFound:
        print("ResourceNotFound, likely deletion completed")
        sys.exit(0)

if __name__ == "__main__":

    argparser = argparse.ArgumentParser(description="Delete a HyperPod cluster by calling delete-cluster repeatedly")
    argparser.add_argument("--cluster-name", action="store", required=True, help="Name of cluster to delete")
    args = argparser.parse_args()

    delete_with_loop(args.cluster_name)
