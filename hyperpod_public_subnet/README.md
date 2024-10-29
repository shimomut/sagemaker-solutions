# Solution to create/run a HyperPod cluster in a public subnet


## Overview

Currently, HyperPod doesn't support creating a cluster in public subnet. 
The [developer guide document](https://docs.aws.amazon.com/sagemaker/latest/dg/sagemaker-hyperpod-eks-prerequisites.html) also 
states that “The type of the subnet in your VPC must be private for HyperPod clusters”.
If you actually try to create a HyperPod cluster in a public subnet, the cluster creation will take a long time, 
and it eventually fail. This is because EIPs are not automatically attached to ENIs.

This document describes how to work around this limitation using a helper script. The script has following commands:

1. Create and attach EIPs to ENIs for HyperPod instances
2. Switch the route table association of the subnet public ↔ private
3. Delete unused EIPs

Running these commands manually from your development machine (such as a local laptop) will allow you to switch the subnet for your HyperPod instances to public while maintaining internet access from the instances by attaching EIPs.


## How to use

#### Prerequisites and preparations

1. Create a CloudFormation stack from the HyperPod workshop template
1. Create a HyperPod cluster
1. Raise the quota for number of EIPs beforehand as-needed.
    - “Service Quotas” > “Amazon Elastic Compute Cloud (Amazon EC2)” > “EC2-VPC Elastic IPs”
1. Download [hyperpod_public_subnet.py](https://github.com/shimomut/sagemaker-solutions/blob/main/hyperpod_public_subnet/hyperpod_public_subnet.py) to your development machine
1. Configure config.py, referring to the [sample config file](https://github.com/shimomut/sagemaker-solutions/blob/main/hyperpod_public_subnet/_config.py), and put it next to the downloaded hyperpod_public_subnet.py.


#### How to switch to public

1. Run `create-and-attach-eips` command to create and attach EIPs

    ``` bash
    python3 hyperpod_public_subnet.py create-and-attach-eips
    ```

1. Run `switch-to-public` command to switch the route table association to public

    ``` bash
    python3 hyperpod_public_subnet.py switch-to-public
    ```

1. Confirm that the cluster nodes are `Ready` status

    ``` bash
    kubectl get nodes
    ```

1. Confirm your job runs
1. Check the NAT Gateway usage metrics and confirm it is not being used.


#### How to scale up the cluster

1. Raise the quota for number of EIPs beforehand as-needed.
    - “Service Quotas” > “Amazon Elastic Compute Cloud (Amazon EC2)” > “EC2-VPC Elastic IPs”
1. Trigger cluster scaling up
1. While cluster scaling up is taking time and being blocked due to missing EIPs, run `create-and-attach-eips` command to create and attach EIPs to ENIs for the new instances.
1. Wait until the cluster status changes to InService again.


#### How to replace instance

* No special treatment is needed for instance replacement. Existing ENIs are re-used when replacing instances.


#### How to clean up (after cluster scale-down or cluster deletion)

1. Run `delete-unused-eips` command to delete unused EIPs

    ``` bash
    python3 hyperpod_public_subnet.py delete-unused-eips
    ```

1. Open the EIP management console UI, and make sure EIPs were deleted.



## Script commands

```
$ python3 hyperpod_public_subnet.py --help         
  usage: hyperpod_public_subnet.py [-h] [--verbose]
    {create-and-attach-eips,delete-unused-eips,switch-to-public,switch-to-private,clean} ...
  
  HyperPod subnet public/private switching tool
  
  positional arguments:
    {create-and-attach-eips,delete-unused-eips,switch-to-public,switch-to-private,clean}
      create-and-attach-eips  Create and attach EIPs to ENIs if it is not done yet
      delete-unused-eips      Delete unused EIPs
      switch-to-public        Switch to public route table
      switch-to-private       Switch to private route table
      clean                   Clean up all for testing
  
  options:
    -h, --help                show this help message and exit
    --verbose                 Print detailed logs
```


## Sample configuration file (config.py)

``` python
class Config:
    hyperpod_cluster_arn = "arn:aws:sagemaker:us-east-1:842413447717:cluster/wthlbldg1lkq"
    subnet = "subnet-05a70d97c1dec6bff"
    route_table_for_private = "rtb-046c1c0e0fa32478e"
    route_table_for_public = "rtb-0486999e28ae7f3a6"
```
