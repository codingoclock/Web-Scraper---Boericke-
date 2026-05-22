# boericke-scraper

Command-line tool to scrape homeopathic materia medica data from Boericke's Repertory to produce structured JSON datasets for downstream NLP and machine learning tasks.

## Prerequisites
- Python 3.9+
- pip

## Installation
1. Clone the repository:
   ```bash
   git clone <repository-url>
   cd boericke-scraper
   ```
2. Create and activate a virtual environment:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## How to Run
### Execution
```bash
python scraper.py
```

### Resume Behavior
- The scraper tracks progress locally. If execution is interrupted, restarting the script resumes from the last successfully parsed URL/remedy letter.
- URLs that fail to parse or return non-200 responses are written to `failed_urls.txt` for future retry.

### Produced Output Files
- `boericke_remedies.json`: Main output dataset containing a JSON array of parsed remedies.
- `sample_output.json`: A 5-remedy sample committed manually.
- `failed_urls.txt`: Text file listing URLs that failed to scrape.

## Output Fields
The output JSON file contains an array of remedy records. Below is the detailed schema for each remedy object:

| Field | Type | Always Present? | Description |
|---|---|---|---|
| `abbreviation` | string | Yes | The uppercase abbreviation of the remedy as shown in the letter index (e.g., `ABIES-C`). |
| `full_name` | string | Yes | The full Latin/scientific name extracted from the page title. |
| `common_name` | string \| null | No | The common or English name of the source substance (e.g., `Hemlock Spruce`). |
| `source_url` | string | Yes | The original URL of the individual scraped remedy page. |
| `letter` | string | Yes | The uppercase letter index grouping (A–Z) for this remedy. |
| `general` | string | Yes | The introductory or general summary text block before any subheadings. |
| `sections` | object | Yes | A dictionary mapping clinical organ systems (e.g., `Mind`, `Head`, `Eyes`) to their parsed text blocks. |
| `relationships` | string \| null | No | The raw text of the remedy relationship modalities, if present. |
| `keywords` | array of strings | Yes | Top clinically relevant words extracted by term frequency analysis. |

## Rate Limiting and Server Courtesy
- A delay of 0.5 to 1.0 second is enforced between requests to avoid overloading the target server.
- Request headers include a custom User-Agent identifying the crawler.
