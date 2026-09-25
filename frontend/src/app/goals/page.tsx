"use client";

import Link from "next/link";
import { Check, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { API, getJSON, type Dashboard, type Goal, type Trend } from "@/lib/api";
import { METRIC_LABEL, fmt, shortDate } from "@/lib/format";
import { Button, Card, CardTitle, Empty, Offline, PageHeader, ProgressBar, Skeleton } from "@/components/ui";
import { TrendChart } from "@/components/Charts";

export default function Goals() {
  const [goals, setGoals] = useState<Goal[] | null>(null);
  const [trends, setTrends] = useState<Record<string, Trend>>({});
  const [bands, setBands] = useState<Dashboard["phase_bands"]>([]);
  const [err, setErr] = useState<string | null>(null);

  const load = () =>
    getJSON<Goal[]>("/api/goals")
      .then((gs) => {
        setGoals(gs);
        gs.filter((g) => g.metric).forEach((g) =>
          getJSON<Trend>(`/api/trend?metric=${g.metric}&days=60`).then((t) => setTrends((s) => ({ ...s, [g.metric!]: t }))),
        );
      })
      .catch((e) => setErr(e.message));

  useEffect(() => {
    load();
    getJSON<Dashboard>("/api/dashboard?days=60").then((d) => setBands(d.phase_bands)).catch(() => {});
  }, []);

  const setStatus = async (id: number, status: string) => {
    await fetch(`${API}/api/goals/${id}`, { method: "PATCH", headers: { "content-type": "application/json" }, body: JSON.stringify({ status }) });
    load();
  };

  if (err) return <Offline message={err} />;
  if (!goals) return <Skeleton className="mx-auto h-96 max-w-5xl" />;

  return (
    <div className="mx-auto max-w-5xl">
      <PageHeader title="Goals" subtitle="Proposed by your coach, approved by you, tracked automatically." />
      {!goals.length && (
        <Empty title="No active goals">
          <p>Ask your coach something like “set me a body-fat goal for December”. You’ll review and approve it before it’s saved.</p>
          <Link href="/coach?persona=coach&q=Set%20me%20a%20realistic%20body-fat%20goal%20for%20December" className="mt-4 inline-block rounded-full bg-ink px-4 py-2 text-sm text-bg">Set a goal with my coach</Link>
        </Empty>
      )}
      <div className="space-y-4">
        {goals.map((g, i) => (
          <Card key={g.id} delay={i * 0.05}>
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div>
                <p className="font-serif text-2xl leading-snug">{g.title}</p>
                <p className="mt-1 text-sm text-muted">
                  {g.metric && <>{METRIC_LABEL[g.metric] ?? g.metric} → <b className="text-ink">{fmt(g.target_value)} {g.unit}</b> · </>}
                  {g.deadline && <>by {shortDate(g.deadline)} · </>}set {shortDate(g.created_at.slice(0, 10))}
                </p>
              </div>
              <div className="flex gap-2">
                <Button variant="soft" onClick={() => setStatus(g.id, "done")}><Check size={15} />Done</Button>
                <Button variant="ghost" onClick={() => setStatus(g.id, "archived")} aria-label="Archive"><Trash2 size={15} /></Button>
              </div>
            </div>
            {g.progress && (
              <div className="mt-5">
                <div className="mb-1.5 flex justify-between text-sm">
                  <span className="text-muted">from {fmt(g.progress.baseline)} → now <b className="text-ink">{fmt(g.progress.current)}</b></span>
                  <span className="font-medium">{g.progress.pct}%</span>
                </div>
                <ProgressBar pct={g.progress.pct} />
              </div>
            )}
            <div className="mt-6 grid gap-6 md:grid-cols-2">
              <div>
                <CardTitle>Weekly plan</CardTitle>
                <ul className="space-y-2 text-sm">
                  {g.weekly_plan.map((p, j) => <li key={j} className="flex gap-2"><Check size={16} className="mt-0.5 shrink-0 text-s1" />{p}</li>)}
                </ul>
                {g.rationale && <p className="mt-4 text-xs text-muted">{g.rationale}</p>}
              </div>
              {g.metric && trends[g.metric] && (
                <div>
                  <CardTitle>Last 60 days</CardTitle>
                  <TrendChart trend={trends[g.metric]} bands={bands} height={170} target={g.target_value} />
                </div>
              )}
            </div>
          </Card>
        ))}
      </div>
    </div>
  );
}
