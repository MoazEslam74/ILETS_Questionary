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


# ----------------------------------------------------------------------
# 2. Pull the answer key: {question_number(int): answer_text(str)}
# ----------------------------------------------------------------------
def extract_answer_key(soup: BeautifulSoup) -> dict:
    answer_div = soup.find("div", id=re.compile(r"^bg-showmore-hidden-"))
    if not answer_div:
        return {}
 
    # br tags act as line separators; convert them to \n before extracting text
    for br in answer_div.find_all("br"):
        br.replace_with("\n")
 
    raw_text = answer_div.get_text()
    answers = {}
    # matches lines like "12. C" or "29. timber and stone"
    for m in re.finditer(r"(?m)^\s*(\d{1,3})\.\s*(.+?)\s*$", raw_text):
        num = int(m.group(1))
        ans = m.group(2).strip()
        answers[num] = ans
    return answers
 
 
# ----------------------------------------------------------------------
# 3. Classify a question-group instruction paragraph into a type label
# ----------------------------------------------------------------------
TYPE_RULES = [
    (r"complete the summary", "Summary Completion"),
    (r"complete the table", "Table Completion"),
    (r"complete the notes", "Note Completion"),
    (r"look at the following notes", "Matching Features"),
    (r"match each cause", "Matching (Cause & Effect)"),
    (r"agree with the (information|views|claims)", "Yes/No/Not Given"),
    (r"true.*false.*not given|does the (following )?statement", "True/False/Not Given"),
    (r"choose the appropriate letters", "Multiple Choice (Single Answer)"),
    (r"which\s+\w+\s+of the following", "Multiple Choice (Select Multiple)"),
    (r"choose the correct heading", "Matching Headings"),
    (r"no more than \w+ words?", "Short Answer / Completion"),
]


def classify_type(instruction_text: str) -> str:
    t = instruction_text.lower()
    for pattern, label in TYPE_RULES:
        if re.search(pattern, t):
            return label
    return "Unclassified"


# ----------------------------------------------------------------------
# 4. Walk entry-content, split into passages, then into question-groups
# ----------------------------------------------------------------------
QRANGE_RE = re.compile(r"Questions?\s+(\d{1,3})\s*(?:-|–|to)\s*(\d{1,3})", re.I)
 
 
def get_passage_title(node):
    """A passage title is a centered/capitalised <p><strong>...</strong></p>
    with an id starting 'mcetoc'."""
    strong = node.find("strong")
    return strong.get_text(strip=True) if strong else node.get_text(strip=True)
 
 
def extract_statements_by_number(text: str, numbers):
    """
    For blocks where each question is literally 'N. text' or 'N text'
    separated by <br/> (already converted to \n), grab the statement
    text for each number in `numbers`.
    """
    out = {}
    lines = text.split("\n")
    for line in lines:
        line = line.strip()
        m = re.match(r"^(\d{1,3})[\.\)]?\s+(.*\S)\s*$", line)
        if m:
            n = int(m.group(1))
            if n in numbers:
                out[n] = m.group(2).strip()
    return out
 