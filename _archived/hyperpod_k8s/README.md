# How to install self-managed Kubernetes on HyperPod



### Overview

This is a sample solution to set up Kubernetes cluster on HyperPod. Cluster will include Slurm, but this solution installs Kubernetes in addition to it.

In this solution, Kubernetes is automatically installed by the lifecycle script ([lcc/*](https://github.com/shimomut/sagemaker-solutions/tree/main/hyperpod_k8s/lcc)). You can customize how to install Kubernetes as-needed by modifying the lifecycle script.


> **Important:** This is not a part of HyperPod service. Use this sample solution at your own risk.



### Limitations / out-of-scope

* Auto-resume is out-of-scope. (Manual instance replacement is possible)
* Multi master nodes is not supported yet (although you can try to customize the script to support it).
* You need to login to master node (head node) to use kubectl command to run workloads. Using kubectl from remote machines would be possible, but it is not tested.
* When cluster scaling up operation fails and rolls back (e.g., hardware health check failure), you may see garbage nodes in the node list. As of now, this solution doesn't automatically delete nodes when nodes are deleted by cluster rolling back. Please manually delete nodes using `kubectl delete node`.
* Due to HyperPod’s current limitation, EBS root volume size is limited at 100GB. As a workaround, the lifecycle configuration script automatically change the containerd data path to NVMe if available.
* Due to HyperPod’s current limitation, cluster cannot be scaled down. Deleting instance group and decreasing the number of instances are not possible today. 


### What the lifecycle configuration script does

1. Common initialization (phase1)
    1. Setup Slurm cluster as usual
    2. Install boto3
    3. Configure bridged network traffic
    4. Configure containerd as the container runtime.
    5. Install Kubernetes packages
2. Master node specific initialization (phase2)
    1. Run “kubeadm init” to create a Kubernetes cluster, and store join token in the SecretsManager
    2. Install flannel as the CNI plugin
3. Worker node specific initialization (phase2)
    1. Get join token from SecretsManager with retries.
    2. Run “kubeadm join” to join the cluster
4. Master node specific initialization (phase3)
    1. Wait until all nodes become “Ready” status
    2. Add label “node.kubernetes.io/instance-type={instance type}” to all nodes.


### How to set up a Kubernetes cluster on HyperPod

##### Create an IAM Role for HyperPod cluster instance groups

* Base permissions for HyperPod - https://docs.aws.amazon.com/sagemaker/latest/dg/sagemaker-hyperpod-prerequisites.html#sagemaker-hyperpod-prerequisites-iam-role-for-hyperpod (including Additional permissions for using SageMaker HyperPod with Amazon Virtual Private Cloud)

* Inline permission to read/write SecretsManager. This solutions uses SecretsManager to store and exchange Kubernetes join token.

    ``` json
    {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": [
                    "secretsmanager:CreateSecret",
                    "secretsmanager:UpdateSecret",
                    "secretsmanager:ListSecrets",
                    "secretsmanager:GetSecretValue"
                ],
                "Resource": "arn:aws:secretsmanager:*:842413447717:secret:hyperpod-*"
            }
        ]
    }
    ```

* (if you use ECR as the container image resository) Inline permission to read ECR
    
    ``` json
    {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": [
                    "ecr:BatchCheckLayerAvailability",
                    "ecr:BatchGetImage",
                    "ecr:GetDownloadUrlForLayer",
                    "ecr:GetAuthorizationToken"
                ],
                "Resource": "*"
            }
        ]
    }
    ```

##### Create a cluster with Kubernetes enabled lifecycle script

1. Create prerequisite resources (VPC, FSxL, etc) using the CF templates in the workshop
    - https://catalog.workshops.aws/sagemaker-hyperpod/en-US/00-setup/02-own-account
    - Make sure your S3 bucket’s name starts with “sagemaker-”. Cluster execution IAM role has permission to access only those buckets which starts with “sagemaker-” prefix.
2. Create a HyperPod cluster with K8s enabled LCC script
    - https://github.com/shimomut/sagemaker-solutions/tree/main/hyperpod_k8s/lcc
    - Configure the version of Kubernetes as needed. Edit "lcc/utils/install_kubernetes.sh".
    - Configure CIDR of Pod network as needed, based on your taget cluster size. By default, CIDR of Pod network is set to "10.244.0.0/16", and each node uses /24 as the mask size of PodCIDR. With this default setting, you can create up to 256 nodes (including master node) in the cluster. If this is not sufficient for you, you can change the "pod_network_cidr" in the "lcc/configure_k8s.py". (e.g., 10.244.0.0/14 for 1024 nodes).

3. Confirm the cluster becomes “InService” status.
4. Login to the controller node with SSM or SSH.
5. Confirm nodes are visible in Kubernetes world.

    ```
    $ kubectl get nodes
    NAME              STATUS   ROLES           AGE   VERSION
    ip-10-2-115-210   Ready    <none>          18m   v1.29.1
    ip-10-2-69-128    Ready    <none>          18m   v1.29.1
    ip-10-2-75-197    Ready    control-plane   20m   v1.29.1
    ```

6. (Optional but recommended) Configure AWS region and output format
    ```
    $ aws configure
    AWS Access Key ID [None]: 
    AWS Secret Access Key [None]: 
    Default region name [None]: us-west-2
    Default output format [None]: json
    ```

7. (Optional but recommended) Install git
    ```
    $ sudo apt install git
    ```



### How to run a sample workload

##### Environment setup for sample workload

1. Login to the controller node by SSM or SSH. (You can use VS Code as well)
2. Install Nvidia device plugin

    1. Deploy
        ```
        $ kubectl apply -f https://raw.githubusercontent.com/NVIDIA/k8s-device-plugin/v0.15.0/deployments/static/nvidia-device-plugin.yml
        ```
    
    2. Verify “nvidia.com/gpu” field appears in the worker node description.
        
        ```
        $ kubectl describe node {node-name}
        ```
        
        ```
        Capacity:
            cpu:                192
            ephemeral-storage:  101569200Ki
            hugepages-1Gi:      0
            hugepages-2Mi:      42242Mi
            memory:             2097112716Ki
            nvidia.com/gpu:     8
            pods:               110
        ```

    3. You can also check multiple nodes in bulk.
        ```
        $ kubectl get nodes "-o=custom-columns=NAME:.metadata.name,GPU:.status.allocatable.nvidia\.com/gpu"
        ```

        ```
        NAME              GPU
        ip-10-2-0-25      1
        ip-10-2-103-146   1
        ip-10-2-105-39    1
        ip-10-2-116-255   1
        ip-10-2-119-24    1
        ip-10-2-125-107   1
        ip-10-2-19-110    1
        ip-10-2-20-114    1
            :
            :
        ```
              
3. Install EFA Device Plugin
    1. Checkout https://github.com/aws-samples/aws-do-eks.git

        ```    
        $ git clone https://github.com/aws-samples/aws-do-eks.git
        ```
    
    2. Change directory to the efa-device-plugin.

        ```
        $ cd ~/aws-do-eks/Container-Root/eks/deployment/efa-device-plugin
        ```
    
    3. Add imagePullSecrets in the efa-k8s-device-plugin.yaml

        ``` yaml
        hostNetwork: true
        imagePullSecrets:
        - name: regcred-efa
        containers:
        ```

    4. Login
        
        ```
        $ kubectl create secret docker-registry regcred-efa --docker-server=602401143452.dkr.ecr.us-west-2.amazonaws.com --docker-username=AWS --docker-password=$(aws --region us-west-2 ecr get-login-password) --namespace=kube-system
        ```

    5. Deploy
        
        ```
        $ kubectl apply -f efa-k8s-device-plugin.yaml
        ```

    6. Verify “vpc.amazonaws.com/efa” appears in the worker node description.
        
        ```
        $ kubectl get nodes
        $ kubectl describe node {worker-node-name}
        ```
        
        ```
        Capacity:
            cpu:                    192
            ephemeral-storage:      101569200Ki
            hugepages-1Gi:          0
            hugepages-2Mi:          42242Mi
            memory:                 2097112716Ki
            nvidia.com/gpu:         8
            pods:                   110
            vpc.amazonaws.com/efa:  32
        ```

4. Install MPI operator

    1. Change directory to the mpi-operator.
    
        ```
        $ cd ~/aws-do-eks/Container-Root/eks/deployment/kubeflow/mpi-operator
        ```
    
    2. Deploy the MPI operator

        ```
        $ ./deploy.sh
        ```

    3. Verify MPI operator is running
        
        ```
        $ kubectl get pods -n mpi-operator
        NAME                            READY   STATUS    RESTARTS   AGE
        mpi-operator-7477b5bdbd-j4vrd   1/1     Running   0          9s
        ```



##### Run “nccl-efa-tests”

1. On your development machine (e.g. EC2 instance), build the container image
    1. Checkout https://github.com/aws-samples/aws-do-eks.git

        ```
        $ git clone https://github.com/aws-samples/aws-do-eks.git
        ```

    2. Change directory to cuda-efa-nccl-tests.

        ```
        $ cd aws-do-eks/Container-Root/eks/deployment/nccl-test/cuda-efa-nccl-tests
        ```

    3. Remove --progress=plain from .env.

        ``` bash
        #export BUILD_OPTS="--progress=plain --no-cache --build-arg http_proxy=${http_proxy} --build-arg https_proxy=${https_proxy} --build-arg no_proxy=${no_proxy}"
        export BUILD_OPTS="--no-cache --build-arg http_proxy=${http_proxy} --build-arg https_proxy=${https_proxy} --build-arg no_proxy=${no_proxy}"`
        ```

    4. Build and Push (building image takes 30~60min)

        ```
        $ ./build.sh
        $ ./push.sh
        ```

2. On the controller node, deploy the app
    1. Go to the nccl-test directory

        ```
        $ cd aws-do-eks/Container-Root/eks/deployment/nccl-test
        ```

    2. Add imagePullSecrets in “all-reduce.yaml-template" file. There are two places, one for Launcher and another for Worker.

        ``` yaml
            :
        imagePullSecrets:
        - name: regcred-nccl-test
        containers:
            :
        ```

    3. Login
        ```
        $ kubectl create secret docker-registry regcred-nccl-test --docker-server=842413447717.dkr.ecr.us-west-2.amazonaws.com --docker-username=AWS --docker-password=$(aws --region us-west-2 ecr get-login-password)
        ```

    4. Deploy
        ```
        $ ./run.sh
        ```

    5. Monitor

        ```
        $ ./status.sh
        $ ./logs.sh
        ```

    6. Verify job completion

        ```
        $ kubectl get pods
        NAME                    READY   STATUS      RESTARTS   AGE
        mpirun-launcher-qksj6   0/1     Completed   3          3m
        ```


### Tips

##### How to replace faulty instances

1. Drain the node, to disable scheduling for the node
    ```
    $ kubectl drain {node-name} --ignore-daemonsets
    ```

2. Delete the node from the cluster
    ```
    $ kubectl delete node {node-name}
    ```

3. Run the “hyperpod_k8s_op.py replace-instance” command (It takes 10min ~ 20min)
    ```
    $ python3.9 hyperpod_k8s_op.py replace-instance {node-name}
    ```
4. Verify new instance is visible by “kubectl get nodes” command.
    ```
    kubectl get nodes
    ```


##### How to scale-up cluster

1. Run the “hyperpod_k8s_op.py generate-new-token” command.
    ```
    $ python3.9 hyperpod_k8s_op.py generate-new-token
    ```

2. Increase the number of instances by “Edit” button on the Management Console, or with “update-cluster” API.



##### How to delete orphan nodes

When you scale-up your cluster, it is possible HyperPod detects hardware failures in the new instances, and scaling up operation rolls back. But if the failed instances are already added to the Kubernetes cluster, they are not automatically removed. You can use the script to delete those orphan nodes.

1. Run the hyperpod_k8s_op.py delete-orphan-nodes” command.
    ```
    $ python3.9 ./hyperpod_k8s_op.py delete-orphan-nodes
    ```

2. You will be asked before actually deleting them.

    ```
    Orphan nodes:
    ip-10-2-118-116
    ip-10-2-14-164
    ip-10-2-39-55
    ip-10-2-69-189
    ip-10-2-77-176
    ip-10-2-77-36
    ip-10-2-93-180
    ip-10-2-95-229
    Delete these orphan nodes? [y/N]y
    ```

3. Enter "y" if you are sure to delete them.

    ```
    Deleting ip-10-2-118-116
    node "ip-10-2-118-116" deleted
    Deleting ip-10-2-14-164
    node "ip-10-2-14-164" deleted
    Deleting ip-10-2-39-55
    node "ip-10-2-39-55" deleted
    Deleting ip-10-2-69-189
    node "ip-10-2-69-189" deleted
    Deleting ip-10-2-77-176
    node "ip-10-2-77-176" deleted
    Deleting ip-10-2-77-36
    node "ip-10-2-77-36" deleted
    Deleting ip-10-2-93-180
    node "ip-10-2-93-180" deleted
    Deleting ip-10-2-95-229
    node "ip-10-2-95-229" deleted
    ```



