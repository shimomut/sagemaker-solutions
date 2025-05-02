## How to set up Validating Admission Webhook for finer grain access control


1. Generate certificate and key for the webhook

    ``` bash
    openssl genrsa 2048 > tls.key
    openssl req -new -key tls.key -out tls_server.csr
    echo "subjectAltName = DNS:mywebhook.mynamespace.svc, DNS:mywebhook.mynamespace.svc.cluster.local" > san.txt
    openssl x509 -req -sha256 -days 365 -in tls_server.csr -signkey tls.key -out tls.crt -extfile san.txt
    ```

    Note: For the SAN (X509v3 Subject Alternative Name), use following format: `{service-name}.{namespace-name}.svc.cluster.local`


1. (Optional) Test the webhook locally

    In terminal A,
    ``` bash
    python3 webhook.py
    ```

    In terminal B,
    ``` bash
    curl -s -k -H 'Content-Type: application/json' -XPOST https://localhost:8443/validate -d @./sample-request.json
    ```

1. Add the cert and key as a Secret.

    ``` bash
    kubectl create secret webhook mywebhook-secret --key certs/webhook.key --cert certs/webhook.crt -n mynamespace
    ```

1. Build the image for webhook, push it to ECR, and deploy it.

    ``` bash
    make build
    make login
    make tag
    make push
    make deploy
    ```

1. Edit `validating_webhook_config.yaml`

    `caBundle` field has to be updated with the base64 expression of the certificate file. You can get base64 expression of the certificate by following command:

    ``` bash
    base64 -w 0 certs/tls.crt
    ```

1. Depliy the Webhook config.

    ``` bash
    kubectl apply -f validating_webhook_config.yaml
    ```

1. Watch log from the webhook.

    ``` bash
    kubectl logs -f -l app=mywebhook -n mynamespace
    ```

1. Create / delete resources to test the webhook

    ```
	kubectl apply -f hello.yaml
	kubectl delete -f hello.yaml
    ```
