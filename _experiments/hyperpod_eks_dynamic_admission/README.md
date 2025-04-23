


#### How to generate certificate and key for the webhook
``` bash
openssl genrsa 2048 > webhook.key
openssl req -new -key webhook.key -out webhook_server.csr
echo "subjectAltName = DNS:mywebhook.mynamespace.svc, DNS:mywebhook.mynamespace.svc.cluster.local" > san.txt
openssl x509 -req -sha256 -days 365 -in webhook_server.csr -signkey webhook.key -out webhook.crt -extfile san.txt
```

Note: Is SAN (X509v3 Subject Alternative Name) needed?
Note: What NDS name should I use?

    Follow this format?
    `service-name.namespace-name.svc.cluster.local`


#### How to run and test the Webhook locally

In terminal A,
``` bash
python3 webhook.py
```

In terminal B,
``` bash
curl -s -k -H 'Content-Type: application/json' -XPOST https://localhost:8443/validate -d @./sample-request.json
```


#### How to deploy the webhook

1. Add cert and key as a Secret

``` bash
kubectl create secret webhook mywebhook-secret --key certs/webhook.key --cert certs/webhook.crt -n mynamespace
```

2. Build the image for Webhook, push it to ECR, and deploy it

``` bash
make build
make login
make tag
make push
make deploy
```

3. Edit `validating_webhook_config.yaml`

`caBundle` field has to be updated with the base64 expression of the certificate file.

``` bash
base64 -w 0 certs/tls.crt
```

4. Depliy the Webhook config

``` bash
kubectl apply -f validating_webhook_config.yaml
```
