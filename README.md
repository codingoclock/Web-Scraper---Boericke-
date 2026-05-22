Boericke Scraper extracts the complete text of Boericke's Homoeopathic Materia Medica from homeoint.org and outputs a structured JSON dataset of every remedy (A–Z). Designed to power remedy search, repertorization engines, and AI case analysis pipelines at jarvis.care.

~600 remedies · full section-level structure · keyword extraction included

## **Prerequisites**

System prerequisites:
- Python 3.9 or higher
- pip
- Network access to homeoint.org

| Package | Version | Purpose |
|----------------|----------|--------------------------------|
| requests | 2.31.0 | HTTP client for fetching pages |
| beautifulsoup4 | 4.12.3 | HTML parsing |
| lxml | 5.2.1 | HTML parser backend for BS4 |

## **Installation**

```bash
git clone <repo-url>
cd boericke-scraper
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## **Usage**

1. Full run (A–Z):
```bash
python scraper.py
```

2. Resume interrupted run:
Re-run the same command. Already-scraped URLs are skipped automatically via source_url deduplication against the existing boericke_remedies.json. No flags needed.

3. What gets produced:
- boericke_remedies.json — full dataset, all remedies A–Z
- failed_urls.txt — any URLs that could not be fetched after 3 retries

## **Output Schema**

| Field | Type | Always Present | Description |
|---------------|----------------|----------------|-----------------------------------------------------------|
| abbreviation | string | Yes | Uppercase remedy code as shown in the letter index |
| full_name | string | Yes | Full Latin remedy name from the page heading |
| common_name | string or null | No | English or common name if present on the page |
| source_url | string | Yes | Canonical URL of the individual remedy page |
| letter | string | Yes | Single uppercase letter A–Z |
| general | string | Yes | Opening paragraphs before the first section heading |
| sections | dict[str, str] | Yes | Section title mapped to section text (Head, Stomach etc) |
| relationships | string or null | No | Cross-references to related remedies if present |
| keywords | list[str] | Yes | Top 10 symptom keywords extracted from remedy text |

## **Keyword Extraction**

Top 10 symptom keywords per remedy are pulled from the combined `general` and `sections` text using token frequency via `collections.Counter`. No external NLP libraries required. Output lives in the `keywords` field on every remedy object.

```json
  "keywords": ["burning", "anxiety", "restless", "thirst", "fever",
               "palpitation", "skin", "chest", "pain", "worse"]
```

## **Architecture & Design Notes**

Each function in the pipeline has one job, so there is always one obvious place to make a change. A crashed run resumes from the last completed letter — nothing is reprocessed. Pages that fail after 3 retries are logged to failed_urls.txt and skipped; one bad URL does not stop the run.

Adding new output fields or swapping in async fetching with httpx are the natural next steps — the JSON schema is additive so nothing downstream breaks.

## **Project Structure**

```
boericke-scraper/
├── scraper.py              # Core scraper — all pipeline logic
├── requirements.txt        # Pinned dependencies
├── README.md               # This file
├── boericke_remedies.json  # Full A–Z output (generated on run)
├── sample_output.json      # 5-remedy reference sample
└── failed_urls.txt         # Failed URLs after retries (generated on run)
```

## **Rate Limiting & Server Courtesy**

The scraper waits 1.5–3.0 seconds between requests to avoid overloading
homeoint.org, which is a small public-interest server. Do not reduce this
delay. HTTP errors are retried up to 3 times with exponential backoff 
before a URL is marked as failed.
