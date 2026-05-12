import http.server
import socketserver
from pathlib import Path

PORT = 5173
BACKEND_URL = "http://localhost:8000/api/v1/process"

class FrontendHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path in ('/', '/index.html'):
            try:
                with open('index.html', 'r', encoding='utf-8') as f:
                    content = f.read()
                self.send_response(200)
                self.send_header('Content-type', 'text/html; charset=utf-8')
                self.end_headers()
                self.wfile.write(content.encode('utf-8'))
            except FileNotFoundError:
                self.send_error(404, "index.html not found")
        else:
            super().do_GET()

    def log_message(self, format, *args):
        return


if __name__ == '__main__':
    with socketserver.TCPServer(('', PORT), FrontendHandler) as httpd:
        print(f'Frontend running at http://localhost:{PORT}')
        print(f'Using backend: {BACKEND_URL}')
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print('\nStopping frontend server')