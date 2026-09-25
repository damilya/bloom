"""Download the corpus: PDF from the PMC Open-Access S3 bucket, JATS XML fallback from Europe PMC.

(Europe PMC's `?pdf=render` sits behind a Cloudflare JS challenge, so we use the official
`pmc-oa-opendata` AWS Open Data bucket instead.)
    python -m app.rag.fetch
"""
import httpx

from app.config import get_settings
from app.rag.papers import PAPERS

S3 = "https://pmc-oa-opendata.s3.amazonaws.com"
EPMC_XML = "https://www.ebi.ac.uk/europepmc/webservices/rest/{pmcid}/fullTextXML"


def papers_dir():
    d = get_settings().abs_path("data/papers")
    d.mkdir(parents=True, exist_ok=True)
    return d


def _s3_meta(client: httpx.Client, pmcid: str) -> dict | None:
    meta = None
    for v in range(1, 6):
        r = client.get(f"{S3}/{pmcid}.{v}/{pmcid}.{v}.json")
        if r.status_code != 200:
            break
        meta = r.json()
    return meta


def fetch_one(client: httpx.Client, pmcid: str) -> str:
    out = papers_dir()
    if (out / f"{pmcid}.pdf").exists() or (out / f"{pmcid}.xml").exists():
        return "cached"
    meta = _s3_meta(client, pmcid)
    if meta and meta.get("pdf_url"):
        url = meta["pdf_url"].split("?")[0].replace("s3://pmc-oa-opendata", S3)
        r = client.get(url)
        if r.status_code == 200 and r.content[:4] == b"%PDF":
            (out / f"{pmcid}.pdf").write_bytes(r.content)
            return "pdf"
    if meta and meta.get("xml_url"):
        url = meta["xml_url"].split("?")[0].replace("s3://pmc-oa-opendata", S3)
        r = client.get(url)
        if r.status_code == 200:
            (out / f"{pmcid}.xml").write_bytes(r.content)
            return "xml(s3)"
    r = client.get(EPMC_XML.format(pmcid=pmcid))
    if r.status_code == 200 and b"<body" in r.content:
        (out / f"{pmcid}.xml").write_bytes(r.content)
        return "xml(europepmc)"
    return "FAILED"


def fetch_all() -> dict:
    with httpx.Client(timeout=60, follow_redirects=True) as client:
        return {p["pmcid"]: fetch_one(client, p["pmcid"]) for p in PAPERS}


if __name__ == "__main__":
    for k, v in fetch_all().items():
        print(f"{k}: {v}")
