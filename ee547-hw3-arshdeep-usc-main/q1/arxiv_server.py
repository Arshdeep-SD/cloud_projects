import json
import sys
import os
import re
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

# ==============================
# File Paths
# ==============================

BASE_DIR = os.path.dirname(__file__)
DATA_DIR = os.path.join(BASE_DIR, "sample_data")

PAPERS_FILE = os.path.join(DATA_DIR, "papers.json")
CORPUS_FILE = os.path.join(DATA_DIR, "corpus_analysis.json")

papers = []
corpus = {}

# ==============================
# Data Loading
# ==============================

def load_data():
    global papers, corpus

    try:
        with open(PAPERS_FILE, "r", encoding="utf-8") as f:
            papers = json.load(f)
    except Exception:
        papers = []

    try:
        with open(CORPUS_FILE, "r", encoding="utf-8") as f:
            corpus = json.load(f)
    except Exception:
        corpus = {}

# ==============================
# Logging
# ==============================

def log_request(method, path, status_code, message):
    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {method} {path} - {status_code} {message}")

# ==============================
# HTTP Handler
# ==============================

class ArxivHandler(BaseHTTPRequestHandler):

    # ---------- Utilities ----------

    def send_json(self, status_code, data):
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode("utf-8"))

    def parse_request_path(self):
        parsed = urlparse(self.path)
        return parsed.path, parse_qs(parsed.query)

    # ---------- GET Router ----------

    def do_GET(self):
        try:
            path, query = self.parse_request_path()

            if path == "/papers":
                self.handle_papers()

            elif path.startswith("/papers/"):
                arxiv_id = path.split("/")[-1]
                self.handle_paper_detail(arxiv_id)

            elif path == "/search":
                self.handle_search(query)

            elif path == "/stats":
                self.handle_stats()

            else:
                self.send_json(404, {"error": "Not Found"})
                log_request("GET", path, 404, "Not Found")

        except Exception:
            self.send_json(500, {"error": "Internal Server Error"})
            log_request("GET", self.path, 500, "Internal Server Error")

    # ==============================
    # Endpoints
    # ==============================

    # -------- GET /papers --------
    def handle_papers(self):
        response = [
            {
                "arxiv_id": p.get("arxiv_id"),
                "title": p.get("title"),
                "authors": p.get("authors", []),
                "categories": p.get("categories", [])
            }
            for p in papers
        ]

        self.send_json(200, response)
        log_request("GET", "/papers", 200, f"OK ({len(response)} results)")

    # -------- GET /papers/{id} --------
    def handle_paper_detail(self, arxiv_id):
        for p in papers:
            if p.get("arxiv_id") == arxiv_id:

                response = {
                    "arxiv_id": p.get("arxiv_id"),
                    "title": p.get("title"),
                    "authors": p.get("authors", []),
                    "abstract": p.get("abstract", ""),
                    "categories": p.get("categories", []),
                    "published": p.get("published"),
                    "abstract_stats": {
                        "total_words": p.get("abstract_stats", {}).get("total_words"),
                        "unique_words": p.get("abstract_stats", {}).get("unique_words"),
                        "total_sentences": p.get("abstract_stats", {}).get("total_sentences")
                    }
                }

                self.send_json(200, response)
                log_request("GET", f"/papers/{arxiv_id}", 200, "OK")
                return

        self.send_json(404, {"error": "Not Found"})
        log_request("GET", f"/papers/{arxiv_id}", 404, "Not Found")

    # -------- GET /search?q= --------
    def handle_search(self, query):
        if "q" not in query or not query["q"][0].strip():
            self.send_json(400, {"error": "Bad Request"})
            log_request("GET", "/search", 400, "Bad Request")
            return

        raw_query = query["q"][0]
        terms = re.findall(r'\w+', raw_query.lower())

        if not terms:
            self.send_json(400, {"error": "Bad Request"})
            log_request("GET", "/search", 400, "Bad Request")
            return

        results = []

        for p in papers:
            title = p.get("title", "").lower()
            abstract = p.get("abstract", "").lower()

            # Require ALL terms to appear
            if not all(term in title or term in abstract for term in terms):
                continue

            score = 0
            matches_in = set()

            for term in terms:
                t_count = title.count(term)
                a_count = abstract.count(term)

                if t_count > 0:
                    matches_in.add("title")
                if a_count > 0:
                    matches_in.add("abstract")

                score += t_count + a_count

            results.append({
                "arxiv_id": p.get("arxiv_id"),
                "title": p.get("title"),
                "match_score": score,
                "matches_in": list(matches_in)
            })

        results.sort(key=lambda x: x["match_score"], reverse=True)

        response = {
            "query": raw_query,
            "results": results
        }

        self.send_json(200, response)
        log_request("GET", "/search", 200, f"OK ({len(results)} results)")

    # -------- GET /stats --------
    def handle_stats(self):
        corpus_stats = corpus.get("corpus_stats", {})
        top_words = corpus.get("top_50_words", [])
        category_distribution = corpus.get("category_distribution", {})

        response = {
            "total_papers": len(papers),
            "total_words": corpus_stats.get("total_words", 0),
            "unique_words": corpus_stats.get("unique_words_global", 0),
            "top_10_words": [
                {"word": w["word"], "frequency": w["frequency"]}
                for w in top_words[:10]
            ],
            "category_distribution": category_distribution
        }

        self.send_json(200, response)
        log_request("GET", "/stats", 200, "OK")


# ==============================
# Server Runner
# ==============================

def run_server(port=8080):
    load_data()
    server = ThreadingHTTPServer(("0.0.0.0", port), ArxivHandler)
    print(f"Server running on port {port}")
    server.serve_forever()

if __name__ == "__main__":
    port = 8080
    if len(sys.argv) > 1:
        port = int(sys.argv[1])
    run_server(port)