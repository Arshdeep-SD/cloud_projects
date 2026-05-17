# Fetch and Process URLs

`fetch_and_process.py` is a Python script that reads a list of URLs from a file, fetches their content, and generates detailed metrics and summaries about the requests, including response times, content length, word count (for text content), and HTTP status codes. Errors are logged separately.

---

## Features

- Fetches multiple URLs from an input file.
- Measures response time for each request.
- Captures HTTP status codes and content length.
- Counts words in text-based responses.
- Logs errors to a file.
- Produces two output JSON files:
  - `responses.json` — detailed info per URL.
  - `summary.json` — aggregated statistics.
- Supports automatic creation of the output directory.

---

## Requirements

- Python 3.6 or higher
- Standard Python libraries only (`sys`, `json`, `time`, `datetime`, `os`, `re`, `urllib`)
- Docker (optional, for containerized usage)

---

## Usage

### Directly with Python

```bash
python fetch_and_process.py <input_file> <output_dir>
