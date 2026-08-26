"""
IELTS Reading Test scraper for practicepteonline.com style pages.
 
Extracts rows shaped like:
    exam_category, passage, question_type, question_number, question, answer
 
Works off two things in the page:
  1. <div class="entry-content"> ... </div>          -> all passages + questions
  2. <div id="bg-showmore-hidden-...">1. x<br/>2. y...</div>  -> the answer key
 
Usage:
    python ielts_scraper.py path/to/page.html output.csv
    python ielts_scraper.py https://practicepteonline.com/ielts-reading-test-62/ output.csv
"""

import re
import sys
import csv
import json
from bs4 import BeautifulSoup, NavigableString

# ----------------------------------------------------------------------
# 1. Load HTML (local file or URL)
# ----------------------------------------------------------------------
def load_html(source: str) -> str:
    if source.startswith("http://") or source.startswith("https://"):
        import requests
        headers = {"User-Agent": "Mozilla/5.0 (compatible; IELTSScraper/1.0)"}
        resp = requests.get(source, headers=headers, timeout=30)
        resp.raise_for_status()
        return resp.text
    with open(source, "r", encoding="utf-8", errors="ignore") as f:
        return f.read()
 