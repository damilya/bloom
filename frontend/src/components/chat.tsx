"use client";

import { AnimatePresence, motion } from "framer-motion";
import { BookOpen, Check, ChevronDown, ExternalLink, Pencil, Stethoscope, X } from "lucide-react";
import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Button } from "@/components/ui";
import { cx, fmt, METRIC_LABEL } from "@/lib/format";

export type Citation = {
  n: number; ref: string; title: string; year: number; doi: string; url: string;
  section: string; page: number | null; level: string; text: string;
};
export type GoalProposal = {
  title: string; metric: string | null; target_value: number | null; unit: string | null;
  deadline: string | null; weekly_plan: string[]; rationale: string;
};
export type Msg = {
  id: string;
  role: "user" | "assistant";
  content: string;
  persona?: string;
  steps?: string[];
  citations?: Citation[];
  route?: string;
  streaming?: boolean;
  goal?: GoalProposal | null;
  goalState?: "pending" | "approved" | "rejected" | "saving";
  meta?: { skills?: string[]; cache?: { hit?: boolean; similarity?: number } | null; attempts?: number; tool_source?: string };
  error?: string;
};

export const PERSONA_STYLE: Record<string, { color: string; soft: string; initial: string }> = {
  coach: { color: "var(--s1)", soft: "var(--sage-soft)", initial: "C" },
  nutritionist: { color: "var(--s2)", soft: "var(--sand-soft)", initial: "N" },
  integrative: { color: "var(--s3)", soft: "var(--rose-soft)", initial: "I" },
};

export function Avatar({ persona, size = 36 }: { persona: string; size?: number }) {
  const s = PERSONA_STYLE[persona] ?? PERSONA_STYLE.coach;
  return (
    <span className="grid shrink-0 place-items-center rounded-full font-serif text-[15px] font-medium"
      style={{ width: size, height: size, background: s.soft, color: s.color, border: `1px solid ${s.color}33` }}>
      {s.initial}
    </span>
  );
}

/** Turn [n] and [data] into link tokens the markdown renderer can style. */
function linkify(text: string) {
  return text.replace(/\[(\d+)\](?!\()/g, "[$1](#cite-$1)").replace(/\[data\](?!\()/gi, "[data](#data)");
}

export function AssistantMessage({ m, onCite, onGoal }: {
  m: Msg; onCite: (c: Citation) => void;
  onGoal: (decision: "approve" | "edit" | "reject", goal?: Partial<GoalProposal>) => void;
}) {
  const [showSteps, setShowSteps] = useState(false);
  const doctor = m.route === "doctor";
  return (
    <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} className="flex gap-3">
      <Avatar persona={m.persona ?? "coach"} />
      <div className="min-w-0 flex-1">
        <div className={cx("card px-5 py-4", doctor && "!border-terracotta/40 !bg-terracotta-soft")}>
          {doctor && (
            <p className="mb-2 inline-flex items-center gap-1.5 text-xs font-medium uppercase tracking-wider text-terracotta">
              <Stethoscope size={14} /> Please check with a doctor
            </p>
          )}
          {m.streaming && !m.content && <Thinking step={m.steps?.at(-1)} />}
          {m.content && (
            <div className="prose-chat text-[15px]">
              <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                components={{
                  a: ({ href, children }) => {
                    if (href?.startsWith("#cite-")) {
                      const n = Number(href.slice(6));
                      const c = m.citations?.find((x) => x.n === n);
                      return (
                        <button onClick={() => c && onCite(c)} disabled={!c}
                          className="mx-0.5 inline-flex h-[18px] min-w-[18px] -translate-y-0.5 items-center justify-center rounded-full bg-sage-soft px-1 align-middle text-[11px] font-semibold text-s1 transition hover:bg-s1 hover:text-white disabled:opacity-60"
                          title={c ? `${c.ref} — ${c.title}` : "source"}>
                          {n}
                        </button>
                      );
                    }
                    if (href === "#data")
                      return <span className="mx-0.5 rounded-full bg-sand-soft px-1.5 py-px align-middle text-[10px] font-medium uppercase tracking-wide text-muted">your data</span>;
                    return <a href={href} target="_blank" rel="noreferrer" className="underline decoration-line underline-offset-2">{children}</a>;
                  },
                }}
              >
                {linkify(m.content)}
              </ReactMarkdown>
              {m.streaming && <span className="ml-0.5 inline-block h-4 w-1.5 animate-pulse rounded-sm bg-sage align-middle" />}
            </div>
          )}
          {m.error && <p className="text-sm text-terracotta">{m.error}</p>}

          {!!m.citations?.length && !m.streaming && (
            <div className="mt-4 border-t border-line pt-3">
              <p className="mb-2 text-[11px] font-medium uppercase tracking-wider text-muted">Sources</p>
              <div className="flex flex-wrap gap-2">
                {m.citations.map((c) => (
                  <button key={c.n} onClick={() => onCite(c)}
                    className="group inline-flex max-w-full items-center gap-2 rounded-full border border-line bg-surface px-3 py-1.5 text-left text-xs transition hover:border-s1">
                    <span className="grid h-4 w-4 shrink-0 place-items-center rounded-full bg-sage-soft text-[10px] font-semibold text-s1">{c.n}</span>
                    <span className="truncate">{c.ref}</span>
                    <span className="hidden shrink-0 text-muted sm:inline">· {c.level}</span>
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>

        {m.goal && <GoalCard goal={m.goal} state={m.goalState ?? "pending"} onDecide={onGoal} />}

        {!!m.steps?.length && (
          <div className="mt-2 pl-1">
            <button onClick={() => setShowSteps((v) => !v)} className="inline-flex items-center gap-1 text-xs text-muted hover:text-ink">
              <ChevronDown size={14} className={cx("transition", showSteps && "rotate-180")} />
              How I got here · {m.steps.length} steps
              {m.meta?.cache?.hit && <span className="ml-1 rounded-full bg-sand-soft px-2 py-px">cached</span>}
              {!!m.meta?.skills?.length && <span className="ml-1 rounded-full bg-rose-soft px-2 py-px">skill: {m.meta.skills.join(", ")}</span>}
            </button>
            <AnimatePresence>
              {showSteps && (
                <motion.ol initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }}
                  className="mt-2 space-y-1 overflow-hidden border-l border-line pl-4 text-xs text-muted">
                  {m.steps.map((s, i) => <li key={i}>{s}</li>)}
                </motion.ol>
              )}
            </AnimatePresence>
          </div>
        )}
      </div>
    </motion.div>
  );
}

function Thinking({ step }: { step?: string }) {
  return (
    <div className="flex items-center gap-3 text-sm text-muted">
      <span className="flex gap-1">
        {[0, 1, 2].map((i) => (
          <motion.span key={i} className="h-1.5 w-1.5 rounded-full bg-sage"
            animate={{ opacity: [0.3, 1, 0.3] }} transition={{ duration: 1.2, repeat: Infinity, delay: i * 0.2 }} />
        ))}
      </span>
      {step ?? "Thinking…"}
    </div>
  );
}

export function UserMessage({ m }: { m: Msg }) {
  return (
    <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} className="flex justify-end">
      <div className="max-w-[85%] rounded-3xl rounded-br-md bg-ink px-4 py-3 text-[15px] leading-relaxed text-bg">{m.content}</div>
    </motion.div>
  );
}

function GoalCard({ goal, state, onDecide }: { goal: GoalProposal; state: string; onDecide: (d: "approve" | "edit" | "reject", g?: Partial<GoalProposal>) => void }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<GoalProposal>(goal);
  const done = state === "approved" || state === "rejected";
  return (
    <motion.div initial={{ opacity: 0, scale: 0.98 }} animate={{ opacity: 1, scale: 1 }}
      className={cx("mt-3 rounded-3xl border-2 border-dashed p-5", done ? "border-line opacity-80" : "border-s1/40 bg-sage-soft/40")}>
      <p className="mb-1 text-[11px] font-medium uppercase tracking-wider text-s1">
        {state === "approved" ? "Goal saved" : state === "rejected" ? "Goal dismissed" : "Proposed goal · needs your approval"}
      </p>
      {editing ? (
        <div className="space-y-3">
          <input className="w-full rounded-xl border border-line bg-surface px-3 py-2 font-serif text-lg" value={draft.title}
            onChange={(e) => setDraft({ ...draft, title: e.target.value })} />
          <div className="grid grid-cols-2 gap-3 text-sm">
            <label className="flex flex-col gap-1 text-muted">Target {draft.unit ? `(${draft.unit})` : ""}
              <input type="number" step="0.1" className="rounded-xl border border-line bg-surface px-3 py-2 text-ink" value={draft.target_value ?? ""}
                onChange={(e) => setDraft({ ...draft, target_value: e.target.value === "" ? null : Number(e.target.value) })} />
            </label>
            <label className="flex flex-col gap-1 text-muted">Deadline
              <input type="date" className="rounded-xl border border-line bg-surface px-3 py-2 text-ink" value={draft.deadline ?? ""}
                onChange={(e) => setDraft({ ...draft, deadline: e.target.value })} />
            </label>
          </div>
          <textarea rows={4} className="w-full rounded-xl border border-line bg-surface px-3 py-2 text-sm"
            value={draft.weekly_plan.join("\n")} onChange={(e) => setDraft({ ...draft, weekly_plan: e.target.value.split("\n").filter(Boolean) })} />
        </div>
      ) : (
        <>
          <p className="font-serif text-xl leading-snug">{goal.title}</p>
          <p className="mt-1 text-sm text-muted">
            {goal.metric && <>{METRIC_LABEL[goal.metric] ?? goal.metric}: <b className="text-ink">{fmt(goal.target_value)} {goal.unit}</b> · </>}
            {goal.deadline && <>by {goal.deadline}</>}
          </p>
          <ul className="mt-3 space-y-1.5 text-sm">
            {goal.weekly_plan.map((p, i) => (
              <li key={i} className="flex gap-2"><Check size={16} className="mt-0.5 shrink-0 text-s1" />{p}</li>
            ))}
          </ul>
          <p className="mt-3 text-xs text-muted">{goal.rationale}</p>
        </>
      )}
      {!done && (
        <div className="mt-4 flex flex-wrap gap-2">
          {editing ? (
            <>
              <Button onClick={() => onDecide("edit", draft)} disabled={state === "saving"}><Check size={16} />Save edited goal</Button>
              <Button variant="ghost" onClick={() => setEditing(false)}>Cancel</Button>
            </>
          ) : (
            <>
              <Button onClick={() => onDecide("approve")} disabled={state === "saving"}><Check size={16} />{state === "saving" ? "Saving…" : "Approve"}</Button>
              <Button variant="ghost" onClick={() => setEditing(true)}><Pencil size={14} />Edit</Button>
              <Button variant="danger" onClick={() => onDecide("reject")}><X size={16} />Not now</Button>
            </>
          )}
        </div>
      )}
    </motion.div>
  );
}

export function CitationDrawer({ c, onClose }: { c: Citation | null; onClose: () => void }) {
  return (
    <AnimatePresence>
      {c && (
        <>
          <motion.div className="fixed inset-0 z-40 bg-ink/20 backdrop-blur-[2px]" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={onClose} />
          <motion.aside initial={{ x: "100%" }} animate={{ x: 0 }} exit={{ x: "100%" }} transition={{ type: "spring", damping: 30, stiffness: 280 }}
            className="fixed inset-y-0 right-0 z-50 flex w-full max-w-md flex-col border-l border-line bg-surface p-6 shadow-2xl">
            <div className="flex items-center justify-between">
              <span className="inline-flex items-center gap-2 text-xs font-medium uppercase tracking-wider text-muted"><BookOpen size={14} /> Source [{c.n}]</span>
              <button onClick={onClose} className="rounded-full p-1.5 text-muted hover:bg-surface-2 hover:text-ink" aria-label="Close"><X size={18} /></button>
            </div>
            <h3 className="mt-4 font-serif text-2xl leading-snug">{c.title}</h3>
            <p className="mt-2 text-sm text-muted">{c.ref} · {c.year}</p>
            <div className="mt-4 flex flex-wrap gap-2 text-xs">
              <span className="rounded-full bg-sage-soft px-3 py-1 text-s1">{c.level}</span>
              <span className="rounded-full bg-surface-2 px-3 py-1 text-muted">{c.section}{c.page ? ` · p. ${c.page}` : ""}</span>
            </div>
            <p className="mb-2 mt-6 text-[11px] font-medium uppercase tracking-wider text-muted">Passage used</p>
            <blockquote className="flex-1 overflow-y-auto rounded-2xl bg-surface-2 p-4 font-serif text-[15px] leading-relaxed">“{c.text}”</blockquote>
            <div className="mt-5 flex gap-2">
              <a href={c.url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1.5 rounded-full bg-ink px-4 py-2 text-sm font-medium text-bg">Read full paper <ExternalLink size={14} /></a>
              {c.doi && <a href={`https://doi.org/${c.doi}`} target="_blank" rel="noreferrer" className="inline-flex items-center rounded-full border border-line px-4 py-2 text-sm">DOI</a>}
            </div>
          </motion.aside>
        </>
      )}
    </AnimatePresence>
  );
}
