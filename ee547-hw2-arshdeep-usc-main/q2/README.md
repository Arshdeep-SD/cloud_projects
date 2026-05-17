# ArXiv Abstract Processor

`arxiv_processor.py` is a Python script that queries the ArXiv API for papers based on a search term, processes abstracts, and generates detailed statistics on word usage, sentence structure, technical terms, and category distribution.  

It outputs both per-paper data and corpus-wide analyses in JSON format, and logs progress and errors to a log file.

---

## Features

- Fetches papers from ArXiv API based on a query.
- Limits results to 1–100 papers.
- Processes abstracts to extract:
  - Total and unique word counts
  - Sentence statistics (length, average words)
  - Top 20 words excluding stopwords
  - Technical terms (uppercase, numeric, hyphenated)
- Tracks category distributions across papers.
- Generates per-paper JSON and corpus-wide analysis JSON.
- Logs processing steps and network errors.

---

## Requirements

- Python 3.6 or higher
- Standard Python libraries: `sys`, `json`, `urllib`, `xml`, `datetime`, `time`, `re`, `os`
- `stopwords.py` file containing a `STOPWORDS` list
- Docker (optional, for containerized usage)

---

## Usage

### Directly with Python

```bash
python arxiv_processor.py <query> <max_results> <output_dir>
