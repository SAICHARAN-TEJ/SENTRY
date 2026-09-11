# Retrofitting 3D into an existing site

Everything in `three-core.md`, `r3f-drei.md`, `gsap-scroll.md`, and `performance.md` applies unchanged — Three.js doesn't care if the DOM around it is new or ten years old. What changes on a retrofit is the *integration strategy* and the constraints you're not allowed to break.

## Step 1 — Check the stack before anything else

- **Already React** (including Vite/Next, and specifically Lovable's default `vite_react_shadcn_ts` stack) → R3F drops in directly, `<Canvas>` is just another component.
- **Not React** (plain HTML/JS, Vue, WordPress, etc.) → use vanilla Three.js, not R3F. Mount it into a specific container element, don't fight the existing framework for control of the DOM.

## Step 2 — Pick *where* the 3D pays off, don't blanket the whole site

A full-site 3D re-skin is rarely the right call on a retrofit. Look for the page/section that's structurally suited to it:

- A **hub / navigation screen** (map, world, dashboard of areas) — 3D replaces what would otherwise be a grid of cards or links, and the spatial metaphor does real work instead of being decoration.
- A **hero section** — bounded, doesn't touch the rest of the site's layout or content.
- Content-heavy, form-heavy, or data-table screens (quiz questions, checkout, settings) are usually *not* good 3D candidates — the interaction cost of WebGL competes with the interaction the user actually came to do. Keep those flat, fast, and accessible; scope the 3D to where it's earning its keep.

## Step 3 — Don't regress what already works

This is the part a greenfield build doesn't have to think about:

- **Existing routes/state/logic stay untouched.** The 3D layer is additive — mount it in a new route/component, don't rewrite working screens to fit it.
- **Accessibility of existing content can't get worse.** If the site has forms, quizzes, or any keyboard/screen-reader-dependent flow, the 3D layer must not sit on top of or intercept that interaction. Keep WebGL to presentational/navigational screens, keep interactive/input screens semantic HTML.
- **First-load budget.** An existing site already has a performance baseline (fonts, analytics, existing bundle). A WebGL scene added on top is a new, often large chunk of JS + GPU work — lazy-load it (route-level code splitting, `React.lazy` + `Suspense` around the `Canvas`) so pages that don't use it don't pay for it. This matters more on a retrofit than a greenfield build, because a greenfield build's whole budget is planned around the 3D from day one; a retrofit is stacking cost onto an existing bill.
- **Mobile fallback is not optional here either** — see `patterns-and-antipatterns.md` — but on a retrofit you also have real analytics/traffic on the existing site to check before assuming desktop-first is fine.

## Step 4 — Integration path depends on how the project is edited

**Platform-built projects with an AI agent in the loop (e.g. Lovable, `vite_react_shadcn_ts` stack):**
Two viable paths, not interchangeable:
1. **Through the platform's own agent** (e.g. Lovable's `send_message`) — stays inside the platform's edit history/versioning, respects its existing component conventions (shadcn primitives, Tailwind config) automatically. Paste this skill's relevant reference content into the instruction so the platform's agent has the same grounding instead of improvising Three.js from general knowledge.
2. **Direct edit via a synced GitHub repo** — clone locally, edit with full control using this skill's patterns directly, push; the platform re-syncs on next pull. Gives more precision (exact `InstancedMesh`/`ScrollTrigger` control) but can diverge from the platform's own edit history if both sides edit concurrently — pick one channel per work session, don't interleave them.

**Traditional codebase (no AI-platform in the loop):** just a normal PR — build the 3D component/route, review, merge.

## Retrofit-specific checklist before starting

1. Confirm the stack (React or not) — decides R3F vs vanilla Three.js.
2. Pick the *one* screen/section where 3D adds real value — resist "the whole site."
3. Confirm the integration channel (platform agent vs direct repo edit) and stick to it for the session.
4. Plan the lazy-load boundary so non-3D pages don't inherit the bundle cost.
5. Identify anything interactive/accessible on the target screen that must keep working unchanged.
