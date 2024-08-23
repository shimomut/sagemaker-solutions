## HyperPod issue reporting script


#### Overview

This script gathers issue reporting information from your cluster. By running this script on the head node, you will get a Zip file that contains troubleshooting information.


#### Precondition

- This script assumes SSH access from the head node to all worker nodes are already set up. See also the [relevant workshop page](https://catalog.workshops.aws/sagemaker-hyperpod/en-US/01-cluster/07-ssh-compute).


#### Data to be collected

- /opt/ml/config/resource_config.json (on head node)
- /var/log/aws/clusters/* (on head node)
- sinfo / sinfo -R (on head node)
- systemctl status slurmctld (on head node)
- systemctl status slurmd (on worker nodes)
- /opt/slurm/etc/* (on head node)
- nvidia-smi (on worker nodes)
- nvidia-bug-report (on worker nodes)
- /var/log/syslog
- /var/log/kern.log
- /var/log/slurm/*
- df


#### Usage

1. Login to the head node
1. Put this script under FSxL file system (e.g., /fsx/ubuntu)
1. Run this script
    ```
    python3 ./hyperpod_issue_report.py
    ```
1. Wait until completion
1. Download the generated Zip archive file (e.g., ./hyperpod_issue_report_20240823_023049.zip)


#### Sample output

```
hyperpod_issue_report_20240823_023724
├── control
│   └── ip-10-2-109-13
│       ├── df.log
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
    │   ├── kern.log
    │   ├── nvidia-bug-report.log.gz
    │   ├── nvidia-smi.log
    │   ├── slurmd_status.log
    │   ├── syslog
    │   └── var_log_slurm
    │       ├── slurm_jobacct.log
    │       ├── slurm_jobcomp.log
    │       ├── slurmctld.log
    │       ├── slurmd.log
    │       └── slurmdbd.log
    └── ip-10-2-99-136
        ├── df.log
        ├── kern.log
        ├── nvidia-bug-report.log.gz
        ├── nvidia-smi.log
        ├── slurmd_status.log
        ├── syslog
        └── var_log_slurm
            ├── slurm_jobacct.log
            ├── slurm_jobcomp.log
            ├── slurmctld.log
            ├── slurmd.log
            └── slurmdbd.log
```