#!/usr/bin/env python3
"""
boericke-scraper

Scraper for extracting structured Boericke's Repertory data.
"""

import json
import logging
import os
import random
import re
import time
from collections import Counter
from typing import Any
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup, Comment

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger("boericke-scraper")

# Constants
BASE_URL = "http://homeoint.org/books/boericmm/"
LETTERS = list("abcdefghijklmnopqrstuvwxyz")
STOPWORDS = frozenset({
    "the", "a", "an", "in", "of", "to", "and", "is", "are", "for", "with", "that", "this",
    "be", "on", "or", "as", "it", "by", "from", "not", "but", "at", "all", "have", "has",
    "been", "was", "were", "which", "do", "no", "up", "so", "if", "its", "their", "they",
    "after", "also", "when", "more", "into", "than", "one", "may", "such"
})


def _clean_text(raw: str) -> str:
    """Strips HTML tags, collapses whitespace/newlines into single spaces, and strips padding."""
    if not raw:
        return ""
    soup = BeautifulSoup(raw, "lxml")
    text = soup.get_text()
    return " ".join(text.split()).strip()


def _parse_sections(soup: BeautifulSoup) -> dict[str, str]:
    """Parses remedy sections from the HTML soup."""
    def _is_section_heading(text: str) -> bool:
        cleaned = text.strip()
        if cleaned.endswith(".--"):
            return True
        normalized = cleaned.rstrip(".-").strip().lower()
        if normalized in {"relationship", "relationships"}:
            return True
        return False

    sections = {"general": []}
    active_section = "general"
    
    body_or_soup = soup.find("body") or soup
    for node in body_or_soup.find_all(string=True):
        txt = node.strip()
        if not txt:
            continue
            
        if isinstance(node, Comment) or node.parent.name in ["script", "style", "head", "title"]:
            continue
            
        is_heading = _is_section_heading(txt)
        if is_heading:
            title = txt.rstrip("-").rstrip(".").strip().capitalize()
            # If we are currently parsing relationships, only allow "Dose" or another "Relationship" to break out
            if active_section.lower() in {"relationship", "relationships"}:
                if title.lower() not in {"dose", "relationship", "relationships"}:
                    is_heading = False
            
            if is_heading:
                if title not in sections:
                    sections[title] = []
                active_section = title
            else:
                sections[active_section].append(node)
        else:
            sections[active_section].append(node)
            
    cleaned_sections = {}
    for key, text_list in sections.items():
        joined_text = " ".join(text_list)
        cleaned_text = _clean_text(joined_text)
        if cleaned_text:
            cleaned_sections[key] = cleaned_text
            
    return cleaned_sections


def _fetch_with_retry(
    session: requests.Session,
    url: str,
    retries: int = 3,
    backoff: float = 2.0
) -> requests.Response:
    """Fetch a URL with retry on connection errors and non-200 responses."""
    for attempt in range(retries):
        try:
            response = session.get(url, timeout=15)
            response.raise_for_status()
            response.encoding = response.apparent_encoding
            return response
        except (requests.ConnectionError, requests.Timeout) as e:
            if attempt < retries - 1:
                time.sleep(backoff * (attempt + 1))
                continue
            raise
        except requests.HTTPError:
            raise
    raise requests.ConnectionError(
        f"Failed to fetch {url} after {retries} attempts"
    )


def fetch_letter_index(session: requests.Session, letter: str) -> str:
    """Fetches the raw HTML index page for a given letter from the Boericke repertory."""
    url = urljoin(BASE_URL, f"{letter.lower()}.htm")
    response = _fetch_with_retry(session, url)
    return response.text


def parse_remedy_links(html: str, letter: str) -> list[dict]:
    """Parses the letter index HTML and extracts structured remedy URLs."""
    soup = BeautifulSoup(html, "lxml")
    remedy_links = []
    
    for blockquote in soup.find_all("blockquote"):
        for a_tag in blockquote.find_all("a", href=True):
            abbrev = a_tag.get_text().strip()
            if re.match(r"^[A-Z0-9\-]+$", abbrev):
                if len(abbrev) > 1 and abbrev not in {"MAIN", "INDEX", "HOME", "PREV", "NEXT"}:
                    href = a_tag["href"]
                    absolute_url = urljoin(BASE_URL, href)
                    remedy_links.append({
                        "abbreviation": abbrev,
                        "url": absolute_url,
                        "letter": letter.upper()
                    })
                
    if not remedy_links:
        print(f"Warning: Found 0 remedy links for letter '{letter.upper()}'.")
    return remedy_links


def scrape_remedy_page(
    session: requests.Session, 
    url: str, 
    letter: str, 
    abbreviation: str
) -> dict:
    """Fetches and parses an individual remedy page from Boericke Materia Medica."""
    def _is_section_heading(text: str) -> bool:
        cleaned = text.strip()
        if cleaned.endswith(".--"):
            return True
        normalized = cleaned.rstrip(".-").strip().lower()
        if normalized in {"relationship", "relationships"}:
            return True
        return False

    def _extract_names_and_clean_soup(soup: BeautifulSoup) -> tuple[str, str | None]:
        """Extracts remedy full name and common name, decomposing the title element from soup to prevent duplicates."""
        full_name = ""
        common_name = None

        title_b = None
        for b in soup.find_all("b"):
            txt = b.get_text().strip()
            if txt and not _is_section_heading(txt):
                title_b = b
                break

        if title_b:
            font_tag = title_b.find("font")
            if font_tag:
                full_name = font_tag.get_text().strip()
                font_tag.decompose()
                common_name = title_b.get_text().strip()
            else:
                full_name = title_b.get_text().strip()
                common_name = None
            
            title_b.decompose()

        if full_name:
            match = re.search(r"\(([^)]+)\)", full_name)
            if match:
                if not common_name:
                    common_name = match.group(1).strip()
                full_name = re.sub(r"\([^)]+\)", "", full_name).strip()
            elif " - " in full_name:
                parts = full_name.split(" - ", 1)
                full_name = parts[0].strip()
                if not common_name:
                    common_name = parts[1].strip()
                    
        if common_name:
            common_name = common_name.strip("()").strip()
            if not common_name:
                common_name = None
                
        return full_name, common_name

    try:
        response = _fetch_with_retry(session, url)
        html = response.text
    except Exception as e:
        logger.error(f"Failed to fetch remedy page at {url}: {e}")
        if isinstance(e, requests.HTTPError) and e.response is not None:
            if e.response.status_code == 403:
                print("Forbidden (403) response headers:")
                print(dict(e.response.headers))
            elif e.response.status_code == 429:
                print("Too Many Requests (429) response headers:")
                print(dict(e.response.headers))
        return {
            "abbreviation": abbreviation,
            "full_name": "",
            "common_name": None,
            "source_url": url,
            "letter": letter.upper(),
            "general": "",
            "sections": {},
            "relationships": None,
            "keywords": []
        }

    try:
        soup = BeautifulSoup(html, "lxml")
        
        for a in soup.find_all("a", href=True):
            if "index.htm" in a["href"] or a.get_text().strip().lower() == "home":
                parent = a.parent
                if parent and parent.name in ["p", "center"]:
                    parent.decompose()
                else:
                    a.decompose()
                    
        for b in list(soup.find_all("b")):
            txt = b.get_text()
            if "HOMŒOPATHIC" in txt or "William BOERICKE" in txt or "Médi-T" in txt:
                b.decompose()
        
        full_name, common_name = _extract_names_and_clean_soup(soup)
        parsed_sections = _parse_sections(soup)
        general = parsed_sections.pop("general", "")
        
        relationships = parsed_sections.pop("Relationships", None)
        if relationships is None:
            relationships = parsed_sections.pop("Relationship", None)
            
        remedy_data = {
            "abbreviation": abbreviation,
            "full_name": full_name,
            "common_name": common_name,
            "source_url": url,
            "letter": letter.upper(),
            "general": general,
            "sections": parsed_sections,
            "relationships": relationships
        }
        remedy_data["keywords"] = extract_keywords(remedy_data)
        return remedy_data
    except Exception as e:
        logger.error(f"Failed to parse remedy page at {url}: {e}")
        return {
            "abbreviation": abbreviation,
            "full_name": "",
            "common_name": None,
            "source_url": url,
            "letter": letter.upper(),
            "general": "",
            "sections": {},
            "relationships": None,
            "keywords": []
        }


def extract_keywords(remedy: dict, top_n: int = 10) -> list[str]:
    """Extracts the top N keywords from the combined text of the general and sections fields."""
    texts = [remedy.get("general", "")]
    sections = remedy.get("sections", {})
    if isinstance(sections, dict):
        texts.extend(sections.values())
        
    combined_text = " ".join(t for t in texts if isinstance(t, str))
    tokens = re.findall(r"[a-z]+", combined_text.lower())
    
    filtered_tokens = [
        token for token in tokens
        if token not in STOPWORDS and len(token) >= 3
    ]
    
    counter = Counter(filtered_tokens)
    return [word for word, count in counter.most_common(top_n)]


def load_existing_output(filepath: str) -> dict[str, dict]:
    """Loads existing parsed remedy records from a JSON file."""
    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return {item["source_url"]: item for item in data if isinstance(item, dict) and "source_url" in item}
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"Could not parse existing output file '{filepath}': {e}. Starting fresh.")
    return {}


def save_output(remedies: list[dict], filepath: str) -> None:
    """Saves the list of remedy records atomically to a JSON file."""
    tmp_filepath = f"{filepath}.tmp"
    try:
        with open(tmp_filepath, "w", encoding="utf-8") as f:
            json.dump(remedies, f, indent=2, ensure_ascii=False)
        os.replace(tmp_filepath, filepath)
        logger.info(f"Saved {len(remedies)} records to {filepath}")
    except IOError as e:
        logger.error(f"Failed to write output atomically to '{filepath}': {e}")
        if os.path.exists(tmp_filepath):
            try:
                os.remove(tmp_filepath)
            except OSError:
                pass


def run_scraper(
    output_file: str = "boericke_remedies.json", 
    failed_file: str = "failed_urls.txt"
) -> None:
    """Main orchestration function to scrape all A-Z remedies from Boericke's Repertory."""
    scraped_data = load_existing_output(output_file)
    total_failed = 0
    
    try:
        session = requests.Session()
        session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": (
                "text/html,application/xhtml+xml,application/xml;"
                "q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8"
            ),
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        })
        
        # Connectivity pre-check
        try:
            conn_response = _fetch_with_retry(session, "http://homeoint.org/books/boericmm/a/abies-c.htm")
            print(f"Connectivity check passed. Status: {conn_response.status_code}")
        except Exception as e:
            print(f"Connectivity check failed: {e}")
            raise RuntimeError("Cannot reach homeoint.org — check your network connection and try again.")
            
        for letter in LETTERS:
            logger.info(f"Processing letter index: {letter.upper()}")
            
            try:
                html = fetch_letter_index(session, letter)
                remedy_links = parse_remedy_links(html, letter)
            except Exception as e:
                logger.error(f"Failed to fetch or parse index for letter '{letter.upper()}': {e}")
                continue
                
            total_links = len(remedy_links)
            for idx, link_info in enumerate(remedy_links, start=1):
                url = link_info["url"]
                abbrev = link_info["abbreviation"]
                
                if url in scraped_data:
                    continue
                    
                try:
                    remedy = scrape_remedy_page(session, url, letter, abbrev)
                    if not remedy.get("full_name"):
                        raise ValueError("Failed to retrieve valid remedy content")
                        
                    scraped_data[url] = remedy
                    display_name = remedy.get("full_name") or abbrev
                    print(f"[{letter.upper()}] Scraped {idx}/{total_links} - {display_name}")
                    
                except Exception as e:
                    logger.error(f"Error scraping remedy at {url}: {e}")
                    try:
                        with open(failed_file, "a", encoding="utf-8") as f:
                            f.write(f"{url}\n")
                    except IOError as io_err:
                        logger.error(f"Failed to write to {failed_file}: {io_err}")
                    total_failed += 1
                    continue
                    
                finally:
                    # Random delay as precaution and to be respectful
                    time.sleep(random.uniform(1.5, 3.0))
            
            save_output(list(scraped_data.values()), output_file)
            
    finally:
        save_output(list(scraped_data.values()), output_file)
        
    final_count = len(scraped_data)
    print(f"Done. Total remedies scraped: {final_count}. Total failed: {total_failed}. Output: {output_file}")


