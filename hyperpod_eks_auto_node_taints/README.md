## Setup Mutating Admission Webhook to automatically set node taints and labels

#### Overview

HyperPod EKS currently doesn't have a feature to automatically add taints and labels to notes (as of 2025-05). 

This solution deploys a Mutating Admission Webhook to automatically add taints and labels to HyperPod nodes. 

> **Note:** The Webhook runs for newly created nodes only. For existing nodes, you need to set taints manually.

#### Setup steps

1. Add tolerations for GPU device plugin and EFA device plugin

    Uninstall existing dependency helm chart.

    Add tolerations to the following places.

    - https://github.com/aws/sagemaker-hyperpod-cli/blob/main/helm_chart/HyperPodHelmChart/values.yaml#L175
    - https://github.com/aws/sagemaker-hyperpod-cli/blob/main/helm_chart/HyperPodHelmChart/values.yaml#L244

        ``` yaml
        tolerations:
              :
          - operator: Exists
            effect: NoSchedule
          - operator: Exists
            effect: NoExecute
        ```
    Install with the updated helm chart.


1. Generate certificate and key for the webhook

    ``` bash
    $ openssl genrsa 2048 > tls.key
    $ openssl req -new -key tls.key -out tls_server.csr

    You are about to be asked to enter information that will be incorporated
    into your certificate request.
    What you are about to enter is what is called a Distinguished Name or a DN.
    There are quite a few fields but you can leave some blank
    For some fields there will be a default value,
    If you enter '.', the field will be left blank.
    -----
    Country Name (2 letter code) [AU]:US
    State or Province Name (full name) [Some-State]:Washington
    Locality Name (eg, city) []:Bellevue
    Organization Name (eg, company) [Internet Widgits Pty Ltd]:Amazon
    Organizational Unit Name (eg, section) []:SageMaker
    Common Name (e.g. server FQDN or YOUR name) []:mutating-webhook.auto-node-taints-test.svc.cluster.local
    Email Address []:shimomut@amazon.com

    Please enter the following 'extra' attributes
    to be sent with your certificate request
    A challenge password []:
    An optional company name []:

    $ echo "subjectAltName = DNS:mutating-webhook.auto-node-taints-test.svc, DNS:mutating-webhook.auto-node-taints-test.svc.cluster.local" > san.txt
    $ openssl x509 -req -sha256 -days 365 -in tls_server.csr -signkey tls.key -out tls.crt -extfile san.txt
    ```

    Note: For the SAN (X509v3 Subject Alternative Name), use following format: `{service-name}.{namespace-name}.svc.cluster.local`


1. Add the cert and key as a Secret

    ``` bash
    kubectl create namespace auto-node-taints-test
    kubectl create secret tls mutating-webhook-secret --key certs/tls.key --cert certs/tls.crt -n auto-node-taints-test
    ```

    Verify it exists.

    ```bash
    kubectl describe secret mutating-webhook-secret -n auto-node-taints-test
    ```

1. Customize the webhook script for intended behavior

    Open `webhook.py` with your text editor.

    Update labels and taints to apply.

    ``` python
    {
        "op": "add",
        "path": "/metadata/labels/mutating-webhook-label",
        "value": "123"
    }
    ```

    ``` python
    {
        "op": "add",
        "path": "/spec/taints/-",
        "value": {
            "key": "mutating-webhook-taint",
            "effect": "NoSchedule",
            "value": "true",
        }
    }
    ```

    You can delete label adding section if you don't need to apply node labels.


1. Build the image for webhook, push it to ECR, and deploy it

    ``` bash
    make login-ecr
    make build-image
    make tag-image
    make push-image
    make deploy-webhook
    ```

    Confirm the webhook Pod exists and running.

    ```bash
    make list-webhook-pods
    ```


1. Edit `mutating_webhook_config.yaml`

    `caBundle` field has to be updated with the base64 expression of the certificate file. You can get base64 expression of the certificate by following command:

    ``` bash
    base64 -w 0 certs/tls.crt
    ```


1. Deploy the Webhook config

    ``` bash
    make deploy-webhook-config
    ```


1. Watch logs from the webhook

    ``` bash
    make watch-webhook-logs
    ```

    or if you use `stern` to watch logs:

    ``` bash
    stern mutating-webhook- -n auto-node-taints-test
    ```


1. Verify

    Scale up the GPU instance group.

    Confirm new nodes have intended node taints and labels.

    Confirm Deep Health Checks run through.

    Run this command to list nodes, and confirm Deep Health Check field shows "Passed"

    ``` bash
    kubectl get nodes "-o=custom-columns=NAME:.metadata.name,INSTANCETYPE:.metadata.labels.node\.kubernetes\.io/instance-type,GPU:.status.allocatable.nvidia\.com/gpu,EFA:.status.allocatable.vpc\.amazonaws\.com/efa,HEALTH:.metadata.labels.sagemaker\.amazonaws\.com/node-health-status,DHC:.metadata.labels.sagemaker\.amazonaws\.com\/deep-health-check-status"
    ```

    ``` text
    NAME                          INSTANCETYPE   GPU  EFA  HEALTH      DHC
    hyperpod-i-07dd1e8461b5048cc  ml.g5.8xlarge  1    1    Schedulable Passed
    hyperpod-i-0b078973a60deb9c8  ml.g5.8xlarge  1    1    Schedulable Passed
    ```

