#!/usr/bin/env python3

import sys
import json
import time
import datetime
import os
import re
import urllib.request
import urllib.error


def utc_now():
    return datetime.datetime.utcnow().isoformat(timespec="milliseconds") + "Z"


def is_text_content(content_type):
    return content_type is not None and "text" in content_type.lower()


def count_words(text):
    return len(re.findall(r"[A-Za-z0-9]+", text))


def main():
    if len(sys.argv) != 3:
        print("Usage: fetch_and_process.py <input_file> <output_dir>", file=sys.stderr)
        sys.exit(1)

    input_file = sys.argv[1]
    output_dir = sys.argv[2]

    os.makedirs(output_dir, exist_ok=True)

    responses = []
    errors_log_path = os.path.join(output_dir, "errors.log")

    processing_start = utc_now()

    total_bytes_downloaded = 0
    successful_requests = 0
    failed_requests = 0
    status_code_distribution = {}

    with open(input_file, "r", encoding="utf-8") as f:
        urls = [line.strip() for line in f if line.strip()]

    for url in urls:
        timestamp = utc_now()
        start_time = time.time()

        response_data = {
            "url": url,
            "status_code": None,
            "response_time_ms": None,
            "content_length": 0,
            "word_count": None,
            "timestamp": timestamp,
            "error": None
        }

        try:
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=10) as resp:
                elapsed_ms = (time.time() - start_time) * 1000.0
                body = resp.read()

                status_code = resp.getcode()
                content_type = resp.headers.get("Content-Type", "")

                response_data["status_code"] = status_code
                response_data["response_time_ms"] = elapsed_ms
                response_data["content_length"] = len(body)

                total_bytes_downloaded += len(body)
                successful_requests += 1

                status_code_distribution[str(status_code)] = (
                    status_code_distribution.get(str(status_code), 0) + 1
                )

                if is_text_content(content_type):
                    charset_match = re.search(r"charset=([^\s;]+)", content_type, re.I)
                    charset = charset_match.group(1) if charset_match else "utf-8"
                    text = body.decode(charset, errors="ignore")
                    response_data["word_count"] = count_words(text)

        except urllib.error.HTTPError as e:
            elapsed_ms = (time.time() - start_time) * 1000.0
            response_data["status_code"] = e.code
            response_data["response_time_ms"] = elapsed_ms
            response_data["error"] = str(e)

            failed_requests += 1
            status_code_distribution[str(e.code)] = (
                status_code_distribution.get(str(e.code), 0) + 1
            )

            with open(errors_log_path, "a", encoding="utf-8") as ef:
                ef.write(f"[{timestamp}] {url}: {e}\n")

        except Exception as e:
            elapsed_ms = (time.time() - start_time) * 1000.0
            response_data["response_time_ms"] = elapsed_ms
            response_data["error"] = str(e)

            failed_requests += 1

            with open(errors_log_path, "a", encoding="utf-8") as ef:
                ef.write(f"[{timestamp}] {url}: {e}\n")

        responses.append(response_data)

    processing_end = utc_now()

    avg_response_time = (
        sum(r["response_time_ms"] for r in responses if r["response_time_ms"] is not None)
        / len(responses)
        if responses
        else 0.0
    )
    


    summary = {
        "total_urls": len(urls),
        "successful_requests": successful_requests,
        "failed_requests": failed_requests,
        "average_response_time_ms": avg_response_time,
        "total_bytes_downloaded": total_bytes_downloaded,
        "status_code_distribution": status_code_distribution,
        "processing_start": processing_start,
        "processing_end": processing_end
    }

    with open(os.path.join(output_dir, "responses.json"), "w", encoding="utf-8") as rf:
        json.dump(responses, rf, indent=2)

    with open(os.path.join(output_dir, "summary.json"), "w", encoding="utf-8") as sf:
        json.dump(summary, sf, indent=2)


if __name__ == "__main__":
    main()
