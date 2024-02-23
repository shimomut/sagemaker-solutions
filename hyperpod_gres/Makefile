all:

enqueue:
	sbatch job.sh

alloc:
	salloc --gres=gpu:1 --mem=4G

run:
	srun --gpus=1 --mem=4G ping www.amazon.com

log:
	tail -f output/*

q:
	squeue

clean:
	rm output/log_*.txt
