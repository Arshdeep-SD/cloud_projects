#!/usr/bin/env python3

import sys
import json
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
import datetime
import time
import re
import os

from stopwords import STOPWORDS

ARXIV_API = "http://export.arxiv.org/api/query"


# ---------- Utilities ----------

def utc_now():
    return datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z"


def log(log_path, message):
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(f"[{utc_now()}] {message}\n")


# ---------- Networking ----------

def fetch_arxiv(query, max_results, log_path):
    url = (
        f"{ARXIV_API}"
        f"?search_query={query}"
        f"&start=0"
        f"&max_results={max_results}"
        f"&sortBy=lastUpdatedDate"
        f"&sortOrder=descending"
    )

    for attempt in range(3):
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "arxiv-processor/1.0 (educational use)"}
            )
            with urllib.request.urlopen(req) as resp:
                return resp.read()

        except urllib.error.HTTPError as e:
            if e.code == 429:
                log(log_path, "Received 429 rate limit. Waiting 3 seconds before retry.")
                time.sleep(3)
            else:
                log(log_path, f"HTTP Error: {e}")
                sys.exit(1)

        except Exception as e:
            log(log_path, f"Network error: {e}")
            sys.exit(1)

    log(log_path, "Exceeded maximum retry attempts due to rate limiting.")
    sys.exit(1)


# ---------- Text Processing ----------

def tokenize(text):
    return re.findall(r"[A-Za-z0-9\-]+", text)


def split_sentences(text):
    return [s.strip() for s in re.split(r"[.!?]", text) if s.strip()]


def process_abstract(text):
    tokens = tokenize(text)
    tokens_lower = [w.lower() for w in tokens]

    # Total & unique words (INCLUDING stopwords)
    total_words = len(tokens)
    unique_words = len(set(tokens_lower))

    # Word frequency excluding stopwords
    word_freq = {}
    for w in tokens_lower:
        if w not in STOPWORDS:
            word_freq[w] = word_freq.get(w, 0) + 1

    # Top 20 most frequent words (excluding stopwords)
    top_20 = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)[:20]

    # Sentence analysis
    sentences = split_sentences(text)
    sentence_lengths = [len(tokenize(s)) for s in sentences if tokenize(s)]

    total_sentences = len(sentence_lengths)
    avg_words_per_sentence = (
        sum(sentence_lengths) / total_sentences if total_sentences else 0.0
    )

    longest_sentence = max(sentence_lengths) if sentence_lengths else 0
    shortest_sentence = min(sentence_lengths) if sentence_lengths else 0

    avg_word_length = (
        sum(len(w) for w in tokens) / total_words if total_words else 0.0
    )

    # Technical terms (preserve original case)
    uppercase_terms = sorted({w for w in tokens if re.search(r"[A-Z]", w)})
    numeric_terms = sorted({w for w in tokens if re.search(r"\d", w)})
    hyphenated_terms = sorted({w for w in tokens if "-" in w})

    return {
        "total_words": total_words,
        "unique_words": unique_words,
        "total_sentences": total_sentences,
        "avg_words_per_sentence": avg_words_per_sentence,
        "avg_word_length": avg_word_length,
        "longest_sentence_words": longest_sentence,
        "shortest_sentence_words": shortest_sentence,
        "top_20_words": [
            {"word": w, "frequency": f} for w, f in top_20
        ],
        "word_freq": word_freq,
        "uppercase_terms": uppercase_terms,
        "numeric_terms": numeric_terms,
        "hyphenated_terms": hyphenated_terms,
    }


# ---------- Main ----------

def main():
    if len(sys.argv) != 4:
        print("Usage: arxiv_processor.py <query> <max_results> <output_dir>", file=sys.stderr)
        sys.exit(1)

    query = sys.argv[1]
    max_results = int(sys.argv[2])
    output_dir = sys.argv[3]

    if not (1 <= max_results <= 100):
        print("max_results must be between 1 and 100", file=sys.stderr)
        sys.exit(1)

    os.makedirs(output_dir, exist_ok=True)

    log_path = os.path.join(output_dir, "processing.log")
    start_time = time.time()

    log(log_path, f"Starting ArXiv query: {query}")

    xml_data = fetch_arxiv(query, max_results, log_path)

    try:
        root = ET.fromstring(xml_data)
    except ET.ParseError as e:
        log(log_path, f"Invalid XML received: {e}")
        sys.exit(1)

    ns = {"atom": "http://www.w3.org/2005/Atom"}
    entries = root.findall("atom:entry", ns)

    log(log_path, f"Fetched {len(entries)} results from ArXiv API")

    papers = []
    global_word_freq = {}
    doc_freq = {}
    category_dist = {}
    all_upper = set()
    all_numeric = set()
    all_hyphenated = set()
    abstract_lengths = []

    for entry in entries:
        try:
            arxiv_id = entry.find("atom:id", ns).text.split("/")[-1]
            title = entry.find("atom:title", ns).text.strip()
            abstract = entry.find("atom:summary", ns).text.strip()
            published = entry.find("atom:published", ns).text
            updated = entry.find("atom:updated", ns).text
            authors = [a.find("atom:name", ns).text for a in entry.findall("atom:author", ns)]
            categories = [c.attrib["term"] for c in entry.findall("atom:category", ns)]
        except Exception:
            log(log_path, "Skipping paper due to missing required fields")
            continue

        log(log_path, f"Processing paper: {arxiv_id}")

        stats = process_abstract(abstract)
        abstract_lengths.append(stats["total_words"])

        for w, c in stats["word_freq"].items():
            global_word_freq[w] = global_word_freq.get(w, 0) + c
            doc_freq[w] = doc_freq.get(w, 0) + 1

        all_upper.update(stats["uppercase_terms"])
        all_numeric.update(stats["numeric_terms"])
        all_hyphenated.update(stats["hyphenated_terms"])

        for cat in categories:
            category_dist[cat] = category_dist.get(cat, 0) + 1

        papers.append({
            "arxiv_id": arxiv_id,
            "title": title,
            "authors": authors,
            "abstract": abstract,
            "categories": categories,
            "published": published,
            "updated": updated,
            "abstract_stats": {
                "total_words": stats["total_words"],
                "unique_words": stats["unique_words"],
                "total_sentences": stats["total_sentences"],
                "avg_words_per_sentence": stats["avg_words_per_sentence"],
                "avg_word_length": stats["avg_word_length"],
                "longest_sentence_words": stats["longest_sentence_words"],
                "shortest_sentence_words": stats["shortest_sentence_words"],
                "top_20_words": stats["top_20_words"]
            }
        })

    top_words = sorted(global_word_freq.items(), key=lambda x: x[1], reverse=True)[:50]

    corpus_analysis = {
        "query": query,
        "papers_processed": len(papers),
        "processing_timestamp": utc_now(),
        "corpus_stats": {
            "total_abstracts": len(papers),
            "total_words": sum(abstract_lengths),
            "unique_words_global": len(global_word_freq),
            "avg_abstract_length": (
                sum(abstract_lengths) / len(abstract_lengths)
                if abstract_lengths else 0.0
            ),
            "longest_abstract_words": max(abstract_lengths) if abstract_lengths else 0,
            "shortest_abstract_words": min(abstract_lengths) if abstract_lengths else 0
        },
        "top_50_words": [
            {"word": w, "frequency": f, "documents": doc_freq.get(w, 0)}
            for w, f in top_words
        ],
        "technical_terms": {
            "uppercase_terms": sorted(all_upper),
            "numeric_terms": sorted(all_numeric),
            "hyphenated_terms": sorted(all_hyphenated)
        },
        "category_distribution": category_dist
    }

    with open(os.path.join(output_dir, "papers.json"), "w", encoding="utf-8") as f:
        json.dump(papers, f, indent=2, ensure_ascii=False)

    with open(os.path.join(output_dir, "corpus_analysis.json"), "w", encoding="utf-8") as f:
        json.dump(corpus_analysis, f, indent=2, ensure_ascii=False)

    elapsed = time.time() - start_time
    log(log_path, f"Completed processing: {len(papers)} papers in {elapsed:.2f} seconds")


if __name__ == "__main__":
    main()
