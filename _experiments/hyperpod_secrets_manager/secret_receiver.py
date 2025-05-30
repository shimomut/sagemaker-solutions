import os
import time
import json
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

import boto3


class SecretCallbackServer(HTTPServer):
    def __init__(self, server_address, RequestHandlerClass):
        super().__init__(server_address, RequestHandlerClass)
        self.secret = None


class SecretCallbackHandler(BaseHTTPRequestHandler):

    def __init__(self, request, client_address, server):
        super().__init__(request, client_address, server)

    def _send_response(self, data):
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def _read_post_data(self):
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length)
        return json.loads(post_data.decode())

    def do_POST(self):

        parsed_url = urlparse(self.path)
        api_path = parsed_url.path

        if api_path == '/secret':
            try:
                post_data = self._read_post_data()

                # print("PostData:")
                # print(json.dumps(post_data, indent=2))

                self.server.secret = post_data["secret"]

                response = {
                }

                self._send_response(response)

            except json.JSONDecodeError as e:

                print("Error:", e)

                self.send_response(400)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({
                    'error': 'Invalid JSON data',
                    'status': 'error'
                }).encode())
        else:
            print(f"Error: unknown API path {api_path}")

            self.send_response(404)
            self.end_headers()


def get_secret(host='0.0.0.0', port=8080):

    region_name = os.environ['AWS_REGION']

    # --------------------
    # Start HTTP server

    server_address = (host, port)
    http_server = SecretCallbackServer(server_address, SecretCallbackHandler)

    thread = threading.Thread(target=http_server.handle_request, args=())
    thread.start()

    # --------------------
    # Invoke Lambda

    # FIXME: Should automatically get from resource_config.json
    lambda_payload = {
        "cluster_name": "slurm-1",
        "node_id": "i-04e74d163c94af4a0",
        "secret_name": "hyperpod-lifecycle-secret-test1"
    }    

    lambda_client = boto3.client('lambda', region_name=region_name)

    # FIXME: should handle errors and do retries
    response = lambda_client.invoke(
        FunctionName='scret_provider', # FIXME: typo in the function name
        InvocationType='RequestResponse',
        Payload=json.dumps(lambda_payload)
    )

    # --------------------
    # Get received secret

    thread.join()

    return http_server.secret


if __name__ == '__main__':

    os.environ['AWS_REGION'] = "us-west-2"

    secret = get_secret()
    print(secret)

