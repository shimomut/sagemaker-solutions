run-normal-1:
	sbatch --qos=normal --priority=1 job.sh

run-normal-100:
	sbatch --qos=normal --priority=100 job.sh

run-high-1:
	sbatch --qos=high --priority=1 job.sh

run-high-100:
	sbatch --qos=high --priority=100 job.sh

list-jobs:
	squeue -O "JobID,Name,Account,UserName,State,Reason,QOS,PriorityLong"