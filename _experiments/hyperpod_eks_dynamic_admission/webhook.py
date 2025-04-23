import os

from http.server import HTTPServer, BaseHTTPRequestHandler
import ssl
import json

this_dirname = os.path.dirname(__file__)


#debug_print = print
def debug_print(*args):
    pass


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
        debug_print("do_POST", 1)
        if self.path == '/validate':
            debug_print("do_POST", 2)
            try:
                debug_print("do_POST", 3)
                post_data = self._read_post_data()
                debug_print("do_POST", 4)
                response_data = {
                    'message': 'Data received successfully',
                    'received_data': post_data,
                    'status': 'success'
                }
                debug_print("do_POST", 5)
                self._send_response(response_data)
                debug_print("do_POST", 6)
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
        certfile = os.path.join(this_dirname, "webhook.crt"),
        keyfile = os.path.join(this_dirname, "webhook.key"),
    )
    
    # Wrap the socket with SSL
    httpd.socket = ssl_context.wrap_socket(httpd.socket, server_side=True)
    
    print(f'Starting secure server on {host}:{port}')
    httpd.serve_forever()

if __name__ == '__main__':
    run_server()
