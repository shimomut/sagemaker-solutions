all:

efa-plugin:
	kubectl apply -f https://raw.githubusercontent.com/aws-samples/aws-efa-eks/main/manifest/efa-k8s-device-plugin.yml

nv-device-plugin:
	kubectl apply -f https://raw.githubusercontent.com/NVIDIA/k8s-device-plugin/v0.14.0/nvidia-device-plugin.yml

nccl-efa-tests:
	kubectl apply -f nccl-efa-tests.yaml