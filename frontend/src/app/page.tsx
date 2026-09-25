"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ArrowRight, CloudRain, CloudSun, Dumbbell, Footprints, Flower2, Sun as SunIcon, Wind } from "lucide-react";
import { getJSON, type Dashboard, type WeatherDay, type Workout } from "@/lib/api";
import { PHASES, fmt, greeting, phaseKey, shortDate, weekday } from "@/lib/format";
import { Card, CardTitle, Empty, Kpi, Offline, PageHeader, PhaseGlyph, PhaseLegend, PhasePill, ProgressBar, Skeleton } from "@/components/ui";
import { MacroChart, TrendChart } from "@/components/Charts";

export default function Today() {
  const [d, setD] = useState<Dashboard | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    getJSON<Dashboard>("/api/dashboard?days=90").then(setD).catch((e) => setErr(String(e.message ?? e)));
  }, []);

  if (err) return <Offline message={err} />;
  if (!d) return <Loading />;

  const L = d.latest;
  const phase = PHASES[phaseKey(d.cycle.phase)];
  const today = d.nutrition.daily.at(-1);

  return (
    <div className="mx-auto max-w-6xl">
      <PageHeader
        title={<>{greeting()}, {d.user}</>}
        subtitle={new Date().toLocaleDateString("en-GB", { weekday: "long", day: "numeric", month: "long" })}
        right={<PhasePill cycle={d.cycle} large />}
      />

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Kpi label="Weight" value={L.weight_kg?.value} unit="kg" delta={L.weight_kg?.delta_7d} metric="weight_kg" delay={0} />
        <Kpi label="Body fat" value={L.body_fat_pct?.value} unit="%" delta={L.body_fat_pct?.delta_7d} metric="body_fat_pct" delay={0.05} />
        <Kpi label="Muscle mass" value={L.muscle_mass_kg?.value} unit="kg" delta={L.muscle_mass_kg?.delta_7d} metric="muscle_mass_kg" delay={0.1} />
        <Kpi label="Protein today" value={today?.protein_g} unit="g" sub={`target ${d.nutrition.targets.protein_g} g`} delay={0.15} />
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2" delay={0.1}>
          <CardTitle right={<PhaseLegend />}>Weight · 90 days</CardTitle>
          <TrendChart trend={d.trends.weight_kg} bands={d.phase_bands} height={300} target={d.goals.find((g) => g.metric === "weight_kg")?.target_value} />
        </Card>

        <div className="flex flex-col gap-4">
          <Card delay={0.15} className="relative overflow-hidden">
            <div className="pointer-events-none absolute -right-10 -top-10 h-40 w-40 rounded-full opacity-60 blur-2xl" style={{ background: phase.soft }} />
            <CardTitle>Your cycle</CardTitle>
            {d.cycle.known ? (
              <>
                <div className="flex items-center gap-3">
                  <PhaseGlyph color={phase.color} size={34} />
                  <div>
                    <p className="font-serif text-2xl leading-tight">{phase.label} phase</p>
                    <p className="text-sm text-muted">Day {d.cycle.cycle_day} of ~{d.cycle.avg_cycle_len}</p>
                  </div>
                </div>
                <p className="mt-4 text-sm">{phase.hint}</p>
                <p className="mt-2 text-xs text-muted">
                  Next period expected ~{shortDate(d.cycle.expected_next_period!)} · {d.cycle.confidence} confidence
                </p>
              </>
            ) : (
              <p className="text-sm text-muted">{d.cycle.message}</p>
            )}
          </Card>
          <WeatherCard days={d.weather.days} />
        </div>
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2" delay={0.2}>
          <CardTitle right={<span className="text-xs text-muted">avg {fmt(d.nutrition.average.kcal, 0)} kcal/day</span>}>Macros · 14 days</CardTitle>
          <MacroChart daily={d.nutrition.daily} />
        </Card>
        <Card delay={0.25}>
          <CardTitle right={<Link href="/goals" className="text-xs text-muted hover:text-ink">All goals →</Link>}>Goals</CardTitle>
          {d.goals.length ? (
            <ul className="space-y-5">
              {d.goals.slice(0, 3).map((g) => (
                <li key={g.id}>
                  <div className="mb-1.5 flex justify-between gap-2 text-sm">
                    <span className="font-medium">{g.title}</span>
                    {g.progress && <span className="text-muted">{g.progress.pct}%</span>}
                  </div>
                  <ProgressBar pct={g.progress?.pct ?? 0} />
                  {g.deadline && <p className="mt-1 text-xs text-muted">by {shortDate(g.deadline)}</p>}
                </li>
              ))}
            </ul>
          ) : (
            <Empty title="No goals yet">Ask your coach to set one with you — you approve it before it’s saved.</Empty>
          )}
        </Card>
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <Card delay={0.3}>
          <CardTitle right={<span className="text-xs text-muted">{d.workouts.per_week} sessions / week</span>}>Recent training</CardTitle>
          <ul className="divide-y divide-line">
            {d.workouts.items.slice(0, 5).map((w) => <WorkoutRow key={w.id} w={w} />)}
          </ul>
        </Card>
        <Card delay={0.35} className="flex flex-col">
          <CardTitle>Ask your coach</CardTitle>
          <p className="font-serif text-xl leading-snug">Evidence-based answers that know your data, your cycle and PCOS.</p>
          <div className="mt-4 flex flex-col gap-2">
            {[
              ["coach", `I'm in my ${phase.label.toLowerCase()} phase — how should I train this week?`],
              ["nutritionist", "Is my protein and fibre intake enough for PCOS?"],
              ["integrative", "Is fasted morning cardio a bad idea for women with PCOS?"],
            ].map(([p, q]) => (
              <Link key={q} href={`/coach?persona=${p}&q=${encodeURIComponent(q)}`}
                className="group flex items-center justify-between gap-3 rounded-2xl border border-line px-4 py-3 text-sm transition hover:border-sage hover:bg-sage-soft/50">
                {q}
                <ArrowRight size={16} className="shrink-0 text-muted transition group-hover:translate-x-0.5 group-hover:text-sage" />
              </Link>
            ))}
          </div>
        </Card>
      </div>
    </div>
  );
}

function WorkoutRow({ w }: { w: Workout }) {
  const Icon = w.type === "running" || w.type === "walking" ? Footprints : w.type === "yoga" ? Flower2 : Dumbbell;
  return (
    <li className="flex items-center gap-3 py-3">
      <span className="grid h-10 w-10 shrink-0 place-items-center rounded-2xl bg-surface-2 text-sage"><Icon size={18} /></span>
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium capitalize">{w.details?.name ?? w.type}</p>
        <p className="text-xs text-muted">
          {shortDate(w.start_ts.slice(0, 10))} · {Math.round(w.duration_min)} min
          {w.distance_km ? ` · ${fmt(w.distance_km)} km` : ""}{w.avg_hr ? ` · ${w.avg_hr} bpm` : ""}
        </p>
      </div>
      <span className="rounded-full bg-surface-2 px-2.5 py-1 text-[11px] text-muted">{w.source === "kinetix" ? "Kinetix" : "Apple Watch"}</span>
    </li>
  );
}

function WeatherCard({ days }: { days: WeatherDay[] }) {
  if (!days.length) return null;
  const icon = (w: WeatherDay) => (w.precip_mm > 1 ? CloudRain : w.weather_code <= 1 ? SunIcon : CloudSun);
  const runnable = (w: WeatherDay) => w.precip_mm < 1 && w.tmax > 5 && w.tmax < 27;
  return (
    <Card delay={0.2}>
      <CardTitle right={<span className="inline-flex items-center gap-1 text-xs text-muted"><Wind size={12} />Brussels</span>}>Outdoor forecast</CardTitle>
      <div className="grid grid-cols-5 gap-1 text-center">
        {days.slice(0, 5).map((w) => {
          const I = icon(w);
          return (
            <div key={w.date} className="rounded-2xl py-2" title={w.summary}>
              <p className="text-xs text-muted">{weekday(w.date)}</p>
              <I size={20} className="mx-auto my-1.5 text-muted" strokeWidth={1.6} />
              <p className="text-sm font-medium">{Math.round(w.tmax)}°</p>
              <span className={`mx-auto mt-1 block h-1 w-5 rounded-full ${runnable(w) ? "bg-s1" : "bg-line"}`} title={runnable(w) ? "good for a run" : ""} />
            </div>
          );
        })}
      </div>
      <p className="mt-2 text-[11px] text-muted"><span className="mr-1 inline-block h-1 w-3 rounded-full bg-s1 align-middle" />good for an outdoor run</p>
    </Card>
  );
}

function Loading() {
  return (
    <div className="mx-auto max-w-6xl space-y-4">
      <Skeleton className="h-12 w-72" />
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-32" />)}</div>
      <div className="grid gap-4 lg:grid-cols-3"><Skeleton className="h-80 lg:col-span-2" /><Skeleton className="h-80" /></div>
    </div>
  );
}
