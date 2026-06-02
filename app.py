from flask import Flask, request, render_template_string
import json
import glob
import csv
import re
import os
import sys

# --- BULLETPROOF PATH FINDING ---
# This forces the app to look for the 'data' folder in the exact same directory
# as the executable, no matter how the user double-clicks or opens it.
if getattr(sys, 'frozen', False):
    base_dir = os.path.dirname(sys.executable)
else:
    base_dir = os.path.dirname(os.path.abspath(__file__))

os.chdir(base_dir)
# --------------------------------

app = Flask(__name__)

def format_legal_text(raw_text):
    text = raw_text.replace('&nbsp;', ' ').replace('_', ',').replace('\n', '<br>').replace('\r', '')
    text = re.sub(r'\b(Mr|Mrs|Ms|Dr|Hon)\.?\s*<br>\s*', r'\1 ', text, flags=re.IGNORECASE)
    text = re.sub(r'([a-z])\.([A-Z])', r'\1. \2', text)
    text = re.sub(r'\,([A-Z][a-z])', r', \1', text)
    text = text.replace('JUDGMENT(', 'JUDGMENT (')
    text = text.replace(',and ', ', and ')
    text = re.sub(r'(?<!\bno)(?<!\bart)(?<!\bvol)(?<!\b[vV])([a-zA-Z\.\)\]\:\;\'\"”“’‘])\s*(\d{1,3}\.\s+[A-Z\“\"‘”“\d])', r'\1<br><br>\2', text)
    text = re.sub(r'(?<!\bMr)(?<!\bMrs)(?<!\bMs)(?<!\bDr)([\.\)\]\:\;\'\"”“’‘])\s*(I{1,3}|IV|V|VI{1,3}|IX|X)\.\s+([A-Z])', r'\1<br><br>\2. \3', text)
    text = re.sub(r'([A-Z]{3,})([A-Z])\.\s+([A-Z])', r'\1<br><br>\2. \3', text)
    text = re.sub(r'([a-zA-Z\.\)\]\:\;\'\"”“’‘])\s*(\([a-z]\)\s+[A-Z\“\"”“’‘])', r'\1<br><br>\2', text)
    text = re.sub(r'(CASE OF [^\(]+?)(?=\s*\(|\s+JUDGMENT|\s+DECISION|\s+FINAL|<br>)', r'<h1 class="case-title">\1</h1>', text, count=1, flags=re.IGNORECASE)
    text = re.sub(r'\b(PROCEDURE|THE FACTS|THE LAW|COMPLAINTS)\b', r'<br><br><h2 class="legal-header">\1</h2><br>', text)
    text = re.sub(r'(FOR THESE REASONS[\sA-Z\,]+?)(?=<br>|\d{1,3}\.)', lambda m: f'<br><br><h2 class="legal-header">{m.group(1).replace("<br>", "").strip()}</h2><br>', text)
    text = re.sub(r'(?:^|<br>|>)\s*(I{1,3}|IV|V|VI{1,3}|IX|X)\.\s+([A-Z\s\-\,]{5,})(?=[A-Z][a-z]|<br>|\d{1,3}\.)', r'<h3 class="legal-subheader">\1. \2</h3>', text)
    text = re.sub(r'(?:^|<br>|>)\s*([A-Z])\.\s+([A-Z][^\<]{2,120}?)(?=<br>)', r'<br><br><h4 class="legal-section">\1. \2</h4>', text)
    text = re.sub(r'(?:^|<br>|>)\s*(\d{1,3})\.\s+([A-Z\“\"”“‘\d])', r'<br><br><span class="para-number">\1.</span> \2', text)
    text = re.sub(r'(?:^|<br>|>)\s*(\([a-z]\))\s+([A-Z\“\"”“‘\d])', r'<br><br><span class="para-number">\1</span> \2', text)
    text = re.sub(r'(<br>\s*){3,}', '<br><br>', text)
    return f'<div class="physical-document">{text}</div>'

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Offline ECHR Viewer</title>
    <style>
        body { font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; max-width: 900px; margin: 40px auto; padding: 20px; background: #cbd0d4; }
        .search-container { background: #e0e4e8; padding: 30px; border-radius: 8px; border: 2px solid #aeb5bc; box-shadow: inset 2px 2px 3px rgba(255,255,255,0.9), inset -2px -2px 3px rgba(0,0,0,0.1), 5px 10px 20px rgba(0,0,0,0.25); }
        input { width: 72%; padding: 16px; font-size: 16px; background: #f4f6f2; border: 1px solid #889098; border-radius: 3px; box-shadow: inset 3px 3px 6px rgba(0,0,0,0.3), inset -1px -1px 2px rgba(255,255,255,0.8); color: #222; }
        input:focus { outline: none; background: #ffffff; }
        button { width: 22%; padding: 16px; font-size: 16px; cursor: pointer; background: linear-gradient(to bottom, #f2f5f7 0%, #c4ccd4 100%); color: #333; border: 1px solid #7c858e; border-radius: 4px; font-weight: bold; text-shadow: 0 1px 0 rgba(255,255,255,0.8); box-shadow: inset 1px 1px 1px rgba(255,255,255,0.9), 0 4px 6px rgba(0,0,0,0.3); transition: all 0.05s ease; }
        button:active { background: #c4ccd4; box-shadow: inset 2px 3px 5px rgba(0,0,0,0.4); transform: translateY(2px); }
        .result { background: #fcfcfb; border: 1px solid #b3b1a8; border-left: 12px solid #4a5d6e; padding: 25px; margin-top: 25px; border-radius: 2px; box-shadow: 3px 5px 10px rgba(0,0,0,0.15); position: relative; }
        .result::before { content: ''; position: absolute; left: 0; top: 0; bottom: 0; width: 4px; background: linear-gradient(to right, rgba(0,0,0,0.2), transparent); }
        .meta { color: #555; font-size: 0.9em; margin-bottom: 15px; padding-bottom: 15px; border-bottom: 1px dashed #c2c0b8; }
        h4 { margin-top: 0; color: #222; font-size: 1.3em;}
        summary { cursor: pointer; color: #3b5063; font-weight: bold; margin-top: 10px; padding: 8px; background: #eef0f2; border: 1px solid #d1d5da; border-radius: 3px; display: inline-block; box-shadow: 1px 2px 3px rgba(0,0,0,0.05); }
        summary:active { box-shadow: inset 1px 1px 3px rgba(0,0,0,0.1); }
        .document-wrapper { margin-top: 15px; max-height: 600px; overflow-y: auto; box-shadow: inset 0 0 15px rgba(0,0,0,0.03); border: 1px solid #dcdad1; }
        .physical-document { background-color: #fdfcf7; color: #2b2b2b; font-family: 'Times New Roman', Times, serif; padding: 40px 50px 40px 70px; position: relative; line-height: 1.6; font-size: 16px; }
        .physical-document::before { content: ''; position: absolute; top: 0; bottom: 0; left: 45px; width: 1px; background: rgba(180, 40, 40, 0.4); box-shadow: 2px 0 0 rgba(180, 40, 40, 0.1); }
        .case-title { text-align: center; font-size: 1.4em; text-transform: uppercase; margin-bottom: 30px; color: #111; }
        .legal-header { text-align: center; font-weight: bold; letter-spacing: 2px; border-bottom: 1px solid #888; margin: 40px 0 20px 0; padding-bottom: 5px; color: #111; font-size: 1.2em; }
        .legal-subheader { font-style: italic; margin-top: 30px; font-size: 1.1em; color: #222; }
        .legal-section { font-weight: bold; margin-top: 20px; text-decoration: underline; font-size: 1.05em; color: #222; }
        .para-number { font-weight: bold; font-size: 1.1em; margin-right: 5px; color: #111; }
    </style>
</head>
<body>
    <div class="search-container">
        <h2 style="margin-top: 0; color: #444; text-shadow: 0 1px 0 #fff; letter-spacing: 1px;">ECHR TERMINAL</h2>
        <form method="GET">
            <input type="text" name="q" placeholder="Enter keywords, ID, or case law..." value="{{ query }}">
            <button type="submit">SEARCH</button>
        </form>
    </div>

    {% if query %}
        <h3 style="color: #444; text-shadow: 0 1px 0 #fff; margin-top: 30px;">Results for "{{ query }}"</h3>
        {% for res in results %}
            <div class="result">
                <h4>{{ res.title }}</h4>
                <div class="meta">
                    <strong>Type:</strong> {{ res.doctype }} &nbsp;|&nbsp;
                    <strong>App No:</strong> {{ res.appno }} &nbsp;|&nbsp;
                    <strong>Date:</strong> {{ res.date }} &nbsp;|&nbsp;
                    <strong>ID:</strong> {{ res.id }}
                </div>
                <details>
                    <summary>Extract Physical Document</summary>
                    <div class="document-wrapper">
                        {{ res.text | safe }}
                    </div>
                </details>
            </div>
        {% else %}
            <p>No results found.</p>
        {% endfor %}
    {% endif %}
</body>
</html>
"""

print("\n--- BOOTING UP DATABASE ---")
cases = {}
metadata = {}

print(f"Directory: {base_dir}")
print("1. Looking for JSON files...")
json_files = glob.glob('data/*.json')
for j_file in json_files:
    try:
        with open(j_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            if isinstance(data, list):
                for item in data:
                    if 'item_id' in item:
                        cases[item['item_id']] = item
    except Exception:
        pass

print(f"\n2. Total Cases loaded into RAM: {len(cases)}")

print("\n3. Looking for CSV metadata files...")
csv_files = glob.glob('data/*.csv')
for c_file in csv_files:
    try:
        with open(c_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if 'itemid' in row:
                    metadata[row['itemid']] = row
    except Exception:
        pass

print(f"4. Total Metadata records loaded: {len(metadata)}\n")
print("--- SERVER READY ---")

@app.route("/")
def index():
    query = request.args.get("q", "").lower()
    results = []

    if query:
        for doc_id, content in cases.items():
            raw_text = content.get('full_text', '')

            if query in raw_text.lower() or query in str(doc_id).lower():
                meta = metadata.get(doc_id, {})
                formatted_text = format_legal_text(raw_text)

                results.append({
                    'id': doc_id,
                    'title': meta.get('docname', 'Unknown Case'),
                    'doctype': meta.get('doctype', 'Unknown Type'),
                    'appno': meta.get('appno', 'N/A'),
                    'date': meta.get('judgementdate', 'N/A').split(' ')[0],
                    'text': formatted_text
                })
                if len(results) >= 20:
                    break

    return render_template_string(HTML_TEMPLATE, query=request.args.get("q", ""), results=results)

if __name__ == "__main__":
    import threading
    import webbrowser

    # Switch to 5050 to avoid macOS AirPlay conflict
    PORT = 5050

    def open_browser():
        webbrowser.open_new(f'http://127.0.0.1:{PORT}/')

    print("--------------------------------------------------")
    print("STARTING ECHR OFFLINE ENGINE...")
    print("Please wait while the database loads into memory.")
    print("--------------------------------------------------")

    threading.Timer(2.0, open_browser).start()
    app.run(port=PORT)
