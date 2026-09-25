"use client";

import { ArrowUp, RotateCcw } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { AssistantMessage, Avatar, CitationDrawer, PERSONA_STYLE, UserMessage, type Citation, type GoalProposal, type Msg } from "@/components/chat";
import { PageHeader } from "@/components/ui";
import { getJSON, postSSE } from "@/lib/api";
import { cx } from "@/lib/format";

type Persona = { id: string; name: string; tagline: string };

const SUGGESTIONS: Record<string, string[]> = {
  coach: ["How should I adapt my training to my current cycle phase?", "Is it OK to lift heavy during my period?", "Set me a body-fat goal for December"],
  nutritionist: ["Is my protein intake enough for my training?", "What should I eat before a morning workout with PCOS?", "How is my fibre intake this week?"],
  integrative: ["Is fasted morning cardio a bad idea for women with PCOS?", "How does sleep affect PCOS?", "Does inositol help with PCOS?"],
};

const uid = () => Math.random().toString(36).slice(2);

function CoachInner() {
  const params = useSearchParams();
  const [personas, setPersonas] = useState<Persona[]>([]);
  const [persona, setPersona] = useState(params.get("persona") ?? "coach");
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [thread, setThread] = useState(uid());
  const [cite, setCite] = useState<Citation | null>(null);
  const bottom = useRef<HTMLDivElement>(null);
  const sentInitial = useRef(false);

  useEffect(() => {
    getJSON<Persona[]>("/api/personas").then(setPersonas).catch(() => {});
  }, []);
  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages]);

  const patch = useCallback((id: string, fn: (m: Msg) => Partial<Msg>) => {
    setMessages((ms) => ms.map((m) => (m.id === id ? { ...m, ...fn(m) } : m)));
  }, []);

  const handleStream = useCallback(
    async (aid: string, path: string, body: unknown) => {
      setBusy(true);
      try {
        await postSSE(path, body, (event, data) => {
          const d = data as Record<string, unknown>;
          if (event === "step") patch(aid, (m) => ({ steps: [...(m.steps ?? []), String(d.text)] }));
          else if (event === "token") patch(aid, (m) => ({ content: m.content + String(d.t) }));
          else if (event === "rewrite") patch(aid, () => ({ content: "" }));
          else if (event === "interrupt") patch(aid, () => ({ goal: d.goal as GoalProposal, goalState: "pending" }));
          else if (event === "final")
            patch(aid, (m) => ({
              content: String(d.answer ?? m.content),
              citations: (d.citations as Citation[]) ?? [],
              route: d.route as string,
              streaming: false,
              goal: (d.goal_result as { goal?: GoalProposal })?.goal ?? m.goal ?? (d.goal_proposal as GoalProposal) ?? null,
              goalState: d.goal_result ? ((d.goal_result as { saved: boolean }).saved ? "approved" : "rejected") : m.goalState,
              steps: (d.trace as string[])?.length ? (d.trace as string[]) : m.steps,
              meta: { skills: d.skills as string[], cache: d.cache as { hit?: boolean; similarity?: number } | null, attempts: d.attempts as number, tool_source: d.tool_source as string },
            }));
          else if (event === "error") patch(aid, () => ({ error: String(d.message), streaming: false }));
        });
      } catch (e) {
        patch(aid, () => ({ error: (e as Error).message, streaming: false }));
      } finally {
        patch(aid, () => ({ streaming: false }));
        setBusy(false);
      }
    },
    [patch],
  );

  const send = useCallback(
    async (text: string) => {
      const q = text.trim();
      if (!q || busy) return;
      setInput("");
      const aid = uid();
      setMessages((ms) => [...ms, { id: uid(), role: "user", content: q }, { id: aid, role: "assistant", content: "", persona, streaming: true, steps: [] }]);
      await handleStream(aid, "/api/chat", { message: q, persona, thread_id: thread });
    },
    [busy, persona, thread, handleStream],
  );

  const decideGoal = async (msgId: string, decision: "approve" | "edit" | "reject", goal?: Partial<GoalProposal>) => {
    patch(msgId, () => ({ goalState: decision === "reject" ? "rejected" : "saving", streaming: false }));
    const aid = msgId;
    await handleStream(aid, "/api/chat/resume", { thread_id: thread, decision, goal: goal ?? null });
  };

  useEffect(() => {
    const q = params.get("q");
    if (q && !sentInitial.current) {
      sentInitial.current = true;
      send(q);
    }
  }, [params, send]);

  const reset = () => {
    setMessages([]);
    setThread(uid());
  };

  const current = personas.find((p) => p.id === persona);

  return (
    <div className="mx-auto flex max-w-3xl flex-col">
      <PageHeader title="Your coach" subtitle="Evidence-based, cycle-aware, and grounded in your own data."
        right={messages.length > 0 && <button onClick={reset} className="inline-flex items-center gap-1.5 text-sm text-muted hover:text-ink"><RotateCcw size={14} />New chat</button>} />

      <div className="grid grid-cols-3 gap-2 sm:gap-3">
        {(personas.length ? personas : [{ id: "coach", name: "Fitness Coach", tagline: "" }, { id: "nutritionist", name: "Nutritionist", tagline: "" }, { id: "integrative", name: "Integrative Medicine", tagline: "" }]).map((p) => {
          const active = p.id === persona;
          return (
            <button key={p.id} onClick={() => setPersona(p.id)}
              className={cx("card flex flex-col items-start gap-2 !rounded-2xl p-3 text-left transition sm:flex-row sm:items-center sm:p-4", active ? "ring-2" : "opacity-70 hover:opacity-100")}
              style={active ? { boxShadow: `0 0 0 2px ${PERSONA_STYLE[p.id].color}` } : undefined}>
              <Avatar persona={p.id} />
              <span className="min-w-0">
                <span className="block text-sm font-medium leading-tight">{p.name}</span>
                <span className="hidden text-xs text-muted sm:block">{p.tagline}</span>
              </span>
            </button>
          );
        })}
      </div>

      <div className="mt-6 flex-1 space-y-6">
        {messages.length === 0 && (
          <div className="card p-6 text-center">
            <p className="font-serif text-2xl">Ask {current?.name ?? "your coach"} anything</p>
            <p className="mx-auto mt-1 max-w-md text-sm text-muted">Answers cite research you can open, use your latest data, and escalate to a doctor when something needs medical attention.</p>
            <div className="mt-5 flex flex-col gap-2">
              {SUGGESTIONS[persona]?.map((s) => (
                <button key={s} onClick={() => send(s)} className="rounded-2xl border border-line px-4 py-2.5 text-sm transition hover:border-s1 hover:bg-sage-soft/50">{s}</button>
              ))}
            </div>
          </div>
        )}
        {messages.map((m) =>
          m.role === "user" ? <UserMessage key={m.id} m={m} /> : (
            <AssistantMessage key={m.id} m={m} onCite={setCite} onGoal={(d, g) => decideGoal(m.id, d, g)} />
          ),
        )}
        <div ref={bottom} />
      </div>

      <form onSubmit={(e) => { e.preventDefault(); send(input); }}
        className="sticky bottom-20 mt-6 flex items-end gap-2 rounded-3xl border border-line bg-surface p-2 shadow-soft lg:bottom-6">
        <textarea value={input} onChange={(e) => setInput(e.target.value)} rows={1} placeholder={`Message ${current?.name ?? "your coach"}…`}
          onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(input); } }}
          className="max-h-40 min-h-[44px] flex-1 resize-none bg-transparent px-3 py-2.5 text-[15px] outline-none placeholder:text-muted" />
        <button type="submit" disabled={busy || !input.trim()} aria-label="Send"
          className="grid h-11 w-11 shrink-0 place-items-center rounded-full bg-ink text-bg transition disabled:opacity-30">
          <ArrowUp size={18} />
        </button>
      </form>
      <p className="mt-2 text-center text-[11px] text-muted">Educational, not medical advice. Red-flag symptoms are always referred to a doctor.</p>
      <CitationDrawer c={cite} onClose={() => setCite(null)} />
    </div>
  );
}

export default function CoachPage() {
  return (
    <Suspense>
      <CoachInner />
    </Suspense>
  );
}
