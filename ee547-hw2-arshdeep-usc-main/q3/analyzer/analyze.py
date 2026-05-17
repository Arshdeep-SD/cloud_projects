#!/usr/bin/env python3
"""
Corpus Analyzer - performs global text analysis with n-grams and document similarity.
"""

import os
import time
import json
import re
from datetime import datetime, timezone
from itertools import combinations

STATUS_FILE = "/shared/status/process_complete.json"
IN_DIR = "/shared/processed"
OUT_DIR = "/shared/analysis"

def utc_now():
    return datetime.now(timezone.utc).isoformat()

def tokenize(text):
    """Lowercase word tokens for frequency counting."""
    return [w.lower() for w in re.findall(r'\b\w+\b', text)]

def jaccard_similarity(words1, words2):
    """Compute Jaccard similarity between two word sets."""
    set1, set2 = set(words1), set(words2)
    union = set1 | set2
    return len(set1 & set2) / len(union) if union else 0.0

def ngrams(words, n):
    """Generate n-grams from a list of words."""
    return zip(*(words[i:] for i in range(n)))

def main():
    print(f"[{utc_now()}] Analyzer starting", flush=True)

    # Wait for processor to finish
    while not os.path.exists(STATUS_FILE):
        print("Waiting for process_complete.json...", flush=True)
        time.sleep(2)

    os.makedirs(OUT_DIR, exist_ok=True)

    documents = []
    all_words = []
    word_freq = {}
    total_sentences = 0
    total_words = 0

    # Load processed documents
    for fname in sorted(os.listdir(IN_DIR)):
        if not fname.endswith(".json"):
            continue
        path = os.path.join(IN_DIR, fname)
        try:
            with open(path, "r", encoding="utf-8") as f:
                doc = json.load(f)
            text = doc.get("text", "")
            words = tokenize(text)
            documents.append({"file": fname, "words": words, "text": text})
            all_words.extend(words)
            total_words += len(words)
            # Count words for global frequency
            for w in words:
                word_freq[w] = word_freq.get(w, 0) + 1
            # Count sentences for readability
            sentences = [s for s in re.split(r'[.!?]', text) if s.strip()]
            total_sentences += len(sentences)
        except Exception as e:
            print(f"[{utc_now()}] Failed reading {fname}: {e}", flush=True)

    unique_words = len(word_freq)

    # Top 100 words
    top_words = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)[:100]
    top_100 = [{"word": w, "count": c, "frequency": c / total_words} for w, c in top_words]

    # Document similarity
    similarities = []
    for doc1, doc2 in combinations(documents, 2):
        sim = jaccard_similarity(doc1["words"], doc2["words"])
        similarities.append({"doc1": doc1["file"], "doc2": doc2["file"], "similarity": sim})

    # N-grams
    bigram_freq = {}
    trigram_freq = {}
    for doc in documents:
        words = doc["words"]
        for bg in ngrams(words, 2):
            bigram_freq[bg] = bigram_freq.get(bg, 0) + 1
        for tg in ngrams(words, 3):
            trigram_freq[tg] = trigram_freq.get(tg, 0) + 1

    top_bigrams = [{"bigram": " ".join(k), "count": v}
                   for k, v in sorted(bigram_freq.items(), key=lambda x: x[1], reverse=True)[:20]]
    top_trigrams = [{"trigram": " ".join(k), "count": v}
                    for k, v in sorted(trigram_freq.items(), key=lambda x: x[1], reverse=True)[:20]]

    # Readability metrics
    avg_sentence_length = total_words / total_sentences if total_sentences else 0.0
    avg_word_length = sum(len(w) for w in all_words) / total_words if total_words else 0.0
    complexity_score = avg_sentence_length * avg_word_length

    report = {
        "processing_timestamp": utc_now(),
        "documents_processed": len(documents),
        "total_words": total_words,
        "unique_words": unique_words,
        "top_100_words": top_100,
        "document_similarity": similarities,
        "top_bigrams": top_bigrams,
        "top_trigrams": top_trigrams,
        "readability": {
            "avg_sentence_length": avg_sentence_length,
            "avg_word_length": avg_word_length,
            "complexity_score": complexity_score
        }
    }

    # Write final report
    out_path = os.path.join(OUT_DIR, "final_report.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    print(f"[{utc_now()}] Analyzer complete", flush=True)
    while True:
        time.sleep(60)

if __name__ == "__main__":
    main()
