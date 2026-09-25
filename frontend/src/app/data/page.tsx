"use client";

import { AlertTriangle, CheckCircle2, Circle, ImageUp, Link2, RefreshCw, Scale, Smartphone, Upload, Dumbbell } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { API, getJSON, type Status } from "@/lib/api";
import { cx, fmt } from "@/lib/format";
import { Button, Card, CardTitle, Offline, PageHeader, Skeleton } from "@/components/ui";

type FoodItem = { meal: string; name: string; kcal: number | null; carbs_g: number | null; fat_g: number | null; protein_g: number | null; fiber_g: number | null };
type Extraction = { date: string; items: FoodItem[]; unreadable: boolean; notes: string; checks: { level: string; item: string; msg: string }[] };

function Dropzone({ accept, label, hint, onFile, busy }: { accept: string; label: string; hint: string; onFile: (f: File) => void; busy?: boolean }) {
  const [over, setOver] = useState(false);
  const ref = useRef<HTMLInputElement>(null);
  return (
    <div
      onDragOver={(e) => { e.preventDefault(); setOver(true); }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => { e.preventDefault(); setOver(false); const f = e.dataTransfer.files[0]; if (f) onFile(f); }}
      onClick={() => ref.current?.click()}
      className={cx("flex cursor-pointer flex-col items-center justify-center rounded-2xl border-2 border-dashed px-4 py-8 text-center transition",
        over ? "border-s1 bg-sage-soft" : "border-line hover:border-muted", busy && "pointer-events-none opacity-60")}>
      <Upload size={22} className="text-muted" />
      <p className="mt-2 text-sm font-medium">{busy ? "Processing…" : label}</p>
      <p className="mt-0.5 text-xs text-muted">{hint}</p>
      <input ref={ref} type="file" accept={accept} hidden onChange={(e) => { const f = e.target.files?.[0]; if (f) onFile(f); e.target.value = ""; }} />
    </div>
  );
}

function Dot({ ok, label }: { ok: boolean; label: string }) {
  return (
    <li className="flex items-center gap-2 text-sm">
      {ok ? <CheckCircle2 size={16} className="text-s1" /> : <Circle size={16} className="text-muted" />}
      <span className={ok ? "" : "text-muted"}>{label}</span>
    </li>
  );
}

