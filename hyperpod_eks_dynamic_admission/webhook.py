import os
import ssl
import json
import pprint
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs


#cert_dirname = os.path.dirname(__file__)
cert_dirname = "/certs"


class APIHandler(BaseHTTPRequestHandler):

    def _send_response(self, data):
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def _read_post_data(self):
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length)
        return json.loads(post_data.decode())

    def _validate(self, req):

        kind = req["kind"]
        operation = req["operation"]
        api_invoker_username = req["userInfo"]["username"]
        api_invoker_groups = req["userInfo"]["groups"]

        print(f"Operation: {operation}, Kind: {kind}")

        # Allow unknown kinds
        if kind["kind"] not in ["Pod", "Deployment"]:
            print("Ignoring unknown kinds:", kind["kind"])
            return True, 200, ""

        # Allow all groups that start with "system:" prefix (except for system:authenticated).
        # Allow "dynamic-admission:admin" group.
        for group in api_invoker_groups:
            if group in ["system:authenticated"]:
                continue
            if group.startswith("system:") or group == "dynamic-admission:admin":
                print(f"Allowing by group: {group}")
                return True, 200, ""

        # Allow all resource creation operations.
        if operation in ["CREATE"]:
            print(f"Allowing operation {operation}")
            return True, 200, ""

        # Get target object information
        if operation in ["UPDATE", "DELETE", "CONNECT"]:
            obj = req["oldObject"]
        elif operation in ["CONNECT"]:
            obj = req["object"]

        # Get owner information from labels
        try:
            obj_owner = obj["metadata"]["labels"]["dynamic-admission-owner"]
        except KeyError:
            obj_owner = None

        # If owner information is missing in the object, allow everything
        if obj_owner is None:
            print(f"Allowing {operation} operation to resources without dynamic admission owner")
            return True, 200, ""

        if obj_owner != api_invoker_username:
            return False, 403, f"Forbidden access to resource owned by different user (owner:{obj_owner} != you:{api_invoker_username})"

        print(f"Allowing {operation} operation to resources owned by the API invoker ({api_invoker_username})")
        return True, 200, ""

    def do_POST(self):

        parsed_url = urlparse(self.path)
        api_path = parsed_url.path

        if api_path == '/validate':
            try:
                post_data = self._read_post_data()

                # print("Request:")
                # print(json.dumps(post_data, indent=2))

                request_id = post_data["request"]["uid"]

                is_allowed, code, message = self._validate(post_data["request"])

                if is_allowed:
                    response_data = {
                        "apiVersion": "admission.k8s.io/v1",
                        "kind": "AdmissionReview",
                        "response": {
                            "uid": request_id,
                            "allowed": True
                        }
                    }
                else:
                    response_data = {
                        "apiVersion": "admission.k8s.io/v1",
                        "kind": "AdmissionReview",
                        "response": {
                            "uid": request_id,
                            "allowed": False,
                            "status": {
                                "code": code,
                                "message": message
                            }
                        }
                    }

                # print("Response:")
                # print(json.dumps(response_data, indent=2))

                self._send_response(response_data)

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

        print("---")
        print("")


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
