# Hero dressing patterns (non-Three.js layer)

Source: distilled from three real production prompts (CodeNest, Sentinel AI, mėntality — dated 2026-07-16/17, provided by the user), not from official docs like the other reference files in this skill. Treat this file's claims as "observed working patterns," not spec-verified API behavior — cross-check CSS feature support (`mask-composite`, `backdrop-filter`) against caniuse if it matters for the target audience.

This file covers the **skin** around a hero section: background media, glass cards, entrance motion, fluid type. It does not require Three.js/R3F — it applies whether the hero background is a hand-built R3F scene (rest of this skill), an embedded pre-built 3D scene (Spline), or plain video. Use `three-core.md`/`r3f-drei.md` when the 3D itself needs to be built or debugged; use this file for what wraps around any of those.

## Spline vs hand-rolled R3F — pick one deliberately

All three source prompts that used 3D used **Spline** (`@splinetool/react-spline`, a hosted scene edited visually and loaded by URL), not hand-authored Three.js. That's a real, different tradeoff from the rest of this skill:

- Spline: faster to get a polished scene, no shader/geometry code, but the scene lives on Spline's platform (URL dependency, less runtime control, harder to hook into scroll-driven camera work described in `gsap-scroll.md`).
- R3F/Three.js (rest of this skill): full runtime control, scroll-jacking and instancing patterns apply directly, but costs actual 3D-authoring time.