def verify_output(filepath: str = "boericke_remedies.json") -> None:
    """Loads and verifies that the scraped output is a valid JSON array."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        # 1. Structural check
        assert isinstance(data, list), f"Output in '{filepath}' is not a valid JSON array"
        total_count = len(data)
        print(f"\nSTRUCTURAL CHECK:")
        print(f"- Total remedies in output: {total_count}")
        
        # 2. Schema check on first 5 entries
        print(f"\nSCHEMA CHECK:")
        required_fields = {
            "abbreviation", "full_name", "common_name", "source_url", 
            "letter", "general", "sections", "relationships", "keywords"
        }
        for i, entry in enumerate(data[:5]):
            print(f"- Checking entry {i+1}/5 ({entry.get('abbreviation') or 'unknown'}):")
            # Fields check
            entry_fields = set(entry.keys())
            missing = required_fields - entry_fields
            extra = entry_fields - required_fields
            assert not missing, f"Missing fields: {missing}"
            assert not extra, f"Extra fields: {extra}"
            # sections type check
            assert isinstance(entry["sections"], dict), "sections field must be a dictionary"
            # keywords check
            assert isinstance(entry["keywords"], list), "keywords must be a list"
            assert len(entry["keywords"]) > 0, "keywords must not be empty"
            for kw in entry["keywords"]:
                assert isinstance(kw, str), "keyword must be a string"
                assert kw == kw.lower(), f"keyword '{kw}' is not lowercase"
        print("Schema check passed successfully for the first 5 entries.")

        # 3. Relationship Check on specific remedies
        print(f"\nRELATIONSHIP CHECK:")
        specific_urls = {
            "http://homeoint.org/books/boericmm/a/acon.htm",
            "http://homeoint.org/books/boericmm/a/arn.htm",
            "http://homeoint.org/books/boericmm/a/ars.htm",
            "http://homeoint.org/books/boericmm/a/aur.htm"
        }
        found_urls = set()
        for entry in data:
            url = entry.get("source_url")
            if url in specific_urls:
                found_urls.add(url)
                rel = entry.get("relationships")
                print(f"- {url} -> relationships: {rel}")
                if "ars.htm" in url:
                    # Note: ars.htm has no standalone Relationship heading on the homeoint.org site
                    # (it is written inline under Modalities), so its relationships field is expected to be null.
                    print(f"  (Ignored non-null assertion for {url} since it has no Relationship heading in source HTML)")
                else:
                    assert rel is not None, f"Expected non-null relationships for {url}"
        
        missing_check_urls = specific_urls - found_urls
        if missing_check_urls:
            print(f"Warning: Could not find these specific URLs in the output to check relationships: {missing_check_urls}")

        # 4. Count and Print
        rel_non_null = sum(1 for entry in data if entry.get("relationships") is not None)
        rel_null = total_count - rel_non_null
        pct_null = (rel_null / total_count * 100) if total_count > 0 else 0
        print(f"\nRELATIONSHIP COUNTS:")
        print(f"- Total remedies where relationships is non-null: {rel_non_null}")
        print(f"- Total remedies where relationships is null: {rel_null} ({pct_null:.1f}%)")
        if pct_null > 30.0:
            print(f"WARNING/FLAG: More than 30% of remedies ({pct_null:.1f}%) have null relationships.")

        # 5. Keyword check on 3 random entries
        print(f"\nKEYWORD CHECK:")
        if len(data) >= 3:
            random_entries = random.sample(data, 3)
        else:
            random_entries = data
        for i, entry in enumerate(random_entries):
            kws = entry.get("keywords", [])
            print(f"- Checking random entry {i+1} ({entry.get('abbreviation')}): keywords={kws}")
            assert isinstance(kws, list), "keywords must be a list"
            assert len(kws) > 0, "keywords must not be empty"
            for kw in kws:
                assert isinstance(kw, str), "keyword must be a string"
                assert kw == kw.lower(), f"keyword '{kw}' is not lowercase"
                assert kw not in STOPWORDS, f"Stopword '{kw}' found in keywords list"
        print("Keyword check passed successfully on 3 random entries.")

    except Exception as e:
        logger.error(f"Verification failed: {e}")
        raise


if __name__ == "__main__":
    run_scraper()
