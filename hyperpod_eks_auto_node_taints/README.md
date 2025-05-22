## Setup Mutating Admission Webhook to automatically set node taints


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


1. Add the cert and key as a Secret.

    ``` bash
    kubectl create namespace auto-node-taints-test
    kubectl create secret tls mutating-webhook-secret --key certs/tls.key --cert certs/tls.crt -n auto-node-taints-test
    ```

    Cerify it exists.

    ```bash
    kubectl describe secret mutating-webhook-secret -n auto-node-taints-test
    ```

1. Build the image for webhook, push it to ECR, and deploy it.

    ``` bash
    make build
    make login
    make tag
    make push
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

1. Depliy the Webhook config.

    ``` bash
    make deploy-webhook-config
    ```

1. Watch log from the webhook.

    ``` bash
    make watch-webhook-logs
    ```

1. Create / delete resources to test the webhook (e.g. scale up instance group)

