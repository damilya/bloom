"use client";

import { useEffect, useState } from "react";
import { getJSON, type Band, type Dashboard, type Trend } from "@/lib/api";
import { METRIC_LABEL, SOURCE_LABEL, cx, fmt } from "@/lib/format";
import { Card, CardTitle, Offline, PageHeader, PhaseLegend, Skeleton } from "@/components/ui";
import { TrendChart } from "@/components/Charts";

const RANGES = [30, 90, 180];
const BODY = ["weight_kg", "body_fat_pct", "muscle_mass_kg", "fat_mass_kg"];
const TANITA = ["visceral_fat", "water_pct", "bmr_kcal", "metabolic_age"];
const VITALS = ["resting_hr", "hrv_ms", "sleep_hours", "steps"];

export default function Trends() {
  const [days, setDays] = useState(90);
  const [bands, setBands] = useState<Band[]>([]);
  const [trends, setTrends] = useState<Record<string, Trend>>({});
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    setTrends({});
    getJSON<Dashboard>(`/api/dashboard?days=${days}`).then((d) => setBands(d.phase_bands)).catch((e) => setErr(e.message));
    [...BODY, ...TANITA, ...VITALS].forEach((m) =>
      getJSON<Trend>(`/api/trend?metric=${m}&days=${days}`).then((t) => setTrends((s) => ({ ...s, [m]: t }))).catch(() => {}),
    );
  }, [days]);

  if (err) return <Offline message={err} />;

  const Section = ({ title, metrics, note }: { title: string; metrics: string[]; note?: string }) => (
    <>
      <h2 className="mb-3 mt-10 font-serif text-2xl">{title}</h2>
      {note && <p className="-mt-2 mb-4 text-sm text-muted">{note}</p>}
      <div className="grid gap-4 md:grid-cols-2">
        {metrics.map((m, i) => {
          const t = trends[m];
          const change = t && Object.entries(t.summary)[0];
          return (
            <Card key={m} delay={i * 0.04}>
              <CardTitle right={change && <span className="text-xs text-muted">{change[1].change > 0 ? "+" : ""}{fmt(change[1].change)} {t.unit} · {SOURCE_LABEL[change[0]] ?? change[0]}</span>}>
                {METRIC_LABEL[m] ?? m}
              </CardTitle>
              {t ? <TrendChart trend={t} bands={bands} height={200} /> : <Skeleton className="h-[200px]" />}
            </Card>
          );
        })}
      </div>
    </>
  );

  return (
    <div className="mx-auto max-w-6xl">
      <PageHeader title="Trends" subtitle="Every scale, watch and gym scan on one timeline — shaded by cycle phase."
        right={
          <div className="flex rounded-full border border-line bg-surface p-1 text-sm">
            {RANGES.map((r) => (
              <button key={r} onClick={() => setDays(r)} className={cx("rounded-full px-4 py-1.5 transition", r === days ? "bg-ink text-bg" : "text-muted hover:text-ink")}>{r}d</button>
            ))}
          </div>
        } />
      <PhaseLegend />
      <Section title="Body composition" metrics={BODY} note="Withings (home, frequent) and Tanita (gym, bi-weekly) disagree by design — compare trends within a source." />
      <Section title="Tanita scan details" metrics={TANITA} />
      <Section title="Recovery & activity" metrics={VITALS} note="From Apple Watch via Apple Health." />
    </div>
  );
}
