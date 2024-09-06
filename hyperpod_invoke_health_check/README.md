## HyperPod health check invoking solution


#### Overview

This is a sample solution to **manually** invoke health check on multiple worker nodes in a HyperPod cluster, and replace instances when faulty nodes are detected.

For who haven't enabled `--auto-resume=1` option in the arguments of `srun` command, this solution can be a helpful tool to quickly find faulty instances.


#### Usage

1. Login to the head node or login node
1. Put `step.py` and `job.sh` under FSxL file system (e.g., /fsx/ubuntu)
1. Update the number of nodes in `job.sh` based on your cluster size.
1. Run the script with sbatch.
    ```
    sbatch ./job.sh
    ```
1. Monitor log output from the job, sinfo, and Console UI, to check if faulty nodes were detected and to monitor the progress of instance replacement.
