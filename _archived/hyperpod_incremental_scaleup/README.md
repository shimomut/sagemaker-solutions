## HyperPod cluster incremental scaling up script

#### Overview

When creating a large HyperPod cluster, it is recommended to create a smaller cluster first, and incrementally scale up to the target size.

This script helps you to scale up your cluster to the target size incrementally.


#### Usage

1. Create a cluster with small size (e.g., 2 instances)
1. Run this script
    ```
    python3 ./hyperpod_incremental_scaleup.py --cluster-name c5-1 --instance-group-name WorkerGroup --target-instance-count 32 --increment-by 4
    ```