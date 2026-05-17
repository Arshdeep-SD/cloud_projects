# Multi-Container Text Processing Pipeline

A Docker Compose pipeline that fetches web pages, processes HTML, and performs corpus-wide text analysis.

---

## Architecture

Three sequential containers communicate via a shared volume (`/shared/`):


| Container   | Role |
|------------|------|
| fetcher    | Downloads URLs → `/shared/raw/` |
| processor  | Extracts text, links, images, stats → `/shared/processed/` |
| analyzer   | Computes word frequency, n-grams, similarity, readability → `/shared/analysis/` |

Status signals are stored in `/shared/status/` to coordinate stages.

---

## Usage

```bash
./run_pipeline.sh <url1> [url2 ...]
