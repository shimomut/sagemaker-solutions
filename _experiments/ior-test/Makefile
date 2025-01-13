
FSX1_DATADIR = /fsx1/ubuntu/ior-data
FSX2_DATADIR = /fsx2/ubuntu/ior-data
FSX3_DATADIR = /fsx3/ubuntu/ior-data
WEKA_DATADIR = /mnt/weka/ior-data

run:
	python3.9 ./ior-test.py

dirs:
	sudo mkdir -p ${FSX1_DATADIR}
	sudo chown ubuntu:ubuntu ${FSX1_DATADIR}

	sudo mkdir -p ${FSX2_DATADIR}
	sudo chown ubuntu:ubuntu ${FSX2_DATADIR}

	sudo mkdir -p ${FSX3_DATADIR}
	sudo chown ubuntu:ubuntu ${FSX3_DATADIR}

	sudo mkdir -p ${WEKA_DATADIR}
	sudo chown ubuntu:ubuntu ${WEKA_DATADIR}

clean:
	rm -f ${FSX1_DATADIR}/*
	rm -f ${FSX2_DATADIR}/*
	rm -f ${FSX3_DATADIR}/*
	rm -f ${WEKA_DATADIR}/*


check-ior-existing-all:
	srun -N 32 make check-ior-existing-single

check-ior-existing-single:
	ps ax | grep ior
