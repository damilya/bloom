"use client";

import { motion } from "framer-motion";
import { ArrowDownRight, ArrowUpRight, Minus } from "lucide-react";
import { PHASES, cx, fmt, phaseKey } from "@/lib/format";
import type { Cycle } from "@/lib/api";

export function Card({ className, children, delay = 0 }: { className?: string; children: React.ReactNode; delay?: number }) {
  return (
    <motion.section
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.45, delay, ease: [0.22, 1, 0.36, 1] }}
      className={cx("card min-w-0 p-5 sm:p-6", className)}
    >
      {children}
    </motion.section>
  );
}

export function CardTitle({ children, right }: { children: React.ReactNode; right?: React.ReactNode }) {
  return (
    <div className="mb-4 flex flex-wrap items-center justify-between gap-x-3 gap-y-2">
      <h2 className="text-[13px] font-medium uppercase tracking-[0.08em] text-muted">{children}</h2>
      {right}
    </div>
  );
}

export function PageHeader({ title, subtitle, right }: { title: React.ReactNode; subtitle?: React.ReactNode; right?: React.ReactNode }) {
  return (
    <header className="mb-8 flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 className="font-serif text-3xl leading-tight tracking-tight sm:text-4xl">{title}</h1>
        {subtitle && <p className="mt-1.5 text-muted">{subtitle}</p>}
      </div>
      {right}
    </header>
  );
}

/** Lower-is-better metrics show a decrease in sage (good) instead of terracotta. */
const LOWER_IS_BETTER = new Set(["weight_kg", "body_fat_pct", "fat_mass_kg", "visceral_fat", "resting_hr", "metabolic_age"]);

export function Kpi({
  label, value, unit, delta, metric, sub, delay,
}: { label: string; value: number | null | undefined; unit?: string; delta?: number | null; metric?: string; sub?: string; delay?: number }) {
  const good = delta == null || delta === 0 ? null : LOWER_IS_BETTER.has(metric ?? "") ? delta < 0 : delta > 0;
  const Icon = delta == null || delta === 0 ? Minus : delta > 0 ? ArrowUpRight : ArrowDownRight;
  return (
    <Card delay={delay} className="!p-5">
      <p className="text-[13px] text-muted">{label}</p>
      <p className="mt-2 font-serif text-[1.75rem] leading-none tracking-tight sm:text-[2.1rem]">
        {fmt(value)}
        {unit && <span className="ml-1 font-sans text-base text-muted">{unit}</span>}
      </p>
      <div className="mt-3 flex flex-wrap items-center gap-1.5 text-[13px]">
        {delta != null && (
          <span className={cx("inline-flex items-center gap-0.5 rounded-full px-2 py-0.5", good === null ? "bg-surface-2 text-muted" : good ? "bg-sage-soft text-sage" : "bg-terracotta-soft text-terracotta")}>
            <Icon size={13} />
            {fmt(Math.abs(delta))} {unit}
          </span>
        )}
        <span className="text-muted">{sub ?? (delta != null ? "vs last week" : "")}</span>
      </div>
    </Card>
  );
}

export function PhasePill({ cycle, large }: { cycle?: Cycle; large?: boolean }) {
  if (!cycle?.known) return <span className="rounded-full bg-surface-2 px-3 py-1 text-sm text-muted">Cycle: no data</span>;
  const k = phaseKey(cycle.phase);
  const p = PHASES[k];
  return (
    <span
      className={cx("inline-flex items-center gap-2 rounded-full border border-line bg-surface font-medium", large ? "px-4 py-2 text-[15px]" : "px-3 py-1 text-sm")}
      title={cycle.note}
    >
      <PhaseGlyph color={p.color} />
      {p.label} · day {cycle.cycle_day}
      {cycle.confidence === "low" && <span className="font-normal text-muted">(estimate)</span>}
    </span>
  );
}

export function PhaseGlyph({ color, size = 14 }: { color: string; size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" aria-hidden>
      <circle cx="8" cy="8" r="7" fill="none" stroke={color} strokeWidth="1.6" />
      <path d="M8 1a7 7 0 0 1 0 14z" fill={color} />
    </svg>
  );
}

export function PhaseLegend() {
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted">
      {(["menstrual", "follicular", "ovulatory", "luteal"] as const).map((k) => (
        <span key={k} className="inline-flex items-center gap-1.5">
          <span className="h-2.5 w-4 rounded-sm" style={{ background: PHASES[k].soft, outline: `1px solid ${PHASES[k].color}33` }} />
          {PHASES[k].label}
        </span>
      ))}
    </div>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={cx("skeleton", className)} />;
}

export function Empty({ title, children }: { title: string; children?: React.ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-line px-6 py-10 text-center">
      <p className="font-serif text-lg">{title}</p>
      {children && <div className="mt-1 max-w-sm text-sm text-muted">{children}</div>}
    </div>
  );
}

export function ProgressBar({ pct, color = "var(--sage)" }: { pct: number; color?: string }) {
  return (
    <div className="h-2 w-full overflow-hidden rounded-full bg-surface-2">
      <motion.div
        className="h-full rounded-full"
        style={{ background: color }}
        initial={{ width: 0 }}
        animate={{ width: `${Math.max(2, Math.min(100, pct))}%` }}
        transition={{ duration: 0.9, ease: [0.22, 1, 0.36, 1] }}
      />
    </div>
  );
}

export function Button({ children, variant = "primary", className, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "ghost" | "danger" | "soft" }) {
  const styles = {
    primary: "bg-ink text-bg hover:opacity-90",
    soft: "bg-sage-soft text-ink hover:brightness-95",
    ghost: "border border-line bg-surface text-ink hover:bg-surface-2",
    danger: "bg-terracotta-soft text-terracotta hover:brightness-95",
  }[variant];
  return (
    <button
      {...props}
      className={cx("inline-flex items-center justify-center gap-2 rounded-full px-4 py-2 text-sm font-medium transition disabled:cursor-not-allowed disabled:opacity-50", styles, className)}
    >
      {children}
    </button>
  );
}

export function Offline({ message }: { message: string }) {
  return (
    <div className="mx-auto mt-20 max-w-md">
      <Empty title="Can't reach the backend">
        <p>{message}</p>
        <p className="mt-2">
          Start it with <code className="rounded bg-surface-2 px-1">make dev</code> (or <code className="rounded bg-surface-2 px-1">docker compose up</code>).
        </p>
      </Empty>
    </div>
  );
}
