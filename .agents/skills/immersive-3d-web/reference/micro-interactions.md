# Micro-interactions: the site-wide polish layer

Source: distilled from hands-on build/review sessions under this skill, plus patterns confirmed in two real production codebases (a live financial dashboard and a personal site) — not official docs, same sourcing caveat as `hero-dressing.md`. Where a pattern shows up independently in more than one real build, that's noted — it's a stronger signal than a single source.

`hero-dressing.md` covers the hero: one section, entrance motion, background media. This file covers the opposite end — tiny, constant feedback spread across the *whole* site (nav links, buttons, cards) that a user only notices on the second look, but whose absence is exactly what makes an otherwise good-looking build read as a screenshot instead of a real product. A hero that nails every pattern in `hero-dressing.md` still feels unfinished if the nav links don't react to the mouse.

## Nav link underline

The recognizable "premium site" nav pattern: a thin line grows in under a link on hover, not just a color change.

```css
.nav-link {
  position: relative;
}
.nav-link::after {
  content: "";
  position: absolute;
  left: 0;
  bottom: -2px;
  width: 100%;
  height: 1px;
  background: currentColor;
  transform: scaleX(0);
  transform-origin: left;
  transition: transform 0.3s cubic-bezier(0.16, 1, 0.3, 1);
}
.nav-link:hover::after,
.nav-link:focus-visible::after {
  transform: scaleX(1);
}
```

Animate `transform: scaleX()`, not `width`. `width` changes layout geometry every frame (the browser has to reflow); `transform` is composited on the GPU and costs nothing extra. Same rule as everywhere else in this skill: transform/opacity for anything that animates on interaction, not layout properties.

## Button feedback needs a press state, not just a hover state

- Hover: `scale-[1.02]` plus a brightness/shadow lift — small enough to feel responsive, not springy.
- Active (press): `scale-[0.97]`. This is the one people skip. Without it, a click doesn't *feel* like it registered before the page reacts — the momentary shrink is what sells "I pressed a real thing."
- Icon-arrow CTAs ("Learn more →"): the arrow itself translates on hover (`group-hover:translate-x-1`), not just the button background. Wrap the button and icon in a `group` so the icon can react to the parent's hover state.
- Outline/ghost buttons: fade the border color and background tint in over ~200ms rather than an instant swap. An instant color swap on hover reads as unstyled default browser behavior even when the colors are custom.

## Sheen sweep — two variants, different triggers

A diagonal light sweep across a button or card. Two independently-confirmed real implementations, and they're not interchangeable — pick based on what should draw the eye:

**Hover-triggered** (buttons, cards) — a skewed gradient strip that sweeps across on `:hover`, idle otherwise:
```css
.btn-sheen { position: relative; overflow: hidden; }
.btn-sheen::after {
  content: ''; position: absolute; top: 0; left: -80%; width: 50%; height: 100%;
  transform: skewX(-20deg);
  background: linear-gradient(90deg, transparent, rgba(255,255,255,0.35), transparent);
  transition: left 0.55s ease;
}
.btn-sheen:hover::after { left: 130%; }
```
Tune the gradient's peak opacity down (~0.10) and slow the transition (~0.9s) for large surfaces like a KPI/data card — the same intensity that reads as crisp on a small button reads as gaudy at card scale.

**Continuous ambient** (the *one* primary hero CTA, not every button) — a looping `background-position` pan, always subtly moving to keep the single most important action visually alive:
```css
.hero-cta { position: relative; overflow: hidden; }
.hero-cta::after {
  content: ''; position: absolute; inset: 0;
  background: linear-gradient(120deg, transparent 30%, rgba(255,255,255,0.35) 50%, transparent 70%);
  background-size: 200% 100%;
  animation: ctaShine 3.5s ease-in-out infinite;
}
@keyframes ctaShine { 0% { background-position: 200% 0; } 100% { background-position: -200% 0; } }
```
Reserve the continuous variant for exactly one element per screen — it's an attention magnet, and two of them fighting for the eye cancels the effect. Both need the standard `prefers-reduced-motion` cutout (`animation: none` / `display: none` on the pseudo-element).

