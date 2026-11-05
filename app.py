import math
import time
import requests
from collections import defaultdict
from flask import Flask, render_template, jsonify

app = Flask(__name__)

# ── Inject math module into Jinja templates ──────────
# (This is the fix for the "'math' is undefined" error)
app.jinja_env.globals.update(math=math)

# ── Config ─────────────────────────────────────────────
EVENT_ID      = "300b29f0-1e58-4983-ab64-6cdea3e13189"
OCCURRENCE_ID = "a250895f-093f-4acf-95f2-7bec4ce6160c"
LAYOUT_VER    = "1bf67a4cca622034"

STATUS_URL = f"https://talantasportscity.com/seatmap/{EVENT_ID}/status"
LAYOUT_URL = f"https://talantasportscity.com/seatmap/{EVENT_ID}/layout/{LAYOUT_VER}"

HEADERS = {"User-Agent": "Mozilla/5.0 (ticket-monitor)"}
TIMEOUT = 15

_LAYOUT_CACHE = {"data": None, "loaded_at": 0}
LAYOUT_TTL_SECONDS = 300


def get_section_meta():
    now = time.time()
    if (_LAYOUT_CACHE["data"] is not None
            and now - _LAYOUT_CACHE["loaded_at"] < LAYOUT_TTL_SECONDS):
        return _LAYOUT_CACHE["data"]

    r = requests.get(LAYOUT_URL, headers=HEADERS, timeout=TIMEOUT)
    r.raise_for_status()
    data = r.json()

    meta = {
        s["id"]: {
            "code":     s.get("code") or "",
            "name":     s.get("name") or "",
            "sign":     s.get("sign_code") or "",
            "tier":     s.get("tier") or "",
            "category": s.get("category") or "",
            "seat_count": s.get("seat_count") or 0,
        }
        for s in data.get("sections", [])
    }

    _LAYOUT_CACHE["data"] = meta
    _LAYOUT_CACHE["loaded_at"] = now
    return meta


def fetch_status():
    r = requests.get(STATUS_URL, params={"o": OCCURRENCE_ID},
                     headers=HEADERS, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


def sort_key(code: str):
    code = (code or "").strip()
    try:
        return (0, int(code))
    except ValueError:
        return (1, code)


def enrich_sections(sections, meta_map):
    out = []
    for s in sections:
        meta = meta_map.get(s["id"], {})
        tier     = meta.get("tier", "")
        category = meta.get("category", "")
        code     = meta.get("code", "")
        name     = meta.get("name", "")
        sign     = meta.get("sign") or name or code or s["id"][:8]

        suffix = f" ({category.upper()})" if category and category != "general" else ""

        out.append({
            **s,
            "code":       code,
            "name":       name,
            "tier":       tier,
            "category":   category,
            "sign":       sign,
            "seat_count": meta.get("seat_count", 0),
            "label":      f"{sign}{suffix}",
        })
    return out


def summarize(sections):
    total_sellable = 0
    total_available = 0
    on_sale_count  = 0
    by_tier        = defaultdict(lambda: {"sections": 0, "available": 0, "sellable": 0})
    by_category    = defaultdict(lambda: {"sections": 0, "available": 0, "sellable": 0})

    for s in sections:
        avail    = s.get("available") or 0
        sellable = s.get("total_sellable") or 0
        total_available += avail
        total_sellable  += sellable
        if s.get("on_sale"):
            on_sale_count += 1

        tier = s.get("tier") or "untyped"
        cat  = s.get("category") or "untyped"
        for bucket in (by_tier[tier], by_category[cat]):
            bucket["sections"]  += 1
            bucket["available"] += avail
            bucket["sellable"]  += sellable

    return {
        "total_sellable":   total_sellable,
        "total_available":  total_available,
        "remaining":        total_available,
        "sold":             total_sellable - total_available,
        "on_sale_sections": on_sale_count,
        "total_sections":   len(sections),
        "by_tier":          dict(by_tier),
        "by_category":      dict(by_category),
    }


@app.route("/")
def index():
    try:
        meta_map = get_section_meta()
        data     = fetch_status()
    except Exception as e:
        return render_template("index.html", error=str(e),
                               summary=None, sections=[], tiers=[], categories=[])

    sections = enrich_sections(data.get("sections", []), meta_map)
    summary  = summarize(sections)

    tier_order = {"lower": 0, "middle": 1, "upper": 2}
    sections.sort(key=lambda s: (tier_order.get(s["tier"], 99), sort_key(s["code"])))

    tiers      = sorted(summary["by_tier"].items(),
                        key=lambda kv: tier_order.get(kv[0], 99))
    categories = sorted(summary["by_category"].items(),
                        key=lambda kv: (-kv[1]["sellable"], kv[0]))

    return render_template(
        "index.html",
        error=None,
        summary=summary,
        sections=sections,
        tiers=tiers,
        categories=categories,
    )


@app.route("/api")
def api():
    try:
        meta_map = get_section_meta()
        data     = fetch_status()
    except Exception as e:
        return jsonify({"error": str(e)}), 502
    sections = enrich_sections(data.get("sections", []), meta_map)
    return jsonify({
        "summary":  summarize(sections),
        "sections": sections,
    })


if __name__ == "__main__":
    app.run(debug=True)