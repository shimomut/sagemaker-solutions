FSX_DATADIR = /fsx2/fio-data
WEKA_DATADIR = /mnt/weka/fio-data

#fio_options = --randrepeat=1 --ioengine=libaio --direct=1 --gtod_reduce=1 --name=test --bs=4k --iodepth=64 --readwrite=randrw --rwmixread=75 --size=4G
#fio_options = --randrepeat=1 --ioengine=libaio --direct=1 --gtod_reduce=1 --name=test --bs=1m --iodepth=64 --readwrite=randrw --rwmixread=75 --size=4G
#fio_options = --randrepeat=1 --ioengine=libaio --direct=1 --gtod_reduce=1 --name=test --bs=128m --iodepth=64 --readwrite=randrw --rwmixread=75 --size=4G

hostname = $(shell hostname)
timestamp = $(shell date +%s)

install-fio:
	sudo apt install -y fio

install-fio-workers:
	srun -N 16 make install-fio

dirs:
	sudo mkdir -p ${FSX_DATADIR}
	sudo chown ubuntu:ubuntu ${FSX_DATADIR}

	sudo mkdir -p ${WEKA_DATADIR}
	sudo chown ubuntu:ubuntu ${WEKA_DATADIR}

run-servers:
	srun -N 16 fio --server

check-servers-remaining:
	srun -N 16 ps ax | grep fio

run:
	python3.9 fio-test.py

clean:
	rm ${FSX_DATADIR}/*
	rm ${WEKA_DATADIR}/*

