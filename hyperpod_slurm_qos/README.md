## How to configure QoS / Preemption / Requeue on HyperPod Slurm cluster

1. Confirm accounting is enabled

    ``` bash
    scontrol show config | grep -i accounting
    sudo sacctmgr show stats
    sacct
    ```

1. Create account/user (adding ubuntu user as an example here)

    ```
    sudo sacctmgr add account ubuntu Cluster=m5-1 Description="Ubuntu" Organization=TestOrg
    sacctmgr list account
    ```

    ```
    sudo sacctmgr add user ubuntu Cluster=m5-1 Account=ubuntu DefaultAccount=ubuntu AdminLevel=Operator
    sacctmgr list user
    ```

1. Enable QoS

    Open "accounting.conf" by text editor:

    ```
    sudo vi /opt/slurm/etc/accounting.conf
    ```

    Add following line:

    ```
    AccountingStorageEnforce=limits,qos
    ```

    Apply the change:

    ```
    sudo systemctl restart slurmctld
    ```

    Verify the account/user is working.
    ```
    srun -N 2 hostname
    ```

1. Create QoS

    ```
    sudo sacctmgr add qos high
    sudo sacctmgr modify qos high set MaxJobs=8
    sudo sacctmgr modify qos high set Priority=10
    sacctmgr show qos format=name,priority,maxtresperuser,maxwall,MaxJobsPU
    ```

1. Apply QoS to ubuntu account (so that ubuntu account can use this qos)

    ```
    sudo sacctmgr modify account where name=ubuntu set qos+=high
    ```

1. Test QoS is working properly

    Run this command multiple times,

    ```
    sbatch --qos=high --priority=1 job.sh
    ```

    And confirm only one job is Running status and others are pending status by "QOSMaxJobsPerUserLimit".
    ```
    squeue -O "JobID,Name,Account,UserName,State,Reason,QOS,PriorityLong"
    ```

    Try other QoS and priority as well.
    ```
    sbatch --qos=normal --priority=1 job.sh
    sbatch --qos=high --priority=100 job.sh
    ```

1. Manual requeue

    Run this command to manually requeue currently running job.
    ```
    scontrol requeue {job-id}
    ```

1. Enable automatic preemption

    Add following lines in the slurm.conf.
    ```
    PreemptMode=REQUEUE
    PreemptType=preempt/qos
    ```

    Apply the change:

    ```
    sudo systemctl restart slurmctld
    ```

    Configure preemption mode and preemption relationship for QoS.
    ```
    sudo sacctmgr modify qos normal set PreemptMode=REQUEUE
    sudo sacctmgr modify qos high set PreemptMode=REQUEUE

    # "normal" can be preempted by "high"
    sudo sacctmgr modify qos high set Preempt=normal

    sacctmgr show qos format=name,priority,maxtresperuser,maxwall,MaxJobsPU,Preempt,PreemptMode
    ```

    Run jobs with --requeue option
    ```
    sbatch --qos=normal --priority=10 --requeue job.sh
    sbatch --qos=normal --priority=10 --requeue job.sh
    sbatch --qos=normal --priority=10 --requeue job.sh
    sbatch --qos=normal --priority=10 --requeue job.sh
    sbatch --qos=high --priority=10 --requeue job.sh
    ```

    Confirm "high" job is running and "normal" job got preempted and requeue'ed.
    ```
    squeue -O "JobID,Name,Account,UserName,State,Reason,QOS,PriorityLong"

    JOBID               NAME                ACCOUNT             USER                STATE               REASON              QOS                 PRIORITY
    57                  hello               ubuntu              ubuntu              PENDING             BeginTime           normal              10
    60                  hello               ubuntu              ubuntu              PENDING             Priority            normal              10
    59                  hello               ubuntu              ubuntu              PENDING             Resources           normal              10
    61                  hello               ubuntu              ubuntu              RUNNING             None                high                10
    58                  hello               ubuntu              ubuntu              RUNNING             None                normal              10
    ```


## See also

* https://slurm.schedmd.com/accounting.html
* https://slurm.schedmd.com/qos.html
* https://slurm.schedmd.com/preempt.html
