export const PHASES: Record<string, { label: string; color: string; soft: string; hint: string }> = {
  menstrual: { label: "Menstrual", color: "var(--rose)", soft: "rgba(216,167,160,0.28)", hint: "Rest if needed — train by feel" },
  follicular: { label: "Follicular", color: "var(--sage)", soft: "rgba(124,154,130,0.10)", hint: "Energy often rising" },
  ovulatory: { label: "Ovulatory", color: "var(--sand)", soft: "rgba(227,201,160,0.30)", hint: "Around ovulation" },
  luteal: { label: "Luteal", color: "var(--plum)", soft: "rgba(216,167,160,0.12)", hint: "Fuel well, prioritise sleep" },
  unknown: { label: "Unknown", color: "var(--muted)", soft: "transparent", hint: "" },
};

export const METRIC_LABEL: Record<string, string> = {
  weight_kg: "Weight",
  body_fat_pct: "Body fat",
  muscle_mass_kg: "Muscle mass",
  fat_mass_kg: "Fat mass",
  water_pct: "Body water",
  visceral_fat: "Visceral fat",
  bmr_kcal: "BMR",
  metabolic_age: "Metabolic age",
  resting_hr: "Resting HR",
  hrv_ms: "HRV",
  sleep_hours: "Sleep",
  steps: "Steps",
  bone_mass_kg: "Bone mass",
  hydration_kg: "Hydration",
};

export const SOURCE_LABEL: Record<string, string> = {
  withings: "Withings",
  tanita: "Tanita · Kinetix",
  apple_health: "Apple Health",
  kinetix: "Kinetix",
  foodvisor_vision: "Foodvisor",
};

/** Fixed categorical order (never cycled): s1 → s2 → s3. Validated for CVD + contrast in both themes. */
export const SOURCE_COLOR: Record<string, string> = {
  withings: "var(--s1)",
  tanita: "var(--s2)",
  apple_health: "var(--s3)",
};
export const MACRO_COLOR = { protein_g: "var(--s1)", carbs_g: "var(--s2)", fat_g: "var(--s3)" } as const;

export function phaseKey(phase?: string) {
  if (!phase) return "unknown";
  const p = phase.toLowerCase();
  return (Object.keys(PHASES).find((k) => p.startsWith(k)) ?? "unknown") as keyof typeof PHASES;
}

export const fmt = (v: number | null | undefined, d = 1) =>
  v === null || v === undefined || Number.isNaN(v) ? "—" : v.toLocaleString("en-GB", { maximumFractionDigits: d, minimumFractionDigits: 0 });

export const shortDate = (iso: string) =>
  new Date(iso + (iso.length === 10 ? "T00:00:00" : "")).toLocaleDateString("en-GB", { day: "numeric", month: "short" });

export const weekday = (iso: string) => new Date(iso + "T00:00:00").toLocaleDateString("en-GB", { weekday: "short" });

export function greeting() {
  const h = new Date().getHours();
  return h < 12 ? "Good morning" : h < 18 ? "Good afternoon" : "Good evening";
}

export const cx = (...c: (string | false | null | undefined)[]) => c.filter(Boolean).join(" ");
