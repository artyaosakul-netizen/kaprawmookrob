
"""Vercel Serverless Function — Gemini API proxy"""

import json
import os
import random
import time
import urllib.request
import urllib.error
from http.server import BaseHTTPRequestHandler


PRIMARY_MODEL = "gemini-3.6-flash"
FALLBACK_MODEL = "gemini-3.8-flash"

# Errors that may be temporary
RETRYABLE_STATUS = {408, 429, 500, 502, 503, 504}


def call_gemini(model, request_data, api_key):
    """Call Gemini and return (status_code, response_data)."""

    url = (
        "https://generativelanguage.googleapis.com/"
        f"v1beta/models/{model}:generateContent"
    )

    request = urllib.request.Request(
        url,
        data=json.dumps(request_data).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": api_key,
        },
        method="POST",
    )

    with urllib.request.urlopen(request, timeout=25) as response:
        data = json.loads(response.read().decode("utf-8"))
        return response.status, data


def call_with_retry(model, request_data, api_key):
    """Retry temporary failures twice, with increasing delays."""

    last_status = 500
    last_data = {
        "error": {"message": "Gemini request failed"}
    }

    for attempt in range(3):
        try:
            status, data = call_gemini(
                model, request_data, api_key
            )
            return status, data

        except urllib.error.HTTPError as error:
            last_status = error.code

            try:
                last_data = json.loads(
                    error.read().decode("utf-8", errors="replace")
                )
            except (json.JSONDecodeError, ValueError):
                last_data = {
                    "error": {
                        "message": "Gemini API request failed"
                    }
                }

            if error.code not in RETRYABLE_STATUS:
                return last_status, last_data

        except (TimeoutError, OSError, urllib.error.URLError) as error:
            last_status = 503
            last_data = {
                "error": {
                    "message": (
                        "Temporary network or timeout error: "
                        + str(error)[:300]
                    )
                }
            }

        if attempt < 2:
            # Wait approximately 1, then 2 seconds
            time.sleep((2 ** attempt) + random.uniform(0, 0.5))

    return last_status, last_data


class handler(BaseHTTPRequestHandler):

    def do_POST(self):
        try:
            content_length = int(
                self.headers.get("Content-Length", "0")
            )

            if content_length <= 0 or content_length > 10_000_000:
                self._send_json(400, {
                    "error": {"message": "Invalid request body size"}
                })
                return

            body = self.rfile.read(content_length)
            request_data = json.loads(body)

            api_key = os.environ.get("GEMINI_API_KEY")

            if not api_key:
                self._send_json(500, {
                    "error": {
                        "message":
                        "GEMINI_API_KEY not configured on server"
                    }
                })
                return

            # Try the primary model first
            status, result = call_with_retry(
                PRIMARY_MODEL, request_data, api_key
            )

            if status == 200:
                self._send_json(200, result)
                return

            # Only use fallback for temporary failures or missing model
            if status not in RETRYABLE_STATUS and status != 404:
                self._send_json(status, result)
                return

            # Try the backup model
            fallback_status, fallback_result = call_with_retry(
                FALLBACK_MODEL, request_data, api_key
            )

            if fallback_status == 200:
                self._send_json(200, fallback_result)
                return

            # Return the final error so it can be diagnosed
            self._send_json(fallback_status, {
                "error": {
                    "message": "Both Gemini models failed",
                    "primary_model": PRIMARY_MODEL,
                    "primary_status": status,
                    "primary_error": result.get("error", {}),
                    "fallback_model": FALLBACK_MODEL,
                    "fallback_status": fallback_status,
                    "fallback_error": fallback_result.get("error", {}),
                }
            })

        except json.JSONDecodeError:
            self._send_json(400, {
                "error": {"message": "Invalid JSON request"}
            })

        except Exception as error:
            # Do not include API keys or request contents in this message
            self._send_json(500, {
                "error": {
                    "message": "Internal server error",
                    "detail": str(error)[:300],
                }
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
