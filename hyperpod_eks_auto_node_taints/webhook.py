import os
import ssl
import json
import base64
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs


if os.path.exists("./certs"):
    cert_dirname = "./certs"
else:
    cert_dirname = "/certs"


class APIHandler(BaseHTTPRequestHandler):

    # Suppress logs
    def log_message(self, format, *args):
        pass

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

        if api_path == '/mutate':
            try:
                post_data = self._read_post_data()

                request = post_data["request"]
                request_id = request["uid"]

                # print( "%s - %s" % (request["kind"]["kind"], request["operation"]) )

                response = {
                    "apiVersion": "admission.k8s.io/v1",
                    "kind": "AdmissionReview",
                    "response": {
                        "uid": request_id,
                        "allowed": True
                    }
                }

                # Add label and taint to new HyperPod nodes
                if request["kind"]["kind"] == "Node" and request["operation"] == "CREATE" and request["name"].startswith("hyperpod-"):

                    print("Request:")
                    print(json.dumps(post_data, indent=2))

                    patch = [
                        
                        # Add a label
                        {
                            "op": "add",
                            "path": "/metadata/labels/mutating-webhook-label",
                            "value": "123"
                        },

                        # Add a taint
                        {
                            "op": "add",
                            "path": "/spec/taints/-",
                            "value": {
                                "key": "mutating-webhook-taint",
                                "effect": "NoSchedule",
                                "value": "true",
                            }
                        }
                    ]
                    
                    # Base64 encode the patch
                    patch_bytes = json.dumps(patch).encode('utf-8')
                    base64_patch = base64.b64encode(patch_bytes).decode('utf-8')
                    
                    # Add the patch to the response
                    response["response"]["patchType"] = "JSONPatch"
                    response["response"]["patch"] = base64_patch                    

                    print("Response:")
                    print(json.dumps(response, indent=2))


                # Add label and toleration to HyperPod system Pods
                elif request["kind"]["kind"] == "Pod" and request["operation"] == "CREATE" and request["namespace"] == "aws-hyperpod":

                    print("Request:")
                    print(json.dumps(post_data, indent=2))

                    patch = [
                        
                        # Add a label
                        {
                            "op": "add",
                            "path": "/metadata/labels/mutating-webhook-label",
                            "value": "123"
                        },

                        # Add a taint
                        {
                            "op": "add",
                            "path": "/spec/tolerations/-",
                            "value": {
                                "key": "mutating-webhook-taint",
                                "operator": "Equal",
                                "effect": "NoSchedule",
                                "value": "true",
                            }
                        }
                    ]
                    
                    # Base64 encode the patch
                    patch_bytes = json.dumps(patch).encode('utf-8')
                    base64_patch = base64.b64encode(patch_bytes).decode('utf-8')
                    
                    # Add the patch to the response
                    response["response"]["patchType"] = "JSONPatch"
                    response["response"]["patch"] = base64_patch                    

                    print("Response:")
                    print(json.dumps(response, indent=2))

                self._send_response(response)

            except json.JSONDecodeError:
                self.send_response(400)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({
                    'error': 'Invalid JSON data',
                    'status': 'error'
                }).encode())
        else:
            self.send_response(404)
            self.end_headers()


def run_server(host='0.0.0.0', port=8443):
    server_address = (host, port)
    httpd = HTTPServer(server_address, APIHandler)
    
    # SSL context configuration
    ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ssl_context.load_cert_chain(
        certfile = os.path.join(cert_dirname, "tls.crt"),
        keyfile = os.path.join(cert_dirname, "tls.key"),
    )
    
    # Wrap the socket with SSL
    httpd.socket = ssl_context.wrap_socket(httpd.socket, server_side=True)
    
    print(f'Starting secure server on {host}:{port}')
    httpd.serve_forever()

if __name__ == '__main__':
    run_server()
