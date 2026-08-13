"""Regenerates assets/search-index.js from the content of docs/**/index.html.

Run manually after editing addon pages:
    python docs/assets/build_search_index.py
"""
import json
import re
from pathlib import Path

DOCS = Path(__file__).resolve().parent.parent

H2_RE = re.compile(r"<h2[^>]*>(.*?)</h2>(.*?)(?=<h2|</article>)", re.S)
TAG_RE = re.compile(r"<[^>]+>")
WS_RE = re.compile(r"\s+")


def clean(html):
    text = TAG_RE.sub(" ", html)
    text = text.replace("&rarr;", "->").replace("&mdash;", "-").replace("&hellip;", "...")
    text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    return WS_RE.sub(" ", text).strip()


def parse_page(path, url):
    html = path.read_text(encoding="utf-8")
    title_m = re.search(r"<title>(.*?)</title>", html)
    title = clean(title_m.group(1)).split(" — ")[0] if title_m else url
    desc_m = re.search(r'<meta name="description" content="(.*?)">', html)
    desc = clean(desc_m.group(1)) if desc_m else ""

    sections = []
    for m in H2_RE.finditer(html):
        heading = clean(m.group(1))
        body = clean(m.group(2))
        snippet = (body[:140] + "...") if len(body) > 140 else body
        anchor = re.sub(r"[^a-z0-9]+", "-", heading.lower()).strip("-")
        sections.append({"title": heading, "url": url + "#" + anchor, "snippet": snippet})

    return {"title": title, "url": url, "desc": desc, "sections": sections}


def main():
    pages = []
    home = DOCS / "index.html"
    pages.append(parse_page(home, "index.html"))

    addons_dir = DOCS / "addons"
    for sub in sorted(addons_dir.iterdir()):
        idx = sub / "index.html"
        if idx.exists():
            pages.append(parse_page(idx, "addons/" + sub.name + "/index.html"))

    out = DOCS / "assets" / "search-index.js"
    out.write_text("window.BP_SEARCH_INDEX = " + json.dumps(pages, indent=2) + ";\n", encoding="utf-8")
    print("Wrote", out, "with", len(pages), "pages")


if __name__ == "__main__":
    main()
