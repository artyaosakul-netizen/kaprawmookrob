"""Vercel Serverless Function — Gemini API proxy"""

import json
import os
import random
import time
import urllib.request
import urllib.error
from http.server import BaseHTTPRequestHandler


# ============================================================
# Gemini Models
# ============================================================

PRIMARY_MODEL = "gemini-3.8-flash"
FALLBACK_MODEL = "gemini-3.6-flash"


# ============================================================
# Temporary errors that are safe to retry
# ============================================================

RETRYABLE_STATUS = {
    408,
    429,
    500,
    502,
    503,
    504,
}


# ============================================================
# Call Gemini API
# ============================================================

def call_gemini(model, request_data, api_key):
    """Call Gemini API and return (status_code, response_data)."""

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

    # Important:
    # Keep this short so Vercel does not hit its ~60 second limit.
    with urllib.request.urlopen(request, timeout=15) as response:

        data = json.loads(
            response.read().decode("utf-8")
        )

        return response.status, data


# ============================================================
# Retry Gemini
# ============================================================

def call_with_retry(model, request_data, api_key):
    """
    Try Gemini a maximum of 2 times.

    This prevents the Vercel function from running
    for too long and reaching the serverless timeout.
    """

    last_status = 503

    last_data = {
        "error": {
            "message": "Gemini request failed"
        }
    }

    for attempt in range(2):

        try:

            status, data = call_gemini(
                model,
                request_data,
                api_key
            )

            return status, data

        except urllib.error.HTTPError as error:

            last_status = error.code

            try:

                raw = error.read().decode(
                    "utf-8",
                    errors="replace"
                )

                last_data = json.loads(raw)

            except Exception:

                last_data = {
                    "error": {
                        "message": str(error)
                    }
                }

            # Do not retry permanent errors
            if error.code not in RETRYABLE_STATUS:
                return last_status, last_data

        except (
            TimeoutError,
            OSError,
            urllib.error.URLError
        ) as error:

            last_status = 503

            last_data = {
                "error": {
                    "message": (
                        "Gemini connection/timeout error: "
                        + str(error)[:300]
                    )
                }
            }

        except Exception as error:

            last_status = 500

            last_data = {
                "error": {
                    "message": (
                        "Unexpected Gemini error: "
                        + str(error)[:300]
                    )
                }
            }

        # Retry only once
        if attempt == 0:

            # Small exponential backoff + jitter
            time.sleep(
                1 + random.uniform(0, 0.5)
            )

    return last_status, last_data


# ============================================================
# Vercel Handler
# ============================================================

class handler(BaseHTTPRequestHandler):

    def do_POST(self):

        try:

            # ------------------------------------------------
            # Read request body
            # ------------------------------------------------

            content_length = int(
                self.headers.get(
                    "Content-Length",
                    "0"
                )
            )

            if (
                content_length <= 0
                or content_length > 10_000_000
            ):

                self._send_json(
                    400,
                    {
                        "error": {
                            "message":
                            "Invalid request body size"
                        }
                    }
                )

                return

            body = self.rfile.read(
                content_length
            )

            request_data = json.loads(body)

            # ------------------------------------------------
            # Get API Key
            # ------------------------------------------------

            api_key = os.environ.get(
                "GEMINI_API_KEY"
            )

            if not api_key:

                self._send_json(
                    500,
                    {
                        "error": {
                            "message":
                            "GEMINI_API_KEY not configured on server"
                        }
                    }
                )

                return

            # ------------------------------------------------
            # Try PRIMARY model
            # ------------------------------------------------

            primary_status, primary_result = (
                call_with_retry(
                    PRIMARY_MODEL,
                    request_data,
                    api_key
                )
            )

            # Success
            if primary_status == 200:

                self._send_json(
                    200,
                    primary_result
                )

                return

            # ------------------------------------------------
            # Try FALLBACK only when appropriate
            # ------------------------------------------------

            if (
                primary_status in RETRYABLE_STATUS
                or primary_status == 404
            ):

                fallback_status, fallback_result = (
                    call_with_retry(
                        FALLBACK_MODEL,
                        request_data,
                        api_key
                    )
                )

                # Fallback succeeded
                if fallback_status == 200:

                    self._send_json(
                        200,
                        fallback_result
                    )

                    return

                # Both failed
                self._send_json(
                    fallback_status,
                    {
                        "error": {
                            "message":
                            "Both Gemini models failed",

                            "primary_model":
                            PRIMARY_MODEL,

                            "primary_status":
                            primary_status,

                            "primary_error":
                            primary_result.get(
                                "error",
                                {}
                            ),

                            "fallback_model":
                            FALLBACK_MODEL,

                            "fallback_status":
                            fallback_status,

                            "fallback_error":
                            fallback_result.get(
                                "error",
                                {}
                            ),
                        }
                    }
                )

                return

            # ------------------------------------------------
            # Permanent error from PRIMARY
            # ------------------------------------------------

            self._send_json(
                primary_status,
                {
                    "error": {
                        "message":
                        "Gemini API request failed",

                        "model":
                        PRIMARY_MODEL,

                        "status":
                        primary_status,

                        "details":
                        primary_result.get(
                            "error",
                            {}
                        ),
                    }
                }
            )

        # ----------------------------------------------------
        # Invalid JSON
        # ----------------------------------------------------

        except json.JSONDecodeError:

            self._send_json(
                400,
                {
                    "error": {
                        "message":
                        "Invalid JSON request"
                    }
                }
            )

        # ----------------------------------------------------
        # Unexpected server error
        # ----------------------------------------------------

        except Exception as error:

            self._send_json(
                500,
                {
                    "error": {
                        "message":
                        "Internal server error",

                        "detail":
                        str(error)[:300]
                    }
                }
            )

    # ========================================================
    # Send JSON response
    # ========================================================

    def _send_json(self, status, data):

        body = json.dumps(
            data,
            ensure_ascii=False
        ).encode("utf-8")

        self.send_response(status)

        self.send_header(
            "Content-Type",
            "application/json; charset=utf-8"
        )

        self.send_header(
            "Access-Control-Allow-Origin",
            "*"
        )

        self.send_header(
            "Access-Control-Allow-Methods",
            "POST, OPTIONS"
        )

        self.send_header(
            "Access-Control-Allow-Headers",
            "Content-Type"
        )

        self.send_header(
            "Content-Length",
            str(len(body))
        )

        self.end_headers()

        self.wfile.write(body)

    # ========================================================
    # CORS preflight
    # ========================================================

    def do_OPTIONS(self):

        self.send_response(200)

        self.send_header(
            "Access-Control-Allow-Origin",
            "*"
        )

        self.send_header(
            "Access-Control-Allow-Methods",
            "POST, OPTIONS"
        )

        self.send_header(
            "Access-Control-Allow-Headers",
            "Content-Type"
        )

        self.end_headers()

    # ========================================================
    # Disable default logging
    # ========================================================

    def log_message(self, fmt, *args):
        return
