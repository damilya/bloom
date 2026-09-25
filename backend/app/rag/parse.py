"""Document parsing: scientific PDFs (PyMuPDF, layout-aware) and JATS XML / HTML (BeautifulSoup).

Output: list of Section(title, page, text). Section awareness matters for citations
("Results, p. 7" is far more useful than an arbitrary character window) and for chunking.

PDF heuristics
  • body font size = most frequent span size; spans noticeably smaller (running heads, footers,
    page numbers, affiliations, table cells) are dropped
  • a heading = short line whose spans are all bold/semibold and not smaller than body text
  • lines repeated on ≥30 % of pages (journal banners) are removed
  • hyphenated line breaks are re-joined
  • back matter (References, Funding, Conflicts, Acknowledgements …) is skipped
"""
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import pymupdf
from bs4 import BeautifulSoup

BACK_MATTER = re.compile(
    r"^(\d+(\.\d+)*\s*)?(references|bibliography|acknowledg|conflicts? of interest|competing interests?|funding|"
    r"author contributions?|declarations?|data availability|ethics|compliance with ethical|supplementary|"
    r"publisher.?s note|open access|abbreviations|footnotes)",
    re.I,
)
STOP = re.compile(r"^(\d+(\.\d+)*\s*)?(references|bibliography)\b", re.I)
CLEAN = str.maketrans({"\x07": "", " ": " ", " ": " ", "\xa0": " ", " ": " ", "ﬁ": "fi", "ﬂ": "fl"})


@dataclass
class Section:
    title: str
    page: int
    text: str


def _is_bold(span: dict) -> bool:
    f = span["font"].lower()
    return bool(span["flags"] & 16) or any(w in f for w in ("bold", "semibold", "black", "heavy"))


def _span_text(span: dict, prev_x1: float | None) -> tuple[str, float | None]:
    """Rebuild span text from glyph boxes, inserting spaces at visual gaps.

    Many journal PDFs position glyphs individually and omit space characters, which makes
    plain extraction glue words together ("isrecommendedtoimprove") and wrecks embeddings.
    """
    out = []
    gap = 0.18 * span["size"]
    for ch in span.get("chars", []):
        c = ch["c"]
        x0, x1 = ch["bbox"][0], ch["bbox"][2]
        if prev_x1 is not None and c != " " and x0 - prev_x1 > gap and out[-1:] != [" "]:
            out.append(" ")
        out.append(c)
        prev_x1 = x1
    return "".join(out), prev_x1


def _line_text(line: dict) -> str:
    prev = None
    parts = []
    for sp in line["spans"]:
        t, prev = _span_text(sp, prev)
        parts.append(t)
    return "".join(parts)


def _norm_line(s: str) -> str:
    return re.sub(r"\d+", "#", s.strip().lower())


def parse_pdf(path: Path) -> list[Section]:
    doc = pymupdf.open(path)
    pages = [p.get_text("rawdict") for p in doc]
    sizes: Counter = Counter()
    line_pages: Counter = Counter()
    for pg in pages:
        seen = set()
        for b in pg["blocks"]:
            for ln in b.get("lines", []):
                txt = _line_text(ln).translate(CLEAN)
                for s in ln["spans"]:
                    sizes[round(s["size"], 1)] += len(s.get("chars", []))
                seen.add(_norm_line(txt))
        line_pages.update(seen)
    body = sizes.most_common(1)[0][0] if sizes else 10.0
    repeated = {ln for ln, n in line_pages.items() if len(pages) > 3 and n >= 0.3 * len(pages) and len(ln) > 3}

    sections: list[Section] = [Section("Abstract / Introduction", 1, "")]
    skipping = False
    for pno, pg in enumerate(pages, start=1):
        for b in pg["blocks"]:
            for ln in b.get("lines", []):
                spans = [s for s in ln["spans"] if "".join(c["c"] for c in s.get("chars", [])).strip()]
                if not spans:
                    continue
                txt = _line_text(ln).translate(CLEAN).strip()
                if not txt or _norm_line(txt) in repeated:
                    continue
                if max(s["size"] for s in spans) < body - 1.2:
                    continue  # footers, affiliations, table cells, captions in small print
                bold_heading = all(_is_bold(s) for s in spans) and min(s["size"] for s in spans) >= body - 0.3
                big_heading = min(s["size"] for s in spans) >= body + 1.5
                is_heading = (bold_heading or big_heading) and len(txt) < 110 and not txt.endswith(".")
                if is_heading and re.search(r"[A-Za-z]{3}", txt):
                    title = re.sub(r"\s+", " ", txt)
                    if STOP.match(title):
                        return _finish(sections)
                    skipping = bool(BACK_MATTER.match(title))
                    # consecutive heading lines (wrapped headings) are merged
                    if sections and not sections[-1].text.strip() and sections[-1].page == pno and len(sections) > 1:
                        sections[-1].title += " " + title
                    else:
                        sections.append(Section(title, pno, ""))
                    continue
                if skipping:
                    continue
                cur = sections[-1]
                if cur.page != pno and f"⟦p{pno}⟧" not in cur.text:
                    cur.text += f" ⟦p{pno}⟧"  # page marker → exact page per chunk (see chunking)
                if cur.text.endswith("-") and txt[:1].islower():
                    cur.text = cur.text[:-1] + txt
                else:
                    cur.text += (" " if cur.text else "") + txt
    return _finish(sections)


def _finish(sections: list[Section]) -> list[Section]:
    out = []
    for s in sections:
        s.text = re.sub(r"\s+", " ", s.text).strip()
        s.title = re.sub(r"^[\d.\s]+", "", s.title).strip() or "Body"
        if len(re.sub(r"⟦p\d+⟧", "", s.text)) > 80:
            out.append(s)
    return out


def parse_jats_xml(path: Path) -> list[Section]:
    """PMC / Europe PMC JATS XML (also works on article HTML with <section>/<h2>)."""
    soup = BeautifulSoup(path.read_bytes(), "lxml-xml")
    for tag in soup.find_all(["ref-list", "table-wrap", "fig", "xref", "fn-group", "ack", "supplementary-material"]):
        tag.decompose()
    sections: list[Section] = []
    abstract = soup.find("abstract")
    if abstract:
        sections.append(Section("Abstract", 1, abstract.get_text(" ", strip=True)))
    body = soup.find("body")
    if body:
        for sec in body.find_all("sec", recursive=False) or [body]:
            _walk_sec(sec, [], sections)
    return _finish(sections)


def _walk_sec(sec, path: list[str], out: list[Section]) -> None:
    title_el = sec.find("title", recursive=False)
    title = title_el.get_text(" ", strip=True) if title_el else ""
    if BACK_MATTER.match(title or ""):
        return
    here = path + ([title] if title else [])
    paras = [p.get_text(" ", strip=True) for p in sec.find_all(["p", "list"], recursive=False)]
    if paras:
        out.append(Section(" › ".join(here[-2:]) or "Body", 0, " ".join(paras)))
    for child in sec.find_all("sec", recursive=False):
        _walk_sec(child, here, out)


def parse_file(path: Path) -> list[Section]:
    if path.suffix.lower() == ".pdf":
        return parse_pdf(path)
    if path.suffix.lower() in (".xml", ".html", ".htm"):
        return parse_jats_xml(path)
    raise ValueError(f"unsupported file type: {path}")
