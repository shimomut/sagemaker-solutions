
FSX_DATADIR = /fsx/ubuntu/fio-test-data
WEKA_DATADIR = /mnt/weka/fio-test-data

run:
	python3.9 ./ior-test.py

make-dirs:
	sudo mkdir ${FSX_DATADIR}
	sudo chown ubuntu:ubuntu ${FSX_DATADIR}

	sudo mkdir ${WEKA_DATADIR}
	sudo chown ubuntu:ubuntu ${WEKA_DATADIR}

list-files:
	ls -al ${FSX_DATADIR}
	ls -al ${WEKA_DATADIR}

clean:
	rm -f ${FSX_DATADIR}/*
	rm -f ${WEKA_DATADIR}/*

