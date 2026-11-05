import requests
from collections import defaultdict
from flask import Flask, render_template, jsonify

app = Flask(__name__)

EVENT_ID = "300b29f0-1e58-4983-ab64-6cdea3e13189"
OCCURRENCE_ID = "a250895f-093f-4acf-95f2-7bec4ce6160c"
STATUS_URL = f"https://talantasportscity.com/seatmap/{EVENT_ID}/status"
HEADERS = {"User-Agent": "Mozilla/5.0 (ticket-monitor)"}
TIMEOUT = 10

def fetch_status():
    r = requests.get(STATUS_URL, params={"o": OCCURRENCE_ID}, headers=HEADERS, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()

def summarize(sections):
    total_sellable = 0
    total_available = 0
    on_sale_count = 0
    by_type = defaultdict(lambda: {"sections": 0, "available": 0, "sellable": 0})

    for s in sections:
        avail = s.get("available") or 0
        sellable = s.get("total_sellable") or 0
        total_available += avail
        total_sellable += sellable
        if s.get("on_sale"):
            on_sale_count += 1

        key = s.get("ticket_type_id") or "untyped"
        by_type[key]["sections"] += 1
        by_type[key]["available"] += avail
        by_type[key]["sellable"] += sellable

    return {
        "total_sellable": total_sellable,
        "total_available": total_available,
        "remaining": total_available,
        "sold": total_sellable - total_available,
        "on_sale_sections": on_sale_count,
        "total_sections": len(sections),
        "by_type": dict(by_type),
    }

@app.route("/")
def index():
    try:
        data = fetch_status()
    except Exception as e:
        return render_template("index.html", error=str(e), summary=None, sections=[])

    sections = data.get("sections", [])
    summary = summarize(sections)
    
    # Sort sections alphabetically by their ID so the grid groups similar sections together (e.g., 101, 102, Gold)
    sections.sort(key=lambda x: x["id"])
    
    return render_template("index.html", error=None, summary=summary, sections=sections)

@app.route("/api")
def api():
    try:
        data = fetch_status()
    except Exception as e:
        return jsonify({"error": str(e)}), 502
    sections = data.get("sections", [])
    return jsonify({"summary": summarize(sections), "sections": sections})

if __name__ == "__main__":
    app.run(debug=True)