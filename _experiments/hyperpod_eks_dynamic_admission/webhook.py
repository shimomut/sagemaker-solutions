import os
import ssl
import json
import pprint
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs


#cert_dirname = os.path.dirname(__file__)
cert_dirname = "/certs"


debug_print = print
# def debug_print(*args):
#     pass


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

    def do_POST(self):

        parsed_url = urlparse(self.path)
        api_path = parsed_url.path
        query_params = parse_qs(parsed_url.query)

        if api_path == '/validate':
            try:
                post_data = self._read_post_data()

                print("Request:")
                pprint.pprint(post_data)

                request_id = post_data["request"]["uid"]

                response_data = {
                    "apiVersion": "admission.k8s.io/v1",
                    "kind": "AdmissionReview",
                    "response": {
                        "uid": request_id,
                        "allowed": True
                    }
                }

                print("Response:")
                pprint.pprint(response_data)

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
