
"""Vercel Serverless Function — Gemini API proxy"""

import json
import os
import urllib.request
import urllib.error
from http.server import BaseHTTPRequestHandler


class handler(BaseHTTPRequestHandler):

    def do_POST(self):
        try:
            content_length = int(
                self.headers.get("Content-Length", "0")
            )

            if content_length <= 0:
                self._send_json(400, {
                    "error": {"message": "Request body is empty"}
                })
                return

            body = self.rfile.read(content_length)
            request_data = json.loads(body)

            # Read the secret key from Vercel settings
            api_key = os.environ.get("GEMINI_API_KEY")

            if not api_key:
                self._send_json(500, {
                    "error": {
                        "message":
                        "GEMINI_API_KEY not configured on server"
                    }
                })
                return

            # Keep the existing model for now
            model = "gemini-flash-latest"

            gemini_url = (
                "https://generativelanguage.googleapis.com/"
                f"v1beta/models/{model}:generateContent"
            )

            req = urllib.request.Request(
                gemini_url,
                data=json.dumps(request_data).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "x-goog-api-key": api_key,
                },
                method="POST",
            )

            with urllib.request.urlopen(
                req, timeout=60
            ) as response:
                result = json.loads(
                    response.read().decode("utf-8")
                )
                self._send_json(200, result)

        except json.JSONDecodeError:
            self._send_json(400, {
                "error": {"message": "Invalid JSON request"}
            })

        except urllib.error.HTTPError as e:
            try:
                error_data = json.loads(
                    e.read().decode("utf-8", errors="replace")
                )
            except json.JSONDecodeError:
                error_data = {
                    "error": {
                        "message": "Gemini API request failed"
                    }
                }

            self._send_json(e.code, error_data)

        except Exception:
            self._send_json(500, {
                "error": {"message": "Internal server error"}
            })

    def _send_json(self, status, data):
        body = json.dumps(
            data, ensure_ascii=False
        ).encode("utf-8")

        self.send_response(status)
        self.send_header(
            "Content-Type", "application/json; charset=utf-8"
        )
        self.send_header(
            "Access-Control-Allow-Origin", "*"
        )
        self.send_header(
            "Access-Control-Allow-Methods", "POST, OPTIONS"
        )
        self.send_header(
            "Access-Control-Allow-Headers", "Content-Type"
        )
        self.send_header(
            "Content-Length", str(len(body))
        )
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header(
            "Access-Control-Allow-Origin", "*"
        )
        self.send_header(
            "Access-Control-Allow-Methods", "POST, OPTIONS"
        )
        self.send_header(
            "Access-Control-Allow-Headers", "Content-Type"
        )
        self.end_headers()

    def log_message(self, fmt, *args):
        return
