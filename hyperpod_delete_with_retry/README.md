## HyperPod cluster delete-with-retry script

#### Overview

When delete a large HyperPod cluster, especially with p5, you may see cluster deletion failures due to ENI API throttling error. In this case, number of instances is actually decreasing.

This script helps you to delete your cluster until the number of instances reaches zero.


#### Usage

1. Run this script
    ```
    python3 ./hyperpod_delete_with_retry.py --cluster-name my-cluster-1
    ```