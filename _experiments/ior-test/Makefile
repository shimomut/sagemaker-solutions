
FSX_DATADIR = /fsx_p2/shimomut/fio-test
WEKA_DATADIR = /mnt/weka/shimomut/fio-test
RESULT_DIR = ./results

run:
	mkdir -p ${RESULT_DIR}
	python3.9 ./ior-test.py

list-files:
	ls -al ${FSX_DATADIR}
	ls -al ${WEKA_DATADIR}

clean:
	rm -f ${FSX_DATADIR}/*
	rm -f ${WEKA_DATADIR}/*

