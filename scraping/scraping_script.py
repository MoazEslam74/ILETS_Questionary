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

def parse_ielts_page(html: str, exam_category_hint: str = None):
    soup = BeautifulSoup(html, "lxml")
 
    title_tag = soup.find("h1", class_=re.compile("page-title"))
    exam_category = exam_category_hint or (
        title_tag.get_text(strip=True) if title_tag else "Unknown Test"
    )
 
    answer_key = extract_answer_key(soup)
 
    entry = soup.find("div", class_="entry-content")
    if not entry:
        return []
 
    rows = []
 
    # Collect ordered list of relevant nodes: passage-title markers,
    # "Questions X-Y" markers, and everything else as body text.
    children = [c for c in entry.find_all(["p", "figure"], recursive=False)]
 
    current_passage = None
    current_group = None  # dict: start,end,type_text,body_lines
    groups = []
 
    for node in children:
        node_text = node.get_text(" ", strip=True)
 
        # --- Passage title marker ---
        p_id = node.get("id", "")
        if p_id.startswith("mcetoc"):
            current_passage = get_passage_title(node)
            continue
 
        if not node_text:
            continue
 
        # --- New question-range header ---
        range_match = QRANGE_RE.search(node_text)
        if range_match and node.find("strong"):
            if current_group:
                groups.append(current_group)
            start, end = int(range_match.group(1)), int(range_match.group(2))
            current_group = {
                "passage": current_passage,
                "start": start,
                "end": end,
                "instruction": node_text,
                "body_nodes": [],
            }
            continue
 
        if current_group is not None:
            current_group["body_nodes"].append(node)
 
    if current_group:
        groups.append(current_group)
 
    # --- For each group, build per-question rows ---
    for g in groups:
        # Classification should look at the header line PLUS the next
        # couple of body paragraphs, since instructions ("Do the
        # following statements agree...", "Complete the table...")
        # often live in a separate <p> right after "Questions X-Y".
        classify_source = g["instruction"] + " " + " ".join(
            n.get_text(" ", strip=True) for n in g["body_nodes"][:2]
        )
        qtype = classify_type(classify_source)
        numbers = list(range(g["start"], g["end"] + 1))
 
        # Convert body nodes to a newline-joined text (br -> \n) for
        # line-based statement extraction (works for MCQ/matching/Y-N-NG).
        joined_html_text_parts = []
        for n in g["body_nodes"]:
            n_copy = BeautifulSoup(str(n), "lxml")
            for br in n_copy.find_all("br"):
                br.replace_with("\n")
            joined_html_text_parts.append(n_copy.get_text())
        joined_text = "\n".join(joined_html_text_parts)
 
        per_question_text = extract_statements_by_number(joined_text, set(numbers))
 
        # Fallback question text: use the group's instruction sentence,
        # since fill-in-the-blank (summary/table) questions don't have
        # a clean standalone "question" string.
        fallback_text = g["instruction"]
 
        for num in numbers:
            question_text = per_question_text.get(num, fallback_text)
            rows.append({
                "exam_category": exam_category,
                "passage": g["passage"] or "",
                "question_type": qtype,
                "question_number": num,
                "question": question_text,
                "answer": answer_key.get(num, ""),
            })
 
    return rows
 
 
# ----------------------------------------------------------------------
# 5. CLI
# ----------------------------------------------------------------------
if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python ielts_scraper.py <html_file_or_url> <output.csv>")
        sys.exit(1)
 
    src, out_path = sys.argv[1], sys.argv[2]
    html = load_html(src)
    rows = parse_ielts_page(html)
 
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["exam_category", "passage", "question_type",
                        "question_number", "question", "answer"],
        )
        writer.writeheader()
        writer.writerows(rows)
 
    print(f"Wrote {len(rows)} rows to {out_path}")