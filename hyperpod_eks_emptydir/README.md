## HyperPod EKS - configure host path for ephemeral storage

#### Overview

As of 2025-07, HyperPod EKS uses the primary EBS storage for kubelet root-dir. 
It means the size of ephemeral storage such as emptyDir is limited by the primary EBS volume of 100GB.

This solution explains how to configure kubelet root-dir in the lifecycle script, so that you can use 2ndary EBS volume for ephemeral storage.

> **Note:** This solution is tested only on AL2 based AMI.

#### Steps

1. Add following lines in the lifecycle script

    ``` bash
    logger "Found secondary EBS volume. Setting kubelet data root to /opt/sagemaker/kubelet"
    mkdir -p /opt/sagemaker/kubelet
    sed -i "\/ExecStart=\/usr\/bin\/kubelet/a \ \ \ \ --root-dir /opt/sagemaker/kubelet \\\\" "/etc/eks/containerd/kubelet-containerd.service"
    ```

2. Create cluster (or, replace instances) to create instances with the updated lifecycle script

3. SSM login to a new instance and make sure kubelet is using /opt/sagemaker/kubelet/.

    ```
    sh-4.2# ls -al /opt/sagemaker/kubelet/
    total 12
    drwxr-xr-x  7 root root  150 Jul 16 14:55 .
    drwxr-xr-x  4 root root   39 Jul 16 14:55 ..
    drwx------  2 root root    6 Jul 16 14:55 checkpoints
    -rw-------  1 root root   62 Jul 16 14:55 cpu_manager_state
    -rw-------  1 root root   61 Jul 16 14:55 memory_manager_state
    drwxr-x---  2 root root    6 Jul 16 14:55 plugins
    drwxr-x---  2 root root    6 Jul 16 14:55 plugins_registry
    drwxr-x---  2 root root   26 Jul 16 14:55 pod-resources
    drwxr-x--- 16 root root 4096 Jul 16 14:56 pods
    ```

4. Use disk based emptyDir in your application.

    ``` yaml
            :
    containers:
    - name: emptydir-test
            :
        volumeMounts:
        - mountPath: /cache
        name: cache-volume
    volumes:
    - name: cache-volume
    emptyDir: {}
            :
    ```

5. (Optional) verify the emptyDir storage size by kubectl exec

    ```
    $ kubectl exec -it emptydir-test-7664f565c7-4qzgb -- bash

    root@emptydir-test-7664f565c7-4qzgb:/# df
    Filesystem     1K-blocks    Used Available Use% Mounted on
    overlay        524032000 5922632 518109368   2% /
    tmpfs              65536       0     65536   0% /dev
    tmpfs           16021700       0  16021700   0% /sys/fs/cgroup
    /dev/nvme1n1   524032000 5922632 518109368   2% /cache
    shm                65536       0     65536   0% /dev/shm
    tmpfs           31026572      12  31026560   1% /run/secrets/kubernetes.io/serviceaccount
    tmpfs           16021700       0  16021700   0% /proc/acpi
    tmpfs           16021700       0  16021700   0% /sys/firmware    
    ```

#### Considerations

- If you need higher performance, consider to use memory based emptyDir.

    ``` yaml
            :
    containers:
    - name: emptydir-test
            :
        volumeMounts:
        - mountPath: /cache
        name: cache-volume

    volumes:
    - name: cache-volume
      emptyDir:
        medium: Memory
        sizeLimit: 10Gi
            :
    ```

