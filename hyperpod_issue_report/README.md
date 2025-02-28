## HyperPod issue reporting script


#### Overview

This script gathers issue reporting information from your cluster. By running this script on the head node, you will get a Zip file that contains troubleshooting information.


#### Precondition

- This script assumes SSH access from the head node to all worker nodes are already set up. See also the [relevant workshop page](https://catalog.workshops.aws/sagemaker-hyperpod/en-US/01-cluster/07-ssh-compute).
- The user who executes this script needs to have sudo privilege.


#### Data to be collected

- Cluster resource configuration file `/opt/ml/config/resource_config.json` (on head node)
- Output of `sinfo` / `sinfo -R` (on head node)
- Output of `systemctl status slurmctld` (on head node)
- Output of `systemctl status slurmd` (on worker nodes)
- Slurm configurations `/opt/slurm/etc/*` (on head node)
- Ourput of `nvidia-smi` (on worker nodes)
- Output of `nvidia-bug-report.sh` (on worker nodes)
- `/var/log/syslog`
- `/var/log/kern.log`
- Output of `dmesg -T`
- Slurm related logs `/var/log/slurm/*`
- SageMaker HyperPod related logs `/var/log/aws/clusters/*`
- Output of `df`


#### Usage

1. Login to the head node
1. Put this script under FSxL file system (e.g., /fsx/ubuntu)
1. (Optional) change the `skip_ssh_host_key_check` to `True` if you want to skip the SSH host key checks.
1. Run this script

    **Case 1:** collect data from all worker nodes and head node.
    ```
    python3 ./hyperpod_issue_report.py
    ```

    **Case 2:** collect data from specific worker nodes and head node.
    ```
    python3 ./hyperpod_issue_report.py --nodes ip-10-3-48-177 ip-10-3-117-137
    ```

    **Case 3** collect data only from head node. (In this case, data is not archived in Zip)
    ```
    python3 ./hyperpod_issue_report.py --capture-single-node --head-node --output-path ./issue_xyz/headnode
    ```

1. Wait until completion
1. Download the generated Zip archive file (e.g., ./hyperpod_issue_report_20240823_023049.zip)




#### Sample output

```
hyperpod_issue_report_20240826_172859
├── control
│   └── ip-10-2-109-13
│       ├── df.log
│       ├── dmesg-T.log
│       ├── kern.log
│       ├── opt_slurm_etc
│       │   ├── accounting.conf
│       │   ├── gres.conf
│       │   ├── plugstack.conf
│       │   ├── plugstack.conf.d
│       │   │   └── pyxis.conf -> /usr/local/share/pyxis/pyxis.conf
│       │   ├── slurm.conf
│       │   ├── slurmdbd.conf
│       │   └── slurmdbd.conf.template
│       ├── resource_config.json
│       ├── sinfo-R.log
│       ├── sinfo.log
│       ├── slurmctld_status.log
│       ├── syslog
│       ├── var_log_aws_clusters
│       │   ├── sagemaker-autoresume.log
│       │   ├── sagemaker-cluster-agent.log
│       │   ├── sagemaker-host-agent.log
│       │   └── sagemaker-role-proxy-agent.log
│       └── var_log_slurm
│           ├── slurm_jobacct.log
│           ├── slurm_jobcomp.log
│           ├── slurmctld.log
│           ├── slurmd.log
│           └── slurmdbd.log
└── worker
    ├── ip-10-2-123-231
    │   ├── df.log
    │   ├── dmesg-T.log
    │   ├── kern.log
    │   ├── nvidia-bug-report.log.gz
    │   ├── nvidia-smi.log
    │   ├── slurmd_status.log
    │   ├── syslog
    │   ├── var_log_aws_clusters
    │   │   ├── sagemaker-autoresume.log
    │   │   ├── sagemaker-cluster-agent.log
    │   │   ├── sagemaker-host-agent.log
    │   │   └── sagemaker-role-proxy-agent.log
    │   └── var_log_slurm
    │       ├── slurm_jobacct.log
    │       ├── slurm_jobcomp.log
    │       ├── slurmctld.log
    │       ├── slurmd.log
    │       └── slurmdbd.log
    └── ip-10-2-99-136
        ├── df.log
        ├── dmesg-T.log
        ├── kern.log
        ├── nvidia-bug-report.log.gz
        ├── nvidia-smi.log
        ├── slurmd_status.log
        ├── syslog
        ├── var_log_aws_clusters
        │   ├── sagemaker-autoresume.log
        │   ├── sagemaker-cluster-agent.log
        │   ├── sagemaker-host-agent.log
        │   └── sagemaker-role-proxy-agent.log
        └── var_log_slurm
            ├── slurm_jobacct.log
            ├── slurm_jobcomp.log
            ├── slurmctld.log
            ├── slurmd.log
            └── slurmdbd.log
```
