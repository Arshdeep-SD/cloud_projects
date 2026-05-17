import json
import time
import random
import urllib.request
import urllib.error
import socket
from datetime import datetime, timezone
from typing import Dict

# -------------------- Time Utility --------------------

def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")

# -------------------- Response Handler --------------------

class ResponseHandler:
    def __init__(self, log_path: str, validator=None):
        self.log_path = log_path
        self.validator = validator
        self._fh = open(log_path, "w", encoding="utf-8")

    def _log(self, event: str, **fields):
        record = {"timestamp": utc_now(), "event": event, **fields}
        self._fh.write(json.dumps(record) + "\n")
        self._fh.flush()

    def _record(self, url: str, callback: str):
        if self.validator:
            self.validator.add_callback(url, callback)

    def on_success(self, url, status, body, latency_ms):
        self._record(url, "on_success")
        self._log("success", url=url, status=status, latency_ms=latency_ms)

    def on_client_error(self, url, status, body):
        self._record(url, "on_client_error")
        self._log("client_error", url=url, status=status)

    def on_server_error(self, url, status, attempt):
        self._record(url, "on_server_error")
        self._log("server_error", url=url, status=status, attempt=attempt)

    def on_timeout(self, url, attempt, timeout_sec):
        self._record(url, "on_timeout")
        self._log("timeout", url=url, attempt=attempt, timeout_sec=timeout_sec)

    def on_connection_error(self, url, attempt, error):
        self._record(url, "on_connection_error")
        self._log("connection_error", url=url, attempt=attempt, error=error)

    def on_slow_response(self, url, latency_ms):
        self._record(url, "on_slow_response")
        self._log("slow_response", url=url, latency_ms=latency_ms)

    def on_retry(self, url, attempt, wait_ms, reason):
        self._record(url, "on_retry")
        self._log("retry", url=url, attempt=attempt, wait_ms=wait_ms, reason=reason)

    def on_body_match(self, url, keyword):
        self._record(url, "on_body_match")
        self._log("body_match", url=url, keyword=keyword)

    def on_max_retries(self, url, attempts, last_error):
        self._record(url, "on_max_retries")
        self._log("max_retries", url=url, attempts=attempts, last_error=last_error)

    def close(self):
        self._fh.close()

# -------------------- Robust HTTP Client --------------------

class RobustHTTPClient:
    SLOW_THRESHOLD_MS = 500.0
    MAX_RETRIES = 3
    BASE_TIMEOUT_SEC = 1.25
    INITIAL_BACKOFF_MS = 100.0
    MAX_BACKOFF_MS = 1250.0
    BACKOFF_MULTIPLIER = 2.0
    MONITORED_KEYWORDS = ["foo", "bar", "baz"]

    def __init__(self, handler: ResponseHandler):
        self.handler = handler
        self.total_requests = 0
        self.retries = 0
        self.latencies = []
        self.slow_responses = 0
        self.by_status: Dict[str, int] = {}
        self.by_error: Dict[str, int] = {}

    def calculate_backoff(self, attempt: int) -> float:
        base = self.INITIAL_BACKOFF_MS * (self.BACKOFF_MULTIPLIER ** attempt)
        jitter = random.uniform(0, 0.1 * base)
        return min(base + jitter, self.MAX_BACKOFF_MS)

    # -------------------- Fetch a single URL --------------------
    def fetch(self, url: str) -> bool:
        last_error = None

        for attempt in range(self.MAX_RETRIES + 1):
            self.total_requests += 1
            start = time.perf_counter()

            try:
                req = urllib.request.Request(url, method="GET")
                with urllib.request.urlopen(req, timeout=self.BASE_TIMEOUT_SEC) as resp:
                    body = resp.read()
                    status = resp.status

                latency_ms = (time.perf_counter() - start) * 1000.0
                self.latencies.append(latency_ms)
                self.by_status[str(status)] = self.by_status.get(str(status), 0) + 1

                if 200 <= status < 300:
                    self.handler.on_success(url, status, body, latency_ms)

                    if latency_ms > self.SLOW_THRESHOLD_MS:
                        self.slow_responses += 1
                        self.handler.on_slow_response(url, latency_ms)

                    body_text = body.decode("utf-8", errors="ignore")
                    for kw in self.MONITORED_KEYWORDS:
                        if kw in body_text:
                            self.handler.on_body_match(url, kw)

                    return True

                if 400 <= status < 500:
                    self.handler.on_client_error(url, status, body)
                    self.by_error[f"client_error_{status}"] = self.by_error.get(f"client_error_{status}", 0) + 1
                    return False

                if 500 <= status < 600:
                    self.handler.on_server_error(url, status, attempt)
                    last_error = f"server_error_{status}"
                    self.by_error[last_error] = self.by_error.get(last_error, 0) + 1

            except urllib.error.HTTPError as e:
                status = e.code
                self.by_status[str(status)] = self.by_status.get(str(status), 0) + 1

                if 400 <= status < 500:
                    self.handler.on_client_error(url, status, e.read())
                    self.by_error[f"client_error_{status}"] = self.by_error.get(f"client_error_{status}", 0) + 1
                    return False

                if 500 <= status < 600:
                    self.handler.on_server_error(url, status, attempt)
                    last_error = f"server_error_{status}"
                    self.by_error[last_error] = self.by_error.get(last_error, 0) + 1

            except socket.timeout:
                self.by_error["timeout"] = self.by_error.get("timeout", 0) + 1
                self.handler.on_timeout(url, attempt, self.BASE_TIMEOUT_SEC)
                last_error = "timeout"

            except Exception as e:
                self.by_error["connection"] = self.by_error.get("connection", 0) + 1
                self.handler.on_connection_error(url, attempt, str(e))
                last_error = "connection"

            # Retry logic
            if attempt < self.MAX_RETRIES:
                wait_ms = self.calculate_backoff(attempt)
                self.retries += 1
                self.handler.on_retry(url, attempt + 1, wait_ms, last_error)
                time.sleep(wait_ms / 1000.0)
            else:
                self.handler.on_max_retries(url, attempt + 1, last_error)

        return False

    # -------------------- Fetch all URLs from provider --------------------
    def fetch_all(self, provider) -> dict:
        successful = 0
        failed = 0
        categorized_errors: Dict[str, int] = {}

        while (url := provider.next_url()) is not None:
            if self.fetch(url):
                successful += 1
            else:
                failed += 1

        # Copy self.by_error to categorized_errors for summary
        for err_type, count in self.by_error.items():
            categorized_errors[err_type] = count

        avg_latency = sum(self.latencies) / len(self.latencies) if self.latencies else 0.0

        return {
            "total_urls": provider.total(),
            "successful": successful,
            "failed": failed,
            "total_requests": self.total_requests,
            "retries": self.retries,
            "avg_latency_ms": round(avg_latency, 2),
            "slow_responses": self.slow_responses,
            "by_status": self.by_status,
            "by_error": categorized_errors
        }
