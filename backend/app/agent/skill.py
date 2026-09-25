"""Runtime loader for Claude-style Skills (SKILL.md with YAML frontmatter).

The same `skills/womens-health-evidence/` folder works in Claude Code / Claude Desktop (Anthropic
Skill format) and in this app: we parse `name` + `description`, derive trigger terms from the
description, and inject the body into the system prompt only when it triggers (progressive
disclosure — the ~1.5k-token body is not paid for on unrelated questions).
"""
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from app.config import ROOT

SKILLS_DIR = ROOT / "skills"


@dataclass
class Skill:
    name: str
    description: str
    body: str
    triggers: list[str]

    def matches(self, text: str) -> list[str]:
        t = text.lower()
        return [kw for kw in self.triggers if re.search(rf"\b{re.escape(kw)}", t)]


# Extra stems for recall on user phrasing ("my period", "empty stomach", "hormonal")
EXTRA_TRIGGERS = {
    "womens-health-evidence": [
        "pcos", "polycystic", "period", "menstru", "cycle", "luteal", "follicular", "ovulat", "hormon",
        "estrogen", "oestrogen", "progesterone", "androgen", "testosterone", "insulin", "fasted", "fasting",
        "empty stomach", "before breakfast", "women", "woman", "female", "inositol", "red-s", "energy availability",
        "amenorrh", "pms", "cramps", "fertility",
    ]
}


def _parse(path: Path) -> Skill:
    raw = path.read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", raw, re.S)
    if not m:
        raise ValueError(f"{path}: missing YAML frontmatter")
    front, body = m.groups()
    meta = dict(re.findall(r"^(\w+):\s*(.+)$", front, re.M))
    name = meta["name"].strip()
    return Skill(name=name, description=meta["description"].strip(), body=body.strip(),
                 triggers=EXTRA_TRIGGERS.get(name, []))


@lru_cache
def load_skills() -> dict[str, Skill]:
    return {s.name: s for s in (_parse(p) for p in SKILLS_DIR.glob("*/SKILL.md"))}


def select_skills(text: str, llm_flag: bool = False) -> list[Skill]:
    """Trigger when keywords match OR the triage LLM flagged the topic as women's-health related."""
    return [s for s in load_skills().values() if s.matches(text) or llm_flag]
