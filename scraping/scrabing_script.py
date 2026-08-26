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


