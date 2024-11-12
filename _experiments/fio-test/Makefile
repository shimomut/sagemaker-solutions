
fio_options = --randrepeat=1 --ioengine=libaio --direct=1 --gtod_reduce=1 --name=test --bs=4k --iodepth=64 --readwrite=randrw --rwmixread=75 --size=4G
hostname = $(shell hostname)
timestamp = $(shell date +%s)

install:
	sudo apt install -y fio

run-fsx:
	fio ${fio_options} --filename=./data-${hostname}-${timestamp}.bin

run-weka:
	fio ${fio_options} --filename=../weka/fio-test/data-${hostname}-${timestamp}.bin

clean:
	rm ./data-*.bin
	rm ../weka/fio-test/data-*.bin