function DataInner() {
  const params = useSearchParams();
  const [status, setStatus] = useState<Status | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(params.get("withings") === "connected" ? `Withings connected — imported ${params.get("n")} measurements.` : null);
  const [busy, setBusy] = useState<string | null>(null);
  const [food, setFood] = useState<Extraction | null>(null);
  const [preview, setPreview] = useState<string | null>(null);

  const refresh = useCallback(() => getJSON<Status>("/api/status").then(setStatus).catch((e) => setErr(e.message)), []);
  useEffect(() => { refresh(); }, [refresh]);

  const upload = async (path: string, f: File, key: string) => {
    setBusy(key); setMsg(null);
    try {
      const fd = new FormData();
      fd.append("file", f);
      const r = await fetch(`${API}${path}`, { method: "POST", body: fd });
      const j = await r.json();
      if (!r.ok) throw new Error(j.detail ?? r.statusText);
      return j;
    } catch (e) {
      setMsg(`⚠️ ${(e as Error).message}`);
      return null;
    } finally {
      setBusy(null);
    }
  };

  const apple = async (f: File) => {
    const j = await upload("/api/upload/apple-health", f, "apple");
    if (!j) return;
    setBusy("apple");
    setMsg("Parsing Apple Health export… large exports take a minute.");
    for (;;) {
      await new Promise((r) => setTimeout(r, 2000));
      const s = await getJSON<{ status: string; result?: Record<string, number>; error?: string }>(`/api/jobs/${j.job_id}`);
      if (s.status === "done") { setMsg(`Apple Health imported: ${s.result?.workouts} workouts, ${s.result?.cycle_days} cycle days, ${s.result?.measurements} daily measurements.`); break; }
      if (s.status === "error") { setMsg(`⚠️ ${s.error}`); break; }
    }
    setBusy(null); refresh();
  };

  const json = async (f: File) => {
    const j = await upload("/api/upload/json", f, "json");
    if (!j) return;
    const files = (j.files ?? []) as { file: string; measurements?: number; workouts?: number; error?: string }[];
    const detail = files
      .map((x) => (x.error ? `${x.file}: ⚠️ ${x.error}` : `${x.file}: ${x.measurements} values, ${x.workouts} workouts${!x.measurements && !x.workouts ? " (nothing recognised)" : ""}`))
      .join(" · ");
    setMsg(`Imported ${j.measurements} body-composition values and ${j.workouts} workouts from ${files.length} file${files.length === 1 ? "" : "s"}. ${detail}`);
    refresh();
  };

  const foodvisor = async (f: File) => {
    setPreview(URL.createObjectURL(f));
    const j = await upload("/api/upload/foodvisor", f, "food");
    if (j) setFood(j);
  };

  const confirmFood = async () => {
    if (!food) return;
    const r = await fetch(`${API}/api/foodvisor/confirm`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ date: food.date, items: food.items }) });
    const j = await r.json();
    setMsg(`Saved ${j.saved} food items for ${food.date}.`); setFood(null); setPreview(null); refresh();
  };

  const post = async (path: string, key: string, ok: (j: Record<string, number>) => string) => {
    setBusy(key); setMsg(null);
    try {
      const r = await fetch(`${API}${path}`, { method: "POST" });
      const j = await r.json();
      if (!r.ok) throw new Error(j.detail);
      setMsg(ok(j)); refresh();
    } catch (e) { setMsg(`⚠️ ${(e as Error).message}`); } finally { setBusy(null); }
  };

  if (err) return <Offline message={err} />;
  if (!status) return <Skeleton className="mx-auto h-96 max-w-5xl" />;

  return (
    <div className="mx-auto max-w-5xl">
      <PageHeader title="Your data" subtitle="Connect your scale, drop in exports and screenshots — everything lands on one timeline." />
      {msg && <div className="mb-4 rounded-2xl border border-line bg-surface px-4 py-3 text-sm">{msg}</div>}

      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardTitle right={<Scale size={18} className="text-muted" />}>Withings smart scale</CardTitle>
          <p className="text-sm text-muted">Live via the Withings API (OAuth). Your scale syncs to Withings’ cloud; Bloom reads weight, fat %, muscle, water and bone mass from there.</p>
          <ul className="mt-4 space-y-1.5">
            <Dot ok={status.withings.configured} label="API credentials in .env" />
            <Dot ok={status.withings.connected} label="Account connected" />
          </ul>
          <div className="mt-5 flex flex-wrap gap-2">
            <a href={`${API}/withings/connect`} className={cx("inline-flex items-center gap-2 rounded-full bg-ink px-4 py-2 text-sm font-medium text-bg", !status.withings.configured && "pointer-events-none opacity-40")}>
              <Link2 size={15} />{status.withings.connected ? "Reconnect" : "Connect Withings"}
            </a>
            <Button variant="ghost" disabled={!status.withings.connected || busy === "withings"} onClick={() => post("/api/withings/sync", "withings", (j) => `Synced ${j.measurements} Withings measurements.`)}>
              <RefreshCw size={15} className={busy === "withings" ? "animate-spin" : ""} />Sync now
            </Button>
          </div>
        </Card>

        <Card>
          <CardTitle right={<Smartphone size={18} className="text-muted" />}>Apple Health</CardTitle>
          <p className="mb-4 text-sm text-muted">iPhone → Health → profile picture → <i>Export All Health Data</i>. Brings in Apple Watch workouts, cycle tracking, sleep, resting HR and steps.</p>
          <Dropzone accept=".zip,.xml" label="Drop export.zip" hint="or click to choose · processed on your server" onFile={apple} busy={busy === "apple"} />
        </Card>

        <Card>
          <CardTitle right={<Dumbbell size={18} className="text-muted" />}>Stadium Kinetix & Tanita</CardTitle>
          <p className="mb-4 text-sm text-muted">JSON exports from the Kinetix app (gym sessions and Tanita body-composition scans: visceral fat, BMR, metabolic age). Zip several files together to import them at once.</p>
          <Dropzone accept=".json,.zip,application/json,application/zip" label="Drop a .zip of exports or a single .json" hint="put all Kinetix / Tanita JSON files in one ZIP" onFile={json} busy={busy === "json"} />
        </Card>

        <Card>
          <CardTitle right={<ImageUp size={18} className="text-muted" />}>Foodvisor screenshot</CardTitle>
          <p className="mb-4 text-sm text-muted">No Foodvisor API exists, so Bloom reads your screenshot with a vision model, checks the numbers add up, and asks you to confirm.</p>
          {!food && <Dropzone accept="image/*" label="Drop a screenshot" hint="daily diary or meal detail screen" onFile={foodvisor} busy={busy === "food"} />}
          {food && (
            <div className="flex gap-4">
              {preview && (
                // eslint-disable-next-line @next/next/no-img-element -- local blob: preview, nothing to optimise
                <img src={preview} alt="screenshot" className="hidden h-56 rounded-xl border border-line object-cover sm:block" />
              )}
              <div className="min-w-0 flex-1">
                {food.unreadable ? <p className="text-sm text-terracotta">This doesn’t look like a food log.</p> : (
                  <>
                    <label className="text-xs text-muted">Date <input type="date" value={food.date} onChange={(e) => setFood({ ...food, date: e.target.value })} className="ml-1 rounded-lg border border-line bg-surface px-2 py-0.5 text-ink" /></label>
                    <ul className="mt-2 max-h-40 divide-y divide-line overflow-y-auto text-sm">
                      {food.items.map((it, i) => (
                        <li key={i} className="py-1.5">
                          <span className="font-medium">{it.name}</span> <span className="text-xs capitalize text-muted">· {it.meal}</span>
                          <p className="text-xs text-muted">{fmt(it.kcal, 0)} kcal · P {fmt(it.protein_g, 0)} · C {fmt(it.carbs_g, 0)} · F {fmt(it.fat_g, 0)} · Fibre {fmt(it.fiber_g, 0)}</p>
                        </li>
                      ))}
                    </ul>
                    <ul className="mt-2 space-y-1">
                      {food.checks.map((c, i) => (
                        <li key={i} className={cx("flex items-start gap-1.5 text-xs", c.level === "ok" ? "text-s1" : "text-terracotta")}>
                          {c.level === "ok" ? <CheckCircle2 size={13} className="mt-px" /> : <AlertTriangle size={13} className="mt-px" />}{c.msg}
                        </li>
                      ))}
                    </ul>
                  </>
                )}
                <div className="mt-3 flex gap-2">
                  {!food.unreadable && (
                    <Button onClick={confirmFood} disabled={!food.items.length}>
                      {food.items.length ? `Save ${food.items.length} item${food.items.length === 1 ? "" : "s"} to my log` : "Nothing to save"}
                    </Button>
                  )}
                  <Button variant="ghost" onClick={() => { setFood(null); setPreview(null); }}>Discard</Button>
                </div>
              </div>
            </div>
          )}
        </Card>
      </div>

      <Card className="mt-4">
        <CardTitle>System</CardTitle>
        <div className="grid gap-6 md:grid-cols-3">
          <ul className="space-y-1.5">
            <Dot ok={status.openai} label="OpenAI API key" />
            <Dot ok={status.langsmith} label="LangSmith tracing" />
            <Dot ok={status.research_index} label="Research index built" />
          </ul>
          <div className="text-sm">
            <p className="text-muted">Models</p>
            <p>{status.models.primary} · {status.models.fast}</p>
            <p className="mt-2 text-muted">Spend today</p>
            <p>${fmt(status.spent_today_usd, 3)} of ${status.budget_usd} budget</p>
            <p className="mt-2 text-muted">Semantic cache</p>
            <p>{status.cache.entries} entries · {status.cache.hits} hits</p>
          </div>
          <div className="text-sm">
            <p className="text-muted">Records</p>
            <p>{Object.entries(status.data).map(([k, v]) => `${v} ${k.replace("_", " ")}`).join(" · ")}</p>
            <Button variant="ghost" className="mt-3" disabled={busy === "seed"} onClick={() => post("/api/demo/seed", "seed", () => "Demo data loaded (replaces current data).")}>Load demo data</Button>
          </div>
        </div>
      </Card>
    </div>
  );
}

export default function DataPage() {
  return <Suspense><DataInner /></Suspense>;
}
