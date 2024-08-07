all:

run:
	srun -N 2 python3.9 -u s3_concurrent_bandwidth.py
	
clean:
	rm tmp/*.bin
	rmdir tmp

s5cmd-bulk:
	srun -N 1 s5cmd cp --concurrency 100 s3://shimomut-files-vpce-us-east-2-842413447717/tmp/*.bin /opt/dlami/nvme/s3test/

awscli-bulk:
	srun -N 1 aws s3 cp s3://shimomut-files-vpce-us-east-2-842413447717/tmp/ /opt/dlami/nvme/s3test/ --recursive
