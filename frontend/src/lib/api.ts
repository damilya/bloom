export const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type Point = { date: string; source: string; value: number };
export type Trend = {
  metric: string;
  unit: string;
  days: number;
  points: Point[];
  summary: Record<string, { first: Point; last: Point; n: number; change: number }>;
};
export type Band = { phase: string; start: string; end: string };
export type Cycle = {
  known: boolean;
  cycle_day?: number;
  phase?: string;
  confidence?: string;
  avg_cycle_len?: number;
  expected_next_period?: string;
  irregular?: boolean;
  note?: string;
  message?: string;
};
export type Latest = Record<string, { value: number; date: string; source: string; unit: string; delta_7d: number | null }>;
export type NutritionDay = { date: string; kcal: number; carbs_g: number; fat_g: number; protein_g: number; fiber_g: number };
export type Nutrition = {
  days_logged: number;
  daily: NutritionDay[];
  average: Partial<NutritionDay> & { pct_kcal?: { carbs: number; protein: number; fat: number } };
  targets: { protein_g: number; fiber_g: number; basis: string };
};
export type Workout = {
  id: number;
  start_ts: string;
  source: string;
  type: string;
  duration_min: number;
  kcal: number | null;
  distance_km: number | null;
  avg_hr: number | null;
  details: { name?: string; exercises?: { name: string; sets: number; reps: number; kg: number }[] };
};
export type Goal = {
  id: number;
  title: string;
  metric: string | null;
  baseline_value: number | null;
  target_value: number | null;
  unit: string | null;
  deadline: string | null;
  weekly_plan: string[];
  rationale: string | null;
  status: string;
  created_at: string;
  progress: { current: number; baseline: number; pct: number } | null;
};
export type WeatherDay = { date: string; tmax: number; tmin: number; precip_mm: number; summary: string; weather_code: number };
export type Dashboard = {
  user: string;
  today: string;
  latest: Latest;
  cycle: Cycle;
  phase_bands: Band[];
  trends: Record<string, Trend>;
  vitals: Record<string, Trend>;
  nutrition: Nutrition;
  workouts: { total: number; per_week: number; by_type: Record<string, { count: number; minutes: number }>; items: Workout[] };
  goals: Goal[];
  weather: { days: WeatherDay[] };
};
export type Status = {
  openai: boolean;
  withings: { configured: boolean; connected: boolean; last_measurement: string | null };
  research_index: boolean;
  langsmith: boolean;
  data: Record<string, number>;
  spent_today_usd: number;
  budget_usd: number;
  cache: { entries: number; hits: number };
  models: Record<string, string>;
};

export async function getJSON<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(`${API}${path}`, { cache: "no-store", ...init });
  if (!r.ok) {
    let detail = r.statusText;
    try {
      detail = (await r.json()).detail ?? detail;
    } catch {}
    throw new Error(detail);
  }
  return r.json();
}

export type SSEHandler = (event: string, data: unknown) => void;

/** POST + Server-Sent Events reader (EventSource can't POST). */
export async function postSSE(path: string, body: unknown, onEvent: SSEHandler, signal?: AbortSignal) {
  const r = await fetch(`${API}${path}`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });
  if (!r.ok || !r.body) {
    let detail = r.statusText;
    try {
      detail = (await r.json()).detail ?? detail;
    } catch {}
    throw new Error(detail);
  }
  const reader = r.body.getReader();
  const dec = new TextDecoder();
  let buf = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true }).replace(/\r\n/g, "\n");
    let idx;
    while ((idx = buf.indexOf("\n\n")) >= 0) {
      const raw = buf.slice(0, idx);
      buf = buf.slice(idx + 2);
      let event = "message";
      const data: string[] = [];
      for (const line of raw.split("\n")) {
        if (line.startsWith("event:")) event = line.slice(6).trim();
        else if (line.startsWith("data:")) data.push(line.slice(5).replace(/^ /, ""));
      }
      if (!data.length) continue;
      try {
        onEvent(event, JSON.parse(data.join("\n")));
      } catch {
        onEvent(event, data.join("\n"));
      }
    }
  }
}
