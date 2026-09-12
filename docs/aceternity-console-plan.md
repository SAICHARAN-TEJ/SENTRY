# SENTRY Console × Aceternity UI — Integration Plan

Scope: the operator console (`index.html` + `js/*.js`) only. The Python backend, worker, and validation engine are untouched. Produced with the `aceternity-ui` skill loaded and grounded in the actual console code (5 tabs, canvas-based, Three.js globe, static vanilla JS, no React, no build step).

---

## 1. The stack gap, stated plainly

| Aceternity requires | SENTRY has today |
|---|---|
| Next.js 13+ (App Router) | Static `index.html`, served by `python -m http.server` |
| React 16.8+ | No framework; 3.3k lines of vanilla JS |
| Tailwind CSS v4 | Hand-rolled CSS with custom properties |
| `motion` (Framer Motion) | Three.js for the globe; no React animation lib |
| shadcn CLI install | Plain `<script src>` tags |

Aceternity components are copy-paste React/TSX with Tailwind classes — they cannot drop into the current console as-is. There is no intermediary that keeps this console vanilla.

## 2. The decision to make (one of two roads)

**Road A — Static console stays, targeted borrowings.** No React. Aceternity is used as a *design reference*: re-implement the 3–4 effects the console actually needs (spotlight header, animated tab underline, loading-screen beams) as ~250 lines of vanilla CSS/JS. Cost stays near zero; the two native canvases (Three.js globe, SRM map) remain untouched; deployment stays "copy files."

**Road B — Next.js port of the console.** Create a `console/` Next.js app (App Router, Tailwind v4, shadcn init + `@aceternity` registry), port the five tabs into React, and install real Aceternity components. Real animated components and real dark mode; the cost is a build toolchain, a React rewrite of ~3.3k lines of working code, and an ESM import-map swap for the Three.js globe (react-three-fiber or a `dynamic(ssr:false)` wrapper).

Both roads keep the backend API contract (`js/api.js`'s real-client routes) — the API layer is portable either way.

**Recommendation: Road A.** The console's identity is instrument-like: 3D globe, split-slider compare, JSON trace, chips — motion should support *reading data*, not compete with it. Aceternity's effects are strongest in marketing surfaces; the operator console needs 4 specific effects, not 100+ components. If a separate public-facing site (demo page, SIH jury page, docs) materializes, that is where Road B / full Aceternity pays off — on a fresh Next.js app, not a port of this console.

## 3. Component mapping (verified against the console)

| Console surface | Aceternity reference | Fit | Notes |
|---|---|---|---|
| Header status chips (Sim/Live, job state) | **Spotlight** | High | One CSS conic-gradient sweep on the header; cheap and instrument-like |
| Tab bar (01 Map / 02 Alerts / 03 Metrics / 04 Trace) | **Tabs** (animated underline via `motion` layoutId) | Medium | Vanilla equivalent: one shared underline element animating `transform: translateX/width` on tab switch (~30 lines) |
| Map split-slider ("Drag to Compare") | **Compare** | High (already exists) | Console already has its own split-slider (`sliderLine`/`sliderHandle`) — Aceternity's adds nothing functional; restyle at most |
| Loading screen (`INITIALIZING…`) | **Background Beams** / **Vortex** | Medium | 2-second window; a slow beam sweep would read well; only worth it if the load path is kept |
| Toast region | Slide-in banners | Low | Current `toast-ok`/`toast-warn` slide-ins are fine; skip |
| Dossier modal | **Animated Modal** | Low | Current modal is functional; Aceternity's is an `AnimatePresence` React pattern; skip |
| Alerts table | (none) | — | Tables are information-dense; no Aceternity analog adds value |
| Metrics charts | (none) | — | Already canvas-rendered line/bar/reliability charts |

## 4. Road A implementation sketch (if approved)

Files touched: `index.html` (2 elements), one new CSS file (~200 lines), `js/app.js` (2 small hooks).

1. **Spotlight header** — `header.console-header::before` with an animated conic-gradient sweep, `pointer-events: none`, disabled under `prefers-reduced-motion` (the console already respects that setting in `app.js`).
2. **Animated tab underline** — a single `.tab-underline` div; on `data-tab` switch, JS reads the active button's `offsetLeft/offsetWidth` and animates `transform`. Works with the existing `role="tab"`/`aria-selected` markup.
3. **Loading screen beams** — CSS-only: two skewed gradient bars translating across `#loadingScreen`, removed by the existing `.hidden` hook.
4. **(Optional) card hover polish** — subtle `translateY(-2px)` + shadow on `.panel` cards; no JS.

Nothing else changes: no dependency additions, no build step, deployment unchanged (static copy). No packages are added, so the skill's supply-chain guidance (postinstall blocking, cooldowns) does not apply.

## 5. Road B sketch (for the record)

1. `cd console && bunx create-next-app@latest` (TS, App Router, Tailwind v4, `@/*` alias).
2. `bunx --bun shadcn@latest init` (new-york style, zinc base, CSS variables), then add `"registries": {"@aceternity": "https://ui.aceternity.com/registry/{name}.json"}` to `components.json`.
3. `bunx shadcn@latest add @aceternity/background-beams @aceternity/spotlight @aceternity/compare` (plus `motion clsx tailwind-merge` if manual).
4. Port order: API client (thin fetch wrapper → `lib/api.ts`), tab shell, Map tab (globe via `dynamic(() => import(...), { ssr: false })` wrapping the existing `three-env.js` as a client module), then Alerts/Metrics/Trace.
5. Keep the static console as a fallback until parity; the FastAPI CORS allowlist already supports localhost dev origins.

Rough cost: the React rewrite of the map / compare / pixel-inspector interactions is the long pole — realistically the largest single piece of frontend work in this repo so far.

## 6. Security notes (from the skill)

Any Aceternity/shadcn install path runs remote code (`create-next-app`, `shadcn init`, `shadcn add`). If Road B ever runs: pin versions, consider `npm config set ignore-scripts true` during scaffolding, prefer `bun` (no postinstall scripts by default), and vet `motion`, `clsx`, `tailwind-merge` before committing a lockfile. None of this applies to Road A (no packages added).

## 7. What was NOT done

No code changes — plan document only, per your choice. `index.html`, `js/*.js`, and the backend are untouched since commit `2b4360f`.
