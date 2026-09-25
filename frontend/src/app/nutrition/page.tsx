"use client";

import { useEffect, useState } from "react";
import { getJSON, type Nutrition } from "@/lib/api";
import { MACRO_COLOR, cx, fmt, shortDate } from "@/lib/format";
import { Card, CardTitle, Empty, Kpi, Offline, PageHeader, Skeleton } from "@/components/ui";
import { MacroChart, TargetBars } from "@/components/Charts";

type Meal = { id: number; meal: string; name: string; kcal: number; carbs_g: number; fat_g: number; protein_g: number; fiber_g: number };

export default function NutritionPage() {
  const [n, setN] = useState<Nutrition | null>(null);
  const [meals, setMeals] = useState<Meal[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [days, setDays] = useState(30);

  useEffect(() => {
    getJSON<Nutrition>(`/api/nutrition?days=${days}`)
      .then((d) => {
        setN(d);
        const last = d.daily.at(-1)?.date;
        if (last) getJSON<Meal[]>(`/api/meals?day=${last}`).then(setMeals);
        else setMeals([]);
      })
      .catch((e) => setErr(e.message));
  }, [days]);

  if (err) return <Offline message={err} />;
  if (!n) return <Skeleton className="mx-auto h-96 max-w-6xl" />;
  const a = n.average;
  const lastDay = n.daily.at(-1)?.date;

  return (
    <div className="mx-auto max-w-6xl">
      <PageHeader title="Nutrition" subtitle={`From your Foodvisor logs · ${n.days_logged} of the last ${days} days logged`}
        right={
          <div className="flex rounded-full border border-line bg-surface p-1 text-sm">
            {[14, 30, 90].map((r) => (
              <button key={r} onClick={() => setDays(r)} className={cx("rounded-full px-4 py-1.5 transition", r === days ? "bg-ink text-bg" : "text-muted hover:text-ink")}>{r}d</button>
            ))}
          </div>
        } />
      {n.days_logged === 0 && (
        <div className="mb-4">
          <Empty title="No meals in this period">Upload a Foodvisor screenshot on the Data page, or pick a longer range.</Empty>
        </div>
      )}
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Kpi label="Energy (avg)" value={a.kcal} unit="kcal" sub="per day" />
        <Kpi label="Protein (avg)" value={a.protein_g} unit="g" sub={`target ${n.targets.protein_g} g`} delay={0.05} />
        <Kpi label="Fibre (avg)" value={a.fiber_g} unit="g" sub={`target ≥ ${n.targets.fiber_g} g`} delay={0.1} />
        <Card delay={0.15} className="!p-5">
          <p className="text-[13px] text-muted">Energy split</p>
          {a.pct_kcal && (
            <>
              <div className="mt-3 flex h-3 overflow-hidden rounded-full">
                {(["protein", "carbs", "fat"] as const).map((k) => (
                  <span key={k} style={{ width: `${a.pct_kcal![k]}%`, background: MACRO_COLOR[`${k}_g` as keyof typeof MACRO_COLOR] }} className="border-r-2 border-surface last:border-0" />
                ))}
              </div>
              <div className="mt-3 space-y-0.5 text-xs text-muted">
                <p>Protein <b className="text-ink">{a.pct_kcal.protein}%</b> · Carbs <b className="text-ink">{a.pct_kcal.carbs}%</b> · Fat <b className="text-ink">{a.pct_kcal.fat}%</b></p>
              </div>
            </>
          )}
        </Card>
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardTitle>Macros per day (g)</CardTitle>
          <MacroChart daily={n.daily} height={260} />
        </Card>
        <Card>
          <CardTitle>{lastDay ? `Meals · ${shortDate(lastDay)}` : "Meals"}</CardTitle>
          <ul className="divide-y divide-line">
            {meals.map((m) => (
              <li key={m.id} className="py-2.5">
                <div className="flex justify-between gap-2 text-sm">
                  <span className="font-medium">{m.name}</span>
                  <span className="shrink-0 text-muted">{fmt(m.kcal, 0)} kcal</span>
                </div>
                <p className="text-xs capitalize text-muted">{m.meal} · P {fmt(m.protein_g, 0)} · C {fmt(m.carbs_g, 0)} · F {fmt(m.fat_g, 0)} · Fibre {fmt(m.fiber_g, 0)}</p>
              </li>
            ))}
          </ul>
        </Card>
      </div>

      <div className="mt-4 grid gap-4 md:grid-cols-2">
        <Card>
          <CardTitle right={<span className="text-xs text-muted">- - - target {n.targets.protein_g} g/day</span>}>Protein vs target</CardTitle>
          <TargetBars daily={n.daily} field="protein_g" target={n.targets.protein_g} color="var(--s1)" />
          <p className="mt-2 text-xs text-muted">{n.targets.basis}</p>
        </Card>
        <Card>
          <CardTitle right={<span className="text-xs text-muted">- - - target ≥ {n.targets.fiber_g} g/day</span>}>Fibre vs target</CardTitle>
          <TargetBars daily={n.daily} field="fiber_g" target={n.targets.fiber_g} color="var(--s2)" />
          <p className="mt-2 text-xs text-muted">Fibre supports glycaemic control — relevant for insulin resistance in PCOS.</p>
        </Card>
      </div>
    </div>
  );
}
