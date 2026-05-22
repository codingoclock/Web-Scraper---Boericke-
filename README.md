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

The script extracts the top 10 symptom keywords per remedy from the combined text of the general field and all section values. It tokenizes text on non-alphabetic boundaries, removes common stopwords, and ranks term frequency using collections.Counter without requiring external NLP libraries. The output is saved directly into the keywords field in every remedy object, providing clean data for downstream semantic search, remedy clustering, and symptom-to-remedy mapping in the AI pipeline.

Example output:
```json
"keywords": ["burning", "anxiety", "restless", "thirst", "fever",
             "palpitation", "skin", "chest", "pain", "worse"]
```

## **Architecture & Design Notes**

The scraper uses single-purpose functions to make changes simple. Changing the output structure or target site format only requires modifying the specific parser or scraping function. The scraper writes accumulated records to the output file at the end of each letter index. If the process stops, restarting it skips already processed URLs. Pages that fail to load are recorded and skipped to prevent a single connection error from stopping the entire pipeline. Future updates can introduce async requests using httpx to increase speed, or upload results directly to MongoDB. The schema is additive, so adding fields does not break existing database readers.

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
