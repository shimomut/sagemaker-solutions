
FSX_DATADIR = /fsx2/ior-data
WEKA_DATADIR = /mnt/weka/ior-data

run:
	python3.9 ./ior-test.py

dirs:
	sudo mkdir -p ${FSX_DATADIR}
	sudo chown ubuntu:ubuntu ${FSX_DATADIR}

	sudo mkdir -p ${WEKA_DATADIR}
	sudo chown ubuntu:ubuntu ${WEKA_DATADIR}

clean:
	rm -f ${FSX_DATADIR}/*
	rm -f ${WEKA_DATADIR}/*


check-ior-existing-all:
	srun -N 16 make check-ior-existing-single

check-ior-existing-single:
	ps ax | grep ior
