"""Tiny static server + /save POST sink so the headless three.js page can hand
back exact canvas pixels (a data: URL) which we persist to disk. Avoids screenshot
colour-management quirks: we store precisely what the WebGL canvas produced."""
import http.server, socketserver, os, sys, base64, urllib.parse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # research/delighting
OUT = sys.argv[2] if len(sys.argv) > 2 else '/tmp/r047'
os.makedirs(OUT, exist_ok=True)

class H(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **k): super().__init__(*a, directory=ROOT, **k)
    def log_message(self, *a): pass
    def do_POST(self):
        if self.path.startswith('/save'):
            q = urllib.parse.urlparse(self.path).query
            name = urllib.parse.parse_qs(q).get('name', ['out'])[0]
            n = int(self.headers['Content-Length']); body = self.rfile.read(n).decode()
            b64 = body.split(',', 1)[1] if ',' in body else body
            with open(os.path.join(OUT, name + '.png'), 'wb') as f:
                f.write(base64.b64decode(b64))
            self.send_response(200); self.end_headers(); self.wfile.write(b'ok')
        else:
            self.send_response(404); self.end_headers()

if __name__ == '__main__':
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8047
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(('127.0.0.1', port), H) as s:
        print(f'serving {ROOT} -> saves to {OUT} on :{port}', flush=True)
        s.serve_forever()
