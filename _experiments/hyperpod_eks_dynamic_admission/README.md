


#### How to generate certificate and key for the webhook
```
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
```
python3 webhook.py
```

In terminal B,
```
curl -s -k -H 'Content-Type: application/json' -XPOST https://localhost:8443/validate -d @./sample-request.json
```