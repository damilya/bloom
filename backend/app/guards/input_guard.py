"""Input guardrail: prompt-injection heuristics + PII redaction (custom, dependency-free).

Why custom instead of Guardrails AI / NeMo: the threat model is narrow (single user, health data
behind tools, no browsing), and heuristics run in ~0 ms with zero cost. The *semantic* checks
(off-topic, red flags) live in the triage LLM node where they get context. Measured by the
injection / off-domain slice of the golden set.
"""
import re
from dataclasses import dataclass, field

INJECTION_PATTERNS = [
    r"ignore (all |any |the )?(previous|prior|above|earlier) (instructions|rules|prompts?)",
    r"disregard (all |the )?(previous|prior|above|system)",
    r"(reveal|print|show|repeat|output) (me )?(your|the) (system|hidden|initial) (prompt|instructions)",
    r"you are now (?!in )",  # "you are now DAN"
    r"\b(jailbreak|DAN mode|developer mode)\b",
    r"act as (an? )?(unfiltered|unrestricted|uncensored)",
    r"pretend (that )?you (have no|don't have) (rules|restrictions|guidelines)",
    r"</?(system|assistant|instructions?)>",
    r"\bsave_goal\b|\bcall the tool\b",
]
PII_PATTERNS = {
    "EMAIL": r"[\w.+-]+@[\w-]+\.[\w.-]+",
    "PHONE": r"(?<!\d)(\+?\d[\d\s().-]{8,}\d)(?!\d)",
    "IBAN": r"\b[A-Z]{2}\d{2}(?:\s?[A-Z0-9]{4}){3,7}\b",
    "BE_NATIONAL_ID": r"\b\d{2}\.\d{2}\.\d{2}-\d{3}\.\d{2}\b",
    "CARD": r"\b(?:\d[ -]?){13,19}\b",
}


@dataclass
class InputCheck:
    blocked: bool
    text: str
    reasons: list[str] = field(default_factory=list)
    redactions: list[str] = field(default_factory=list)


def check_input(text: str, max_chars: int = 4000) -> InputCheck:
    reasons = []
    if len(text) > max_chars:
        reasons.append("too_long")
    for p in INJECTION_PATTERNS:
        if re.search(p, text, re.I):
            reasons.append(f"injection:{p[:30]}")
    redactions = []
    clean = text
    for label, p in PII_PATTERNS.items():
        # don't treat plain measurements like "62.4 kg" or dates as phones/cards
        def repl(m, label=label):
            s = m.group(0)
            if label in ("PHONE", "CARD") and (len(re.sub(r"\D", "", s)) < 9 or re.fullmatch(r"[\d\s./-]{6,10}", s)):
                return s
            redactions.append(label)
            return f"[{label}]"
        clean = re.sub(p, repl, clean)
    return InputCheck(blocked=bool(reasons), text=clean, reasons=reasons, redactions=redactions)


REFUSAL = (
    "I can't follow that request — it looks like an attempt to change my instructions. "
    "I'm happy to help with your training, nutrition, cycle or PCOS questions though!"
)
