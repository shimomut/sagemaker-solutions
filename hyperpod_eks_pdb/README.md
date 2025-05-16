#### How to attach debugger to Python process in Kubernetes Pods

1. Update the Dockerfile to install pdb-attach

    ``` dockerfile
    RUN pip3 install pdb-attach
    ```

1. (Optional) Update the Dockerfile to install debug_tools.py

    ``` dockerfile
    COPY ./debug_tools.py /myapp/
    ```

1. Build the docker image, push it to image repository, and deploy the app

1. Identify the Pod name you want to debug

    ``` bash
    kubectl get pods
    ```

1. Login to the Pod by interactive shell

    ``` bash
    kubectl exec -it {POD_NAME} -- bash
    ```

1. Identify the process ID to debug (Typically "1")

    ``` bash
    ps ax
    ```

1. Attach debugger

    ``` bash
    python -m pdb_attach {PID} 5678
    ```

1. (Optional) Import debug_tools module, and call functions

    ``` python
    (Pdb) import debug_tools
    (Pdb) debug_tools.threads()

    +-----------------+--------------+--------------+
    | ID              | Name         | IsAlive      |
    +-----------------+--------------+--------------+
    | 139764642925440 | MainThread   | True         |
    | 139764635723456 | worker-0     | True         |
    | 139764625233600 | worker-1     | True         |
    | 139764544042688 | worker-2     | True         |
    +-----------------+--------------+--------------+

    (Pdb) debug_tools.stack(139764625233600)

    Call stack:
    File '/usr/local/lib/python3.13/threading.py', line 1012, in _bootstrap
        self._bootstrap_inner()
    File '/usr/local/lib/python3.13/threading.py', line 1041, in _bootstrap_inner
        self.run()
    File '/myapp/debug_target.py', line 23, in run
        time.sleep(5)    
    ```


#### How to handle multiple processes

When you create multiple processes in the Pod, you need to make sure that the port numbers don't conflict each other.
For example, you can use process IDs to make port numbers unique.

``` python
import os
import pdb_attach
pdb_attach.listen(50000 + os.getpid())
```


#### See also

Pdb debugger commands - https://docs.python.org/3/library/pdb.html#debugger-commands
