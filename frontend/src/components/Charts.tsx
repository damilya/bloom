"use client";

import {
  Bar, BarChart, CartesianGrid, Line, LineChart, ReferenceArea, ReferenceLine,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import type { Band, NutritionDay, Trend } from "@/lib/api";
import { MACRO_COLOR, PHASES, SOURCE_COLOR, SOURCE_LABEL, fmt, phaseKey, shortDate } from "@/lib/format";

const day = (iso: string) => new Date(iso + "T00:00:00").getTime();

type Row = { t: number; date: string } & Record<string, number | string | undefined>;

function mergeBySource(trend: Trend): { rows: Row[]; sources: string[] } {
  const map = new Map<string, Row>();
  const sources = new Set<string>();
  for (const p of trend.points) {
    sources.add(p.source);
    const r = map.get(p.date) ?? { t: day(p.date), date: p.date };
    r[p.source] = p.value;
    map.set(p.date, r);
  }
  const order = ["withings", "tanita", "apple_health"];
  const rows = [...map.values()].sort((a, b) => a.t - b.t);
  const srcs = [...sources].sort((a, b) => order.indexOf(a) - order.indexOf(b));
  // Dense daily sources get a 7-day rolling mean: the line shows the trend, dots show raw readings.
  for (const s of srcs) {
    const pts = rows.filter((r) => typeof r[s] === "number");
    if (pts.length < 20) continue;
    for (const r of pts) {
      const win = pts.filter((q) => q.t <= r.t && q.t > r.t - 7 * 86_400_000).map((q) => q[s] as number);
      r[`${s}__avg`] = win.reduce((a, b) => a + b, 0) / win.length;
    }
  }
  return { rows, sources: srcs };
}

const isDense = (rows: Row[], s: string) => rows.some((r) => r[`${s}__avg`] !== undefined);

function Tip({ active, payload, label, unit }: { active?: boolean; payload?: { dataKey: string; value: number; color: string }[]; label?: number; unit: string }) {
  if (!active || !payload?.length || label === undefined) return null;
  return (
    <div className="rounded-xl border border-line bg-surface px-3 py-2 text-xs shadow-soft">
      <p className="mb-1 font-medium">{new Date(label).toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short" })}</p>
      {payload.filter((p) => !p.dataKey.endsWith("__avg")).map((p) => (
        <p key={p.dataKey} className="flex items-center gap-2 text-muted">
          <span className="h-2 w-2 rounded-full" style={{ background: p.color }} />
          {SOURCE_LABEL[p.dataKey] ?? p.dataKey}
          <span className="ml-auto pl-3 font-medium text-ink">{fmt(p.value)} {unit}</span>
        </p>
      ))}
      {payload.filter((p) => p.dataKey.endsWith("__avg")).map((p) => (
        <p key={p.dataKey} className="mt-0.5 text-muted">7-day avg <span className="font-medium text-ink">{fmt(p.value)} {unit}</span></p>
      ))}
    </div>
  );
}

/** Time series with the signature cycle-phase shading behind the lines. */
export function TrendChart({ trend, bands, height = 240, target }: { trend: Trend; bands: Band[]; height?: number; target?: number | null }) {
  const { rows, sources } = mergeBySource(trend);
  if (!rows.length) return <p className="py-10 text-center text-sm text-muted">No data yet</p>;
  const vals = trend.points.map((p) => p.value).concat(target != null ? [target] : []);
  const pad = Math.max(0.5, (Math.max(...vals) - Math.min(...vals)) * 0.15);
  const domain: [number, number] = [Math.floor((Math.min(...vals) - pad) * 2) / 2, Math.ceil((Math.max(...vals) + pad) * 2) / 2];
  const t0 = rows[0].t, t1 = rows[rows.length - 1].t;
  return (
    <div>
      {(sources.length > 1 || sources.some((s) => isDense(rows, s))) && (
        <div className="mb-2 flex gap-4 text-xs text-muted">
          {sources.map((s) => (
            <span key={s} className="inline-flex items-center gap-1.5">
              <span className="h-0.5 w-4 rounded" style={{ background: SOURCE_COLOR[s] }} />
              {SOURCE_LABEL[s] ?? s}{isDense(rows, s) ? " (7-day avg)" : ""}
            </span>
          ))}
        </div>
      )}
      <ResponsiveContainer width="100%" height={height}>
        <LineChart data={rows} margin={{ top: 8, right: 8, bottom: 0, left: -12 }}>
          {bands.map((b, i) => {
            const k = phaseKey(b.phase);
            const x1 = Math.max(day(b.start), t0), x2 = Math.min(day(b.end) + 86_400_000, t1);
            if (x2 <= x1 || k === "follicular" || k === "unknown") return null;
            return <ReferenceArea key={i} x1={x1} x2={x2} fill={PHASES[k].soft} fillOpacity={1} strokeOpacity={0} ifOverflow="hidden" />;
          })}
          <CartesianGrid vertical={false} stroke="var(--line)" strokeDasharray="0" />
          <XAxis dataKey="t" type="number" scale="time" domain={[t0, t1]} tickFormatter={(t) => shortDate(new Date(t).toISOString().slice(0, 10))}
            tickLine={false} axisLine={false} minTickGap={40} />
          <YAxis domain={domain} tickLine={false} axisLine={false} width={44} tickFormatter={(v) => fmt(v)} />
          {target != null && <ReferenceLine y={target} stroke="var(--muted)" strokeDasharray="4 4" label={{ value: `target ${fmt(target)}`, position: "insideTopRight", fill: "var(--muted)", fontSize: 11 }} />}
          <Tooltip content={<Tip unit={trend.unit} />} cursor={{ stroke: "var(--muted)", strokeWidth: 1, strokeDasharray: "3 3" }} />
          {sources.map((s) => {
            const color = SOURCE_COLOR[s] ?? "var(--s1)";
            return isDense(rows, s) ? (
              [
                <Line key={s} dataKey={s} stroke="none" connectNulls legendType="none" isAnimationActive={false}
                  dot={{ r: 2, fill: color, fillOpacity: 0.35, strokeWidth: 0 }} activeDot={{ r: 4, fill: color, strokeWidth: 2, stroke: "var(--surface)" }} />,
                <Line key={`${s}-avg`} dataKey={`${s}__avg`} type="monotone" stroke={color} strokeWidth={2} dot={false}
                  connectNulls activeDot={false} isAnimationActive={false} />,
              ]
            ) : (
              <Line key={s} dataKey={s} type="monotone" stroke={color} strokeWidth={2} connectNulls isAnimationActive={false}
                dot={{ r: 4, strokeWidth: 2, stroke: "var(--surface)", fill: color }} activeDot={{ r: 5, strokeWidth: 2, stroke: "var(--surface)" }} />
            );
          })}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

/** Compact single-series sparkline (no axes). */
export function Sparkline({ trend, height = 48 }: { trend: Trend; height?: number }) {
  const { rows, sources } = mergeBySource(trend);
  const s = sources[0];
  if (!s) return null;
  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={rows} margin={{ top: 4, right: 2, bottom: 4, left: 2 }}>
        <YAxis hide domain={["dataMin - 1", "dataMax + 1"]} />
        <Line dataKey={s} type="monotone" stroke="var(--s1)" strokeWidth={2} dot={false} isAnimationActive={false} />
      </LineChart>
    </ResponsiveContainer>
  );
}

const MACROS = [
  { key: "protein_g", label: "Protein" },
  { key: "carbs_g", label: "Carbs" },
  { key: "fat_g", label: "Fat" },
] as const;

function MacroTip({ active, payload, label }: { active?: boolean; payload?: { payload: NutritionDay }[]; label?: string }) {
  if (!active || !payload?.length || !label) return null;
  const d = payload[0].payload;
  return (
    <div className="rounded-xl border border-line bg-surface px-3 py-2 text-xs shadow-soft">
      <p className="mb-1 font-medium">{shortDate(label)} · {fmt(d.kcal, 0)} kcal</p>
      {MACROS.map((m) => (
        <p key={m.key} className="flex items-center gap-2 text-muted">
          <span className="h-2 w-2 rounded-full" style={{ background: MACRO_COLOR[m.key] }} />
          {m.label}
          <span className="ml-auto pl-3 font-medium text-ink">{fmt(d[m.key], 0)} g</span>
        </p>
      ))}
      <p className="mt-1 text-muted">Fibre <span className="font-medium text-ink">{fmt(d.fiber_g, 0)} g</span></p>
    </div>
  );
}

/** Stacked daily macros in grams (2px surface gaps between segments, rounded top). */
export function MacroChart({ daily, height = 220 }: { daily: NutritionDay[]; height?: number }) {
  if (!daily.length) return <p className="py-10 text-center text-sm text-muted">No meals logged yet</p>;
  return (
    <div>
      <div className="mb-2 flex gap-4 text-xs text-muted">
        {MACROS.map((m) => (
          <span key={m.key} className="inline-flex items-center gap-1.5">
            <span className="h-2.5 w-2.5 rounded-sm" style={{ background: MACRO_COLOR[m.key] }} />
            {m.label}
          </span>
        ))}
      </div>
      <ResponsiveContainer width="100%" height={height}>
        <BarChart data={daily} margin={{ top: 8, right: 4, bottom: 0, left: 0 }} barCategoryGap="28%">
          <CartesianGrid vertical={false} stroke="var(--line)" />
          <XAxis dataKey="date" tickFormatter={shortDate} tickLine={false} axisLine={false} minTickGap={16} />
          <YAxis tickLine={false} axisLine={false} width={44} unit=" g" />
          <Tooltip content={<MacroTip />} cursor={{ fill: "var(--surface-2)" }} />
          {MACROS.map((m, i) => (
            <Bar key={m.key} dataKey={m.key} stackId="m" fill={MACRO_COLOR[m.key]} stroke="var(--surface)" strokeWidth={2}
              radius={i === MACROS.length - 1 ? [4, 4, 0, 0] : [0, 0, 0, 0]} isAnimationActive={false} />
          ))}
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

/** Single-metric daily bars vs a target line (e.g. protein or fibre). */
export function TargetBars({ daily, field, target, color = "var(--s1)", height = 160 }: { daily: NutritionDay[]; field: keyof NutritionDay; target: number; color?: string; height?: number }) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={daily} margin={{ top: 12, right: 4, bottom: 0, left: 0 }} barCategoryGap="30%">
        <CartesianGrid vertical={false} stroke="var(--line)" />
        <XAxis dataKey="date" tickFormatter={shortDate} tickLine={false} axisLine={false} minTickGap={16} />
        <YAxis tickLine={false} axisLine={false} width={44} unit=" g" domain={[0, (max: number) => Math.ceil(Math.max(max, target) * 1.15)]} />
        <Tooltip formatter={(v) => [`${fmt(Number(v), 0)} g`, String(field).replace("_g", "")]} labelFormatter={(l) => shortDate(String(l))}
          contentStyle={{ borderRadius: 12, border: "1px solid var(--line)", background: "var(--surface)", fontSize: 12 }} cursor={{ fill: "var(--surface-2)" }} />
        <ReferenceLine y={target} stroke="var(--ink)" strokeOpacity={0.5} strokeDasharray="4 4" />
        <Bar dataKey={field as string} fill={color} radius={[4, 4, 0, 0]} isAnimationActive={false} />
      </BarChart>
    </ResponsiveContainer>
  );
}
