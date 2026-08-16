import http.server
import socketserver
import json
import io
import os

from parse_evaluation import parse_uspf_evaluation

PORT = 8000

class CustomHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    def do_POST(self):
        if self.path == '/api/parse-pdf':
            try:
                content_length = int(self.headers.get('Content-Length', 0))
                if content_length <= 0:
                    self._send_json({'error': 'Empty PDF payload.'}, 400)
                    return

                raw_bytes = self.rfile.read(content_length)

                # Check if payload is multipart form data or raw pdf
                pdf_bytes = raw_bytes
                if b'PDF-' in raw_bytes:
                    # Extract starting from %PDF- header
                    pdf_start = raw_bytes.find(b'%PDF-')
                    if pdf_start != -1:
                        pdf_bytes = raw_bytes[pdf_start:]
                        # Trim trailing boundary if present
                        pdf_end = pdf_bytes.rfind(b'%%EOF')
                        if pdf_end != -1:
                            pdf_bytes = pdf_bytes[:pdf_end + 5]

                # Parse PDF in memory
                pdf_stream = io.BytesIO(pdf_bytes)
                result = parse_uspf_evaluation(pdf_stream)

                if 'error' in result:
                    self._send_json(result, 400)
                else:
                    self._send_json(result, 200)

            except Exception as e:
                self._send_json({'error': str(e)}, 500)
        else:
            self.send_response(404)
            self.end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def _send_json(self, data, status_code=200):
        self.send_response(status_code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode('utf-8'))

def run_server():
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", PORT), CustomHTTPRequestHandler) as httpd:
        print(f"Serving USPF 'Am I a Latin Honor?' App at http://localhost:{PORT}")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nServer stopped.")

if __name__ == '__main__':
    run_server()
