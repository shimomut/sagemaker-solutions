
fio_options = --randrepeat=1 --ioengine=libaio --direct=1 --gtod_reduce=1 --name=test --bs=4k --iodepth=64 --readwrite=randrw --rwmixread=75 --size=4G
#fio_options = --randrepeat=1 --ioengine=libaio --direct=1 --gtod_reduce=1 --name=test --bs=1m --iodepth=64 --readwrite=randrw --rwmixread=75 --size=4G
#fio_options = --randrepeat=1 --ioengine=libaio --direct=1 --gtod_reduce=1 --name=test --bs=128m --iodepth=64 --readwrite=randrw --rwmixread=75 --size=4G

hostname = $(shell hostname)
timestamp = $(shell date +%s)

install:
	sudo apt install -y fio

data-dirs:
	mkdir -p ./fsx-data
	mkdir -p ../../../weka/fio-test
	ln -s ../../../weka/fio-test ./weka-data

run-fsx-task:
	fio ${fio_options} --filename=./fsx-data/data-${hostname}-${timestamp}.bin

run-weka-task:
	fio ${fio_options} --filename=./weka-data//data-${hostname}-${timestamp}.bin

run-fsx-batch:
	sbatch job-fsx.sbatch

run-weka-batch:
	sbatch job-weka.sbatch

clean:
	rm -f ./fsx-data/data-*.bin
	rm -f ./weka-data/data-*.bin