## Tilt and magnetic hover (cursor-following micro-motion)

Two related cursor-driven effects for cards and buttons, both requiring the same three guards: skip under `prefers-reduced-motion`, skip on coarse (touch) pointers — `window.matchMedia('(pointer: coarse)')` — since there's no hover/cursor-position concept on touch, and write the transform directly to the DOM node in the mousemove handler rather than through React state, so the effect doesn't trigger a re-render on every pixel of mouse movement.

**Tilt** — the element rotates in 3D toward the cursor position:
```js
function onMove(e) {
  const r = el.getBoundingClientRect();
  const px = (e.clientX - r.left) / r.width - 0.5;   // -0.5..0.5
  const py = (e.clientY - r.top) / r.height - 0.5;
  el.style.transform = `perspective(700px) rotateX(${(-py * MAX).toFixed(2)}deg) rotateY(${(px * MAX).toFixed(2)}deg)`;
}
function onLeave() { el.style.transform = ''; }
```
**`MAX` is a brand-tone decision, not a fixed constant** — a confirmed institutional/financial product deliberately used `8°` specifically to read as restrained rather than "gamey," while a consumer/portfolio site used a punchier value. Pick the degree to match the product's register, don't default to whatever a tilt-card tutorial suggests.

**Magnetic** — the element (usually a button, paired with a custom cursor) drifts a few px toward the cursor instead of rotating:
```js
function onMove(e) {
  const r = el.getBoundingClientRect();
  const dx = e.clientX - (r.left + r.width / 2);
  const dy = e.clientY - (r.top + r.height / 2);
  el.style.transform = `translate(${(dx * strength).toFixed(1)}px, ${(dy * strength).toFixed(1)}px)`; // strength ~0.2
}
```
Both need a snappy transition on move (~60ms ease-out or none, applied inline per-move) and a slower one on leave (~300–400ms `cubic-bezier(0.22, 1, 0.36, 1)`) so the return to rest is the only part that visibly eases — matching move 1:1 to the cursor and only easing the release is what makes it feel physical instead of laggy.

## Card hover lift

Anything clickable in a grid (product cards, route/session cards, pricing tiers) gets a small lift on hover: `translateY(-2px)` to `translateY(-4px)` plus a shadow increase. This is the signal that tells a user "this is interactive" before they've consciously read anything on it — skip it and a card grid reads as static content even when every card is a link.

## The actual "professional" signal is consistency, not cleverness

None of the techniques above are individually hard or novel. What makes a site feel premium instead of "a pile of hover effects" is using the **same transition duration and easing curve everywhere** — reuse the ease-out-expo curve from `hero-dressing.md` (`cubic-bezier(0.16, 1, 0.3, 1)`) for interaction feedback too, just faster (200–300ms for hover/press vs. 700–800ms for entrance animation). A page mixing default `ease` transitions on some elements with a custom curve on others feels inconsistent even when every individual detail, judged alone, looks fine. Pick the curve once, put it in a CSS custom property or Tailwind theme token, and reuse it everywhere interaction feedback happens.

## Focus states are not optional

Every hover pattern above needs a `:focus-visible` equivalent that does the same thing — nav underline, button lift, card shadow. A keyboard user tabbing through the page gets zero feedback about where they are without it. This is the same class of gap as skipping `prefers-reduced-motion` (see `hero-dressing.md`): invisible in a normal demo, a real accessibility miss, and it never shows up in a screenshot — only in actual use, which is exactly why it gets skipped.

## Cursor affordance

`<a>` and `<button>` get `cursor: pointer` for free. Anything else wired to `onClick` — a `<div>` acting as a card link, a custom dropdown trigger — needs it set explicitly, or the page silently tells the mouse "this isn't clickable" while the code says otherwise.
