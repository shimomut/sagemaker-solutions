import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import requests
import boto3
import sys

REAL_IMDS = "http://169.254.169.254"
ROLE_NAME = "EmptyTestRole"  # The role you want to substitute
ASSUME_ROLE_ARN =  "arn:aws:iam::842413447717:role/ImdbProxyTestRole"
SESSION_NAME = "test-session"

class IMDSMockHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/latest/meta-data/iam/security-credentials/":
            # Return the spoofed role name
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(ROLE_NAME.encode())

        elif self.path == f"/latest/meta-data/iam/security-credentials/{ROLE_NAME}":
            # Return substituted credentials
            try:
                print("Posting credentials for the role")
                sts = boto3.client("sts")

                try:
                    response = sts.assume_role(
                        RoleArn=ASSUME_ROLE_ARN,
                        RoleSessionName=SESSION_NAME,
                        DurationSeconds=3600  # max 3600 for assume_role
                    )
                    print(response)

                    creds = response["Credentials"]

                    imds_response = {
                        "Code": "Success",
                        "LastUpdated": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "Type": "AWS-HMAC",
                        "AccessKeyId": creds["AccessKeyId"],
                        "SecretAccessKey": creds["SecretAccessKey"],
                        "Token": creds["SessionToken"],
                        "Expiration": creds["Expiration"].strftime("%Y-%m-%dT%H:%M:%SZ")
                    }

                    # send response
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps(imds_response).encode())

                except Exception as e:
                    print(e)
                    self.send_error(500, f"Failed to assume role: {e}")

            except Exception as e:
                self.send_error(500, f"Failed to get credentials: {e}")

        else:
            # Proxy all other IMDS requests to the real IMDS
            try:
                proxied = requests.get(REAL_IMDS + self.path, headers=self.headers, timeout=2)
                self.send_response(proxied.status_code)
                for key, value in proxied.headers.items():
                    self.send_header(key, value)
                self.end_headers()
                self.wfile.write(proxied.content)
            except Exception as e:
                self.send_error(500, f"Proxy failed: {e}")

    def log_message(self, format, *args):
        return  # Suppress logs

def run(server_class=HTTPServer, handler_class=IMDSMockHandler, port=8080):
    server_address = ("127.0.0.1", port)
    httpd = server_class(server_address, handler_class)
    print(f"Mock IMDS proxy running at http://127.0.0.1:{port}")
    httpd.serve_forever()
    
if __name__ == "__main__":
    if len(sys.argv) > 1:
        ROLE_NAME = sys.argv[1]


    # FIXME: test
    sts = boto3.client("sts")
    response = sts.assume_role(
        RoleArn=ASSUME_ROLE_ARN,
        RoleSessionName=SESSION_NAME,
        DurationSeconds=3600  # max 3600 for assume_role
    )


    run()
