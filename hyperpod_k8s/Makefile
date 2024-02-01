all:

master-node:
	cd lcc && python3.9 ./configure_k8s.py --master-node

worker-node:
	cd lcc && python3.9 ./configure_k8s.py

upload-lcc:
	aws s3 sync lcc/ s3://sagemaker-cluster-842413447717/lcc/k8s/