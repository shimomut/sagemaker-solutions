pull-images:
	aws ecr get-login-password --region us-west-2 | docker login --username AWS --password-stdin 905418368575.dkr.ecr.us-west-2.amazonaws.com
	docker pull 905418368575.dkr.ecr.us-west-2.amazonaws.com/hyperpod-health-monitoring-agent:1.0.344.0_1.0.45.0

	aws ecr get-login-password --region us-west-2 | docker login --username AWS --password-stdin 602401143452.dkr.ecr.us-west-2.amazonaws.com
	docker pull 602401143452.dkr.ecr.us-west-2.amazonaws.com/eks/aws-efa-k8s-device-plugin:v0.5.3

	docker pull nvcr.io/nvidia/k8s-device-plugin:v0.16.1
	docker pull kubeflow/training-operator:v1-855e096
	docker pull registry.k8s.io/nfd/node-feature-discovery:v0.15.3
	docker pull mpioperator/mpi-operator:0.5
	docker pull quay.io/coreos/etcd:latest

tag-images:
	docker tag 905418368575.dkr.ecr.us-west-2.amazonaws.com/hyperpod-health-monitoring-agent:1.0.344.0_1.0.45.0 842413447717.dkr.ecr.us-east-1.amazonaws.com/hyperpod-health-monitoring-agent:1.0.344.0_1.0.45.0
	docker tag 602401143452.dkr.ecr.us-west-2.amazonaws.com/eks/aws-efa-k8s-device-plugin:v0.5.3 842413447717.dkr.ecr.us-east-1.amazonaws.com/eks/aws-efa-k8s-device-plugin:v0.5.3
	docker tag nvcr.io/nvidia/k8s-device-plugin:v0.16.1 842413447717.dkr.ecr.us-east-1.amazonaws.com/nvidia/k8s-device-plugin:v0.16.1
	docker tag kubeflow/training-operator:v1-855e096 842413447717.dkr.ecr.us-east-1.amazonaws.com/training-operator:v1-855e096
	docker tag registry.k8s.io/nfd/node-feature-discovery:v0.15.3 842413447717.dkr.ecr.us-east-1.amazonaws.com/nfd/node-feature-discovery:v0.15.3
	docker tag mpioperator/mpi-operator:0.5 842413447717.dkr.ecr.us-east-1.amazonaws.com/mpi-operator:0.5
	docker tag quay.io/coreos/etcd:latest 842413447717.dkr.ecr.us-east-1.amazonaws.com/coreos/etcd:latest

create-repos:
	aws --region us-east-1 ecr create-repository --repository-name hyperpod-health-monitoring-agent
	aws --region us-east-1 ecr create-repository --repository-name eks/aws-efa-k8s-device-plugin
	aws --region us-east-1 ecr create-repository --repository-name nvidia/k8s-device-plugin
	aws --region us-east-1 ecr create-repository --repository-name training-operator
	aws --region us-east-1 ecr create-repository --repository-name nfd/node-feature-discovery
	aws --region us-east-1 ecr create-repository --repository-name mpi-operator
	aws --region us-east-1 ecr create-repository --repository-name coreos/etcd

push-images:
	aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin 842413447717.dkr.ecr.us-east-1.amazonaws.com
	docker image push 842413447717.dkr.ecr.us-east-1.amazonaws.com/hyperpod-health-monitoring-agent:1.0.344.0_1.0.45.0
	docker image push 842413447717.dkr.ecr.us-east-1.amazonaws.com/eks/aws-efa-k8s-device-plugin:v0.5.3
	docker image push 842413447717.dkr.ecr.us-east-1.amazonaws.com/nvidia/k8s-device-plugin:v0.16.1
	docker image push 842413447717.dkr.ecr.us-east-1.amazonaws.com/training-operator:v1-855e096
	docker image push 842413447717.dkr.ecr.us-east-1.amazonaws.com/nfd/node-feature-discovery:v0.15.3
	docker image push 842413447717.dkr.ecr.us-east-1.amazonaws.com/mpi-operator:0.5
	docker image push 842413447717.dkr.ecr.us-east-1.amazonaws.com/coreos/etcd:latest
