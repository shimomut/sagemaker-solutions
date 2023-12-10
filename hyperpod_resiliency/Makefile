all:

run:
	sbatch job2.sh

log:
	tail -f output/*

q:
	squeue

clean:
	rm output/log_*.txt
	rm gpu-failure-happened.txt
