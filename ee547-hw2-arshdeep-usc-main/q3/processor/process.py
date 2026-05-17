#!/usr/bin/env python3
"""
HTML Processor - extracts text and metadata from fetched HTML.
"""

import os
import time
import json
import re
from datetime import datetime, timezone

STATUS_FILE = "/shared/status/fetch_complete.json"
RAW_DIR = "/shared/raw"
OUT_DIR = "/shared/processed"
STATUS_OUT = "/shared/status/process_complete.json"

def utc_now():
    return datetime.now(timezone.utc).isoformat()

def strip_html(html_content):
    # Remove script and style blocks
    html_content = re.sub(
        r'<script[^>]*>.*?</script>',
        '',
        html_content,
        flags=re.DOTALL | re.IGNORECASE
    )
    html_content = re.sub(
        r'<style[^>]*>.*?</style>',
        '',
        html_content,
        flags=re.DOTALL | re.IGNORECASE
    )

    # Extract links and images
    links = re.findall(r'href=[\'"]?([^\'" >]+)', html_content, flags=re.IGNORECASE)
    images = re.findall(r'src=[\'"]?([^\'" >]+)', html_content, flags=re.IGNORECASE)

    # Remove all HTML tags
    text = re.sub(r'<[^>]+>', ' ', html_content)
    text = re.sub(r'\s+', ' ', text).strip()

    return text, links, images

def analyze_text(text):
    words = re.findall(r'\b\w+\b', text)
    sentences = [s.strip() for s in re.split(r'[.!?]', text) if s.strip()]
    paragraphs = [p.strip() for p in re.split(r'\n\s*\n', text) if p.strip()]

    word_count = len(words)
    sentence_count = len(sentences)
    paragraph_count = len(paragraphs)
    avg_word_length = sum(len(w) for w in words) / word_count if word_count else 0.0

    return {
        "word_count": word_count,
        "sentence_count": sentence_count,
        "paragraph_count": paragraph_count,
        "avg_word_length": avg_word_length
    }

def main():
    print(f"[{utc_now()}] Processor starting", flush=True)

    os.makedirs(OUT_DIR, exist_ok=True)
    os.makedirs("/shared/status", exist_ok=True)

    # Wait for fetcher to finish
    while not os.path.exists(STATUS_FILE):
        print("Waiting for fetch_complete.json...", flush=True)
        time.sleep(2)

    processed_files = []

    for fname in sorted(os.listdir(RAW_DIR)):
        if not fname.endswith(".html"):
            continue

        src_path = os.path.join(RAW_DIR, fname)
        out_path = os.path.join(OUT_DIR, fname.replace(".html", ".json"))

        try:
            with open(src_path, "r", encoding="utf-8", errors="ignore") as f:
                html = f.read()

            text, links, images = strip_html(html)
            stats = analyze_text(text)

            result = {
                "source_file": fname,
                "text": text,
                "statistics": stats,
                "links": links,
                "images": images,
                "processed_at": utc_now()
            }

            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(result, f, indent=2)

            processed_files.append(fname)

        except Exception as e:
            print(f"[{utc_now()}] Failed processing {fname}: {e}", flush=True)

    # Write process completion status
    status = {
        "timestamp": utc_now(),
        "files_processed": len(processed_files),
        "files": processed_files
    }

    with open(STATUS_OUT, "w", encoding="utf-8") as f:
        json.dump(status, f, indent=2)

    print(f"[{utc_now()}] Processor complete", flush=True)

if __name__ == "__main__":
    main()