Default to Spline when the ask is "one polished 3D hero, ship it fast" and to R3F when the ask involves scroll-driven camera moves, many repeated objects, or anything perf-critical (Spline's own runtime overhead stacks on top of whatever it's rendering — always lazy-load it: `React.lazy(() => import("@splinetool/react-spline"))` behind `<Suspense>` with a solid-color fallback `div`, so first paint isn't blocked on it).

## Background media that doesn't block interaction

Full-bleed video or embedded-3D as a hero background needs a specific stacking contract, seen identically across all three prompts:

1. Media sits in an `absolute inset-0` layer, `pointer-events-none` isn't enough by itself — the **content wrapper on top** also gets `pointer-events-none`.
2. Individual interactive elements inside that wrapper (buttons, links) get `pointer-events-auto` explicitly re-enabled.
3. Result: clicks pass through empty space to the media/scene below, but CTAs stay clickable. This is the only reliable way to layer a hero without an invisible click-blocking div.

For video specifically: `autoPlay loop muted playsInline`, `object-cover`, no controls. `muted` is load-bearing — autoplay is blocked by every major browser without it.

## Blending media into the page background

Two techniques, pick based on whether the page is dark or light:

- **Dark pages**: layer a `linear-gradient` overlay at partial opacity on top of the video/scene (e.g. dark-to-transparent from one edge) plus a separate bottom-up gradient for text legibility where copy sits over the media.
- **Light pages**: put a solid-color gradient mask (`bg-gradient-to-b from-{page-bg} to-transparent`) *below* the video in stacking order but covering its top edge, so the media appears to fade out of the page background rather than being cut off with a hard edge. Match the gradient's solid color exactly to the page's base background, not to white/black generically — a mismatch is immediately visible.

Never crop media with `overflow-hidden` alone and call it blended — that's a hard edge, not a fade. If nothing else, add a gradient mask.

## Liquid-glass card border

CSS-only glass border effect without an SVG, used for the floating "badge" card pattern:

```css
.glass-card {
  position: relative;
  background: rgba(255, 255, 255, 0.01);
  background-blend-mode: luminosity;
  backdrop-filter: blur(4px);
  box-shadow: inset 0 1px 1px rgba(255, 255, 255, 0.1);
}
.glass-card::before {
  content: "";
  position: absolute;
  inset: 0;
  padding: 1.4px;
  background: linear-gradient(180deg, rgba(255,255,255,0.6), rgba(255,255,255,0));
  -webkit-mask:
    linear-gradient(#fff 0 0) content-box,
    linear-gradient(#fff 0 0);
  -webkit-mask-composite: xor;
  mask-composite: exclude;
}
```

The trick is the `padding` on `::before` combined with `mask-composite: exclude` — it produces a border that's exactly the gradient, with a sharp inner edge and no visible fill, which a plain `border` or `background` gradient can't do. `backdrop-filter` needs a `-webkit-` prefix for Safari; both browsers need it for the blur to actually apply.

## Staggered entrance motion

All three prompts stagger hero elements (eyebrow → headline → description → CTA → trust line) with increasing delays (~0.15–0.2s apart) rather than animating everything at once. The shared shape:

```js
// framer-motion / motion.dev style
initial={{ opacity: 0, y: 15 }}
animate={{ opacity: 1, y: 0 }}
transition={{ duration: 0.7, delay: 0.2, ease: [0.16, 1, 0.3, 1] }}
```

`[0.16, 1, 0.3, 1]` is ease-out-expo — fast start, long soft settle. It's what makes staggered fades read as "premium" instead of generic; the default `ease-out`/`ease-in-out` curves feel flatter. If not using a motion library, the CSS-keyframe equivalent adds a `filter: blur(4px) → blur(0)` alongside the `opacity`/`translateY`, which sells the settle even harder.

## `prefers-reduced-motion` is not optional

None of the three source prompts mention it, and it's the single biggest gap in this file — every technique above (staggered fade-up, scroll-jacked pin/dolly, continuous idle rotation) is exactly the class of motion `prefers-reduced-motion: reduce` exists to suppress. Missing this isn't a polish gap, it's an accessibility bug, same severity class as the "no mobile fallback" anti-pattern in `patterns-and-antipatterns.md`. Two places to gate it:

**CSS side** — override the animation utility unconditionally, outside any `@layer` so it wins the cascade over Tailwind's layered utilities without needing `!important`:

```css
@media (prefers-reduced-motion: reduce) {
  .animate-fade-up {
    animation: none;
    opacity: 1;
    transform: none;
    filter: none;
  }
}
```

**JS side** — anything driven by `useFrame`/`requestAnimationFrame`/GSAP `ScrollTrigger` needs its own check, since CSS can't touch WebGL canvas content or GSAP-driven pin/scrub:

```js
const prefersReducedMotion = () =>
  typeof window !== "undefined" &&
  window.matchMedia("(prefers-reduced-motion: reduce)").matches;
```

Check it once before creating the `ScrollTrigger` (skip the pin/dolly entirely — leave the camera at its default resting position) and inside any continuous idle-rotation `useFrame` (skip the rotation write, render a static frame instead of spinning forever). A `matchMedia` listener can react live if the OS setting changes mid-session, but a one-time check at mount covers the common case and is what most production sites actually ship.

## Fluid typography without breakpoint jumps

`clamp(min, preferred-vw, max)` on heading/subheading font-size scales continuously between mobile and desktop instead of jumping at breakpoints:

```css
font-size: clamp(3rem, 8vw, 6rem); /* h1 */
font-size: clamp(1.125rem, 2.5vw, 1.875rem); /* subheading */
```

Use for hero headings specifically — body copy is fine with normal responsive classes; `clamp()` earns its complexity on the one or two lines that must look intentional at every viewport width, not everywhere.

## Decorative structure that costs nothing

Cheap details that read as "designed," not decoration for its own sake:

- Thin vertical grid lines at 25/50/75% width, `white/10` opacity, desktop-only — implies a design-system grid without a real one.
- A single large blurred SVG ellipse (`filter: blur(25px)`) behind the hero content for an ambient glow, instead of a real light source or gradient mesh library.

The three below are confirmed by two independent real production builds (a financial dashboard and a personal site) that arrived at nearly the same techniques independently — a strong signal each is worth having on hand, not a one-off trick:

- **Slow-drifting blurred gradient blobs** ("aurora" background): 2–3 absolutely-positioned circles, `border-radius: 50%`, `filter: blur(80–100px)`, each with its own slow (16–24s) `ease-in-out infinite` drift keyframe (small `translate`/`scale` swing, not a full traverse — the point is ambient, not attention-grabbing). Cheaper than a video/3D background and works on a plain gradient page with no media asset at all.
  ```css
  @keyframes blobDrift {
    0%, 100% { transform: translate(0, 0) scale(1); }
    50% { transform: translate(5%, -6%) scale(1.1); }
  }
  .blob { position: absolute; border-radius: 50%; filter: blur(90px); animation: blobDrift 18s ease-in-out infinite; }
  ```
- **Animated gradient text**: a multi-stop `linear-gradient` clipped to text (`background-clip: text` + `color: transparent`) with `background-size: 200% auto` panning via `background-position` — reserve for a single prominent heading/figure, not body text; panning too many gradient-text elements at once reads as noisy rather than premium.
- **Breathing watermark/logo mark**: a large low-opacity background logo or icon with a very slow (~7s) opacity+scale pulse instead of sitting dead-static — makes a decorative background element feel alive without competing with foreground content.

All three are continuous idle motion — gate them behind `prefers-reduced-motion` exactly like the staggered entrance above.

## What to leave out when reusing these prompts

The three source prompts hardcode brand-specific asset URLs — a Mux HLS stream, a specific Spline scene ID, a CloudFront video path. These are **not reusable values**, they're placeholders for "point this at your own asset." Never carry a hardcoded third-party URL from one project's prompt into another's — treat every media URL in a prompt like this as a variable to fill in, not a working default.
