import argparse
import pprint
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


def scaleup_with_loop(cluster_name, instance_group_name, target_instance_count, increment_by):
    
    sagemaker_client = boto3.client("sagemaker")
    
    def construct_new_instance_groups_config():

        cluster_desc = sagemaker_client.describe_cluster(ClusterName=cluster_name)

        new_instance_groups = []
        instance_group_found = False

        for instance_group in cluster_desc["InstanceGroups"]:
            if instance_group["InstanceGroupName"]==instance_group_name:
                if instance_group["CurrentCount"] >= target_instance_count:
                    print("Scaling up finished")
                    return None
                current_instance_count = instance_group["CurrentCount"]
                next_target_instance_count = min(current_instance_count + increment_by, target_instance_count)
                print(f"Scaling up {instance_group_name} from {current_instance_count} to {next_target_instance_count}")
                instance_group_found = True
            else:
                next_target_instance_count = instance_group["CurrentCount"]

            new_instance_groups.append(
                {
                    "InstanceGroupName": instance_group["InstanceGroupName"],
                    "InstanceType": instance_group["InstanceType"],
                    "InstanceCount": next_target_instance_count,
                    "LifeCycleConfig": instance_group["LifeCycleConfig"],
                    "ExecutionRole": instance_group["ExecutionRole"],
                    "ThreadsPerCore": instance_group["ThreadsPerCore"],
                }
            )
        
        assert instance_group_found, f"Instance group [{instance_group_name}] not found"

        pprint.pprint(new_instance_groups)

        return new_instance_groups

    def start_scaleup_single_step(new_instance_groups):

        sagemaker_client.update_cluster(ClusterName=cluster_name, InstanceGroups=new_instance_groups )


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
            print(f"Failure message : {cluster_desc["FailureMessage"]}")

    # ---

    wait_cluster_status()
    while True:
        new_instance_groups = construct_new_instance_groups_config()
        if new_instance_groups is None:
            break
        start_scaleup_single_step(new_instance_groups)
        wait_cluster_status()


if __name__ == "__main__":

    argparser = argparse.ArgumentParser(description="Scale up a HyperPod cluster incrementally by the specified step")
    argparser.add_argument("--cluster-name", action="store", required=True, help="Name of cluster to scale up")
    argparser.add_argument("--instance-group-name", action="store", required=True, help="Instance group name to scale up")
    argparser.add_argument("--target-instance-count", action="store", type=int, required=True, help="Target instance count")
    argparser.add_argument("--increment-by", action="store", type=int, required=True, help="Number of instances to add at each step")
    args = argparser.parse_args()

    scaleup_with_loop( args.cluster_name, args.instance_group_name, args.target_instance_count, args.increment_by )
