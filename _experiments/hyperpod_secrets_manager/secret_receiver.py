import os
import json
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse


class SecretReceiver(BaseHTTPRequestHandler):

    def __init__(self, request, client_address, server):
        super().__init__(request, client_address, server)
        self.secret = None

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

                print("PostData:")
                print(json.dumps(post_data, indent=2))

                self.secret = post_data["secret"]

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


def run_server(host='0.0.0.0', port=8080):
    server_address = (host, port)
    http_server = HTTPServer(server_address, SecretReceiver)
    http_server.serve_forever()

if __name__ == '__main__':
    run_server()
