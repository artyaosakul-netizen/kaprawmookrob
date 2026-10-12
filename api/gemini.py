"""Vercel Serverless Function — Gemini API proxy.

Required Vercel Environment Variable:
    GEMINI_API_KEY

This version logs useful error details to Vercel Runtime Logs without
printing the API key or the user's request body.
"""

import json
import os
import random
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler


# Keep the configured model names unchanged.
PRIMARY_MODEL = "gemini-3.8-flash"
FALLBACK_MODEL = "gemini-3.6-flash"

RETRYABLE_STATUS = {408, 429, 500, 502, 503, 504}
MAX_REQUEST_BYTES = 10_000_000
REQUEST_TIMEOUT_SECONDS = 10
MAX_ATTEMPTS = 2


def log_event(message):
    """Write diagnostic information to Vercel Runtime Logs."""
    print(f"[api/gemini] {message}", flush=True)


def safe_error_message(data):
    """Extract a readable error message without exposing secrets."""
    if not isinstance(data, dict):
        return str(data)[:1000]

    error = data.get("error", data)
    if isinstance(error, dict):
        message = error.get("message") or error.get("status") or str(error)
        code = error.get("code")
        status = error.get("status")
        parts = []
        if code is not None:
            parts.append(f"code={code}")
        if status:
            parts.append(f"status={status}")
        parts.append(f"message={str(message)[:1000]}")
        return "; ".join(parts)

    return str(error)[:1000]


def call_gemini(model, request_data, api_key):
    """Call Gemini and return (HTTP status, decoded response)."""
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

    with urllib.request.urlopen(
        request, timeout=REQUEST_TIMEOUT_SECONDS
    ) as response:
        raw = response.read().decode("utf-8", errors="replace")
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            raise RuntimeError(
                f"Gemini returned non-JSON response (HTTP {response.status})"
            )
        return response.status, data


def call_with_retry(model, request_data, api_key):
    """Call a model, retrying transient errors once."""
    last_status = 503
    last_data = {
        "error": {"message": "Gemini request did not complete"}
    }

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            status, data = call_gemini(model, request_data, api_key)
            if status == 200:
                log_event(f"model={model} attempt={attempt} status=200")
            else:
                log_event(
                    f"model={model} attempt={attempt} status={status} "
                    f"error={safe_error_message(data)}"
                )
            return status, data

        except urllib.error.HTTPError as error:
            last_status = error.code
            try:
                raw = error.read().decode("utf-8", errors="replace")
                last_data = json.loads(raw)
            except (json.JSONDecodeError, UnicodeDecodeError, OSError):
                last_data = {
                    "error": {"message": f"HTTP {error.code}: {error.reason}"}
                }

            log_event(
                f"model={model} attempt={attempt} status={last_status} "
                f"error={safe_error_message(last_data)}"
            )

            if last_status not in RETRYABLE_STATUS:
                return last_status, last_data

        except (TimeoutError, OSError, urllib.error.URLError) as error:
            last_status = 503
            last_data = {
                "error": {
                    "message": (
                        "Gemini connection/timeout error: "
                        + str(error)[:500]
                    )
                }
            }
            log_event(
                f"model={model} attempt={attempt} status=503 "
                f"connection_error={type(error).__name__}: {str(error)[:500]}"
            )

        except Exception as error:
            last_status = 500
            last_data = {
                "error": {
                    "message": (
                        f"Unexpected Gemini error: {type(error).__name__}: "
                        f"{str(error)[:500]}"
                    )
                }
            }
            log_event(
                f"model={model} attempt={attempt} status=500 "
                f"unexpected_error={type(error).__name__}: {str(error)[:500]}"
            )
            # Unexpected errors are usually not fixed by retrying.
            return last_status, last_data

        if attempt < MAX_ATTEMPTS:
            time.sleep(0.5 + random.uniform(0, 0.5))

    return last_status, last_data


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            content_length_text = self.headers.get("Content-Length", "0")
            try:
                content_length = int(content_length_text)
            except (TypeError, ValueError):
                self._send_json(400, {"error": {"message": "Invalid Content-Length"}})
                return

            if content_length <= 0 or content_length > MAX_REQUEST_BYTES:
                self._send_json(
                    400,
                    {"error": {"message": "Invalid request body size"}},
                )
                return

            body = self.rfile.read(content_length)
            try:
                request_data = json.loads(body.decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                self._send_json(
                    400, {"error": {"message": "Invalid JSON request"}}
                )
                return

            if not isinstance(request_data, dict):
                self._send_json(
                    400,
                    {"error": {"message": "JSON request must be an object"}},
                )
                return

            api_key = os.environ.get("GEMINI_API_KEY")
            if not api_key:
                log_event("configuration_error=GEMINI_API_KEY is missing")
                self._send_json(
                    500,
                    {
                        "error": {
                            "message": "GEMINI_API_KEY not configured on server"
                        }
                    },
                )
                return

            log_event("request_started route=/api/gemini")

            primary_status, primary_result = call_with_retry(
                PRIMARY_MODEL, request_data, api_key
            )

            if primary_status == 200:
                self._send_json(200, primary_result)
                return

            # Try fallback after transient errors or an unavailable model.
            if primary_status in RETRYABLE_STATUS or primary_status == 404:
                log_event(
                    f"primary_failed model={PRIMARY_MODEL} "
                    f"status={primary_status}; trying fallback={FALLBACK_MODEL}"
                )
                fallback_status, fallback_result = call_with_retry(
                    FALLBACK_MODEL, request_data, api_key
                )

                if fallback_status == 200:
                    log_event(f"fallback_succeeded model={FALLBACK_MODEL}")
                    self._send_json(200, fallback_result)
                    return

                log_event(
                    f"both_models_failed primary_status={primary_status} "
                    f"fallback_status={fallback_status}"
                )
                self._send_json(
                    fallback_status if fallback_status >= 400 else 503,
                    {
                        "error": {
                            "message": "Both Gemini models failed",
                            "primary_model": PRIMARY_MODEL,
                            "primary_status": primary_status,
                            "primary_error": primary_result.get("error", {}),
                            "fallback_model": FALLBACK_MODEL,
                            "fallback_status": fallback_status,
                            "fallback_error": fallback_result.get("error", {}),
                        }
                    },
                )
                return

            log_event(
                f"primary_permanent_failure model={PRIMARY_MODEL} "
                f"status={primary_status} "
                f"error={safe_error_message(primary_result)}"
            )
            self._send_json(
                primary_status if 400 <= primary_status <= 599 else 502,
                {
                    "error": {
                        "message": "Gemini API request failed",
                        "model": PRIMARY_MODEL,
                        "status": primary_status,
                        "details": primary_result.get("error", {}),
                    }
                },
            )

        except Exception as error:
            log_event(
                f"handler_error={type(error).__name__}: {str(error)[:500]}"
            )
            self._send_json(
                500,
                {
                    "error": {
                        "message": "Internal server error",
                        "detail": f"{type(error).__name__}: {str(error)[:300]}",
                    }
                },
            )

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _send_json(self, status, data):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        # Keep normal access logs quiet; diagnostic logs above remain visible.
        return
