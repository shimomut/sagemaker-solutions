all:

run:
	sbatch job.sh

log:
	tail -f output/*

q:
	squeue

clean:
	rm output/log_*.txt
	rm gpu-failure-happened.txt
