"""
A plain HTTP server that runs on your laptop.

This is the "thing we want to expose" — analogous to Home Assistant
running on port 8123 on your Raspberry Pi. It listens only on
127.0.0.1, so nothing outside your laptop can reach it directly.

Run it with:
    python my_service.py
"""

from http.server import BaseHTTPRequestHandler, HTTPServer


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(b"<h1>Hello from my laptop!</h1>")
        self.wfile.write(b"<p>You reached me through the reverse tunnel.</p>")

    def log_message(self, format, *args):
        # Prefix local service logs so they're easy to spot.
        print(f"[my_service] {format % args}")


if __name__ == "__main__":
    host, port = "127.0.0.1", 8080
    print(f"[my_service] listening on http://{host}:{port}")
    HTTPServer((host, port), Handler).serve_forever()
