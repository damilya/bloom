"""Output guardrail: domain constraints on what the coach may say.

  • no medication / supplement dosing  → replaced with "discuss the dose with your doctor"
  • no definitive diagnoses ("you have PCOS/diabetes/…")  → softened + flagged
  • health-condition answers get a short educational disclaimer
  • citation indices must exist in the evidence block (invalid ones are stripped)
"""
import re

DRUGS = r"(metformin|spironolactone|inositol|myo-inositol|letrozole|clomi(ph|f)ene|berberine|vitamin d|iron|" \
        r"ozempic|semaglutide|contracepti\w*|the pill|levothyroxine|ibuprofen|melatonin)"
DOSE = r"\d+(?:[.,]\d+)?\s?(mg|mcg|µg|g|iu|ui|units?)\b"
DIAGNOSIS = r"\byou (definitely |clearly |probably )?(have|are suffering from|are diagnosed with) " \
            r"(pcos|diabetes|insulin resistance|hypothyroidism|an eating disorder|endometriosis|anemia|anaemia)"
CONDITION_TERMS = r"\b(pcos|insulin|hormon|period|menstru|amenorrh|diagnos|thyroid|medication|supplement)"
DISCLAIMER = "\n\n_Educational information, not a diagnosis — for medical decisions, talk to your doctor._"


def check_output(text: str, n_evidence: int) -> tuple[str, list[str]]:
    flags: list[str] = []
    out = text

    # dosing sentences that mention a drug/supplement
    sentences = re.split(r"(?<=[.!?])\s+", out)
    kept = []
    for s in sentences:
        if re.search(DRUGS, s, re.I) and re.search(DOSE, s, re.I):
            flags.append("dosing_removed")
            kept.append("Please discuss any medication or supplement dose with your doctor.")
        else:
            kept.append(s)
    out = " ".join(kept) if flags else out

    if re.search(DIAGNOSIS, out, re.I):
        flags.append("diagnosis_softened")
        out = re.sub(DIAGNOSIS, lambda m: f"your data may be consistent with {m.group(3)} — only a doctor can diagnose this", out, flags=re.I)

    def fix_cite(m):
        n = int(m.group(1))
        if 1 <= n <= n_evidence:
            return m.group(0)
        flags.append(f"invalid_citation_{n}")
        return ""

    out = re.sub(r"\[(\d+)\]", fix_cite, out)

    # drop a model-written disclaimer line (the prompt says not to) so exactly one standard disclaimer remains
    out = re.sub(r"\n+[^\n]*(educational|not a substitute for (professional )?medical)[^\n]*\.?\s*$", "", out, flags=re.I).rstrip()
    if re.search(CONDITION_TERMS, out, re.I) and "not a diagnosis" not in out:
        out += DISCLAIMER
    return out, flags
