# Bloom frontend

Next.js 15 (App Router) · Tailwind v4 · Recharts · Framer Motion. "Calm wellness" design system in `src/app/globals.css`;
the chart series palette (`--s1..--s3`) was validated for color-vision deficiency and contrast in light and dark mode.

```bash
npm install
NEXT_PUBLIC_API_URL=http://localhost:8000 npm run dev   # http://localhost:3000
```

Pages: `/` Today · `/trends` · `/nutrition` · `/coach` (SSE chat, citations drawer, goal approval) · `/goals` · `/data` (uploads, Withings OAuth, system status).
