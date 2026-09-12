# State and feedback: loading, selection, locks, rewards

Source: distilled from two real production codebases (a live financial dashboard and a personal site), not official docs — same sourcing caveat as `hero-dressing.md` and `micro-interactions.md`.

`micro-interactions.md` covers feedback tied to the *cursor* — hover, press, focus. This file covers feedback tied to *application state* — a component before its data has loaded, an item the user has selected, a feature they don't have access to yet, a moment worth celebrating. These are the details that separate a demo (which only ever shows the happy final state) from a real product (which has to render every state honestly).

## Loading states aren't optional

A component that only has a design for "data loaded" is a component that flashes empty or breaks the layout for however long the real request takes. Skeleton placeholders — grey blocks shaped like the content that's coming — go wherever real data loading happens:

```jsx
if (loading) {
  return (
    <div className="border p-4 animate-pulse">
      <div className="h-3 w-20 mb-3 rounded bg-surface-hover" />
      <div className="h-7 w-24 mb-2 rounded bg-surface-hover" />
      <div className="h-3 w-16 rounded bg-surface-hover" />
    </div>
  );
}
```

Match the skeleton's shape (bar widths/heights) to the real content's shape — a generic grey box is better than nothing, but bars sized like the label/value/change-percent that are about to appear is what makes the transition from loading to loaded feel like the *same component*, not a swap.

## Selected / active state

For anything a user can select from a set (a filter, a tab, a KPI card that filters a chart below it): pair a colored ring with an *inset* glow, not just a border-color change — the inset shadow reads as "this one is lit from within," a plain border swap reads as "this one has a different border."

```css
.selected {
  border-color: rgba(88, 166, 255, 0.4);
  background: rgba(88, 166, 255, 0.06);
  box-shadow: inset 0 0 30px -12px rgba(88, 166, 255, 0.6);
}
```
A small pulsing dot (`animate-pulse-slow`, ~2s opacity cycle) next to the label reinforces "currently active" without needing extra text.

## Locked / gated state — and the border-gradient decision rule it surfaces

A feature the user doesn't have access to yet (premium gate, coming-soon) reads completely differently depending on treatment: plain `opacity-50 pointer-events-none` says "broken," a gradient border plus a very soft brand-colored wash says "an upgrade away" — worth the extra styling on anything that's a real upsell surface, not a genuine dead end.

```css
.locked {
  background:
    linear-gradient(135deg, color-mix(in oklch, var(--card) 94%, var(--brand-a) 6%), color-mix(in oklch, var(--card) 94%, var(--brand-b) 6%)) padding-box,
    linear-gradient(90deg, var(--brand-a), var(--brand-b)) border-box;
  border: 1.5px solid transparent;
}
```

This surfaces a real decision that's easy to get wrong: **there are two different techniques for a gradient border, and they are not interchangeable.**

- **Double-background (`padding-box` + `border-box`), shown above** — for an element where you're painting its *own real background*. The `padding-box` layer is opaque and becomes the element's visible interior; the `border-box` layer shows only where the border ring is. Use this whenever the border sits on a surface that should look solid.
- **`mask-composite` cutout (the liquid-glass technique from `hero-dressing.md`)** — for a gradient ring stacked as an *overlay on top of content that already exists* (a card's own text/icons underneath). An opaque `padding-box` fill here would sit above and hide that content; `mask-composite: exclude` genuinely cuts the interior away, leaving only the ring painted, so whatever's underneath stays untouched.

Rule of thumb: building the card from scratch and the border is part of its base look → double-background. Adding a gradient ring on hover/state-change to a card that already renders its own content → mask-composite overlay.

## Number and progress reveal

- **Count-up**: animate a numeric value from its previous displayed value to the new one with an eased curve (`easeOutCubic`: `1 - (1-p)³`) over the current animation frame's progress, not a CSS transition (CSS can't tween the *text content* of a number). Skip straight to the final value under `prefers-reduced-motion`.
  ```js
  const eased = 1 - Math.pow(1 - progress, 3);
  display = from + (target - from) * eased;
  ```
  Use for any KPI/stat that changes on reveal or on live data refresh — a number that visibly counts up reads as "live data," a number that just appears reads as static text even when it isn't.
- **Progress/bar grow**: animate `width` from `0%` to a CSS custom property holding the real target (`--tw: 62%`), `cubic-bezier(0.4,0,0.2,1)`, ~0.7s. This is one of the rare cases animating `width` (not `transform: scaleX`) is fine — a progress bar's width *is* semantically meaningful data, not purely decorative, so the layout cost is acceptable at this scale (one bar, not a list of hundreds).

## `animation-fill-mode: both`, not just `forwards`, for delayed entrances

A staggered-entrance element with `animation-delay` and `animation-fill-mode: forwards` is visible in its *unanimated* state for the entire delay, then jumps to frame 0 and plays — a visible flash-then-snap. `both` holds the animation's `from` state (invisible/offset) through the delay too, so the element genuinely stays hidden until its turn:

```css
.animate-fadeup { animation: fadeUp 0.4s ease-out both; } /* not forwards */
```

## CSS-only stagger via `:nth-child`, when order matches

The inline-style `animationDelay` per element (`hero-dressing.md`'s stagger pattern) is necessary when delays are computed from dynamic data (item index in a rendered list). But when a fixed number of elements are known at author-time and their DOM order already matches the desired stagger order (a hero's eyebrow → headline → CTA), plain CSS is simpler and needs no per-element inline style at all:

```css
.stagger > * { opacity: 0; animation: fadeUp 0.7s cubic-bezier(0.22,1,0.36,1) forwards; }
.stagger > *:nth-child(1) { animation-delay: 0.05s; }
.stagger > *:nth-child(2) { animation-delay: 0.15s; }
.stagger > *:nth-child(3) { animation-delay: 0.28s; }
```
Prefer this default for static hero content; fall back to inline `animationDelay` only once the list is dynamic (mapped from an array/API response).

## Celebratory one-shot animations

A badge unlock, a goal reached, a milestone — a burst of small pieces flying outward, each with randomized angle/distance/color set via inline CSS custom properties per piece (`--tx`, `--ty`, `--rot`, `--delay`), sharing one keyframe:

```css
@keyframes confettiBurst {
  0%   { transform: translate(0,0) rotate(0deg); opacity: 1; }
  100% { transform: translate(var(--tx), var(--ty)) rotate(var(--rot)); opacity: 0; }
}
.confetti-piece { animation: confettiBurst 900ms cubic-bezier(0.2,0.7,0.3,1) both; animation-delay: var(--delay, 0ms); }
```

**Reduced-motion handling here is different from continuous idle motion.** For ambient/idle animation (aurora blobs, breathing watermark), the reduced-motion fallback is a static frame at rest. For a one-shot *reward* moment tied to a real event, cutting straight to "gone" (`animation: none; opacity: 0`) is correct — there's no meaningful "rest state" for a confetti piece to sit in, the event already happened and the celebration was the animation itself.

## Custom cursor

A dot that tracks the real cursor 1:1, plus a ring that trails behind it with easing (lerp toward the cursor position each frame, not a CSS transition):

```js
ring.x += (mouse.x - ring.x) * 0.18; // per-frame lerp, not CSS transition
```
Required guards: disable entirely on coarse/touch pointers (`matchMedia('(pointer: coarse)')` — there's no real cursor to replace), set `document.body.style.cursor = 'none'` only once confirmed non-touch, and toggle a body class on hover-enter/leave of interactive elements (`a, button, input, [role="button"]`) so the dot/ring can react (commonly: ring grows and fades to a soft glow, dot disappears) — the reaction is what makes it worth building over the native cursor, not the replacement itself. This is a heavier, more opinionated choice than everything else in this file — reach for it on a portfolio/brand site where the cursor itself is part of the identity, not on a dense data app where users need the native cursor's predictability.

## Ticker / marquee tape

An infinitely-scrolling horizontal strip (live prices, logos, headlines): render the content list **twice** back-to-back, animate `translateX(0 → -50%)` linearly on a loop — because the content is duplicated, the moment the first copy has scrolled fully off, the second copy is in the exact position the first started in, so the loop is seamless with no reset-jump.

```css
.ticker-track { display: flex; width: max-content; animation: scroll 45s linear infinite; }
@keyframes scroll { from { transform: translateX(0); } to { transform: translateX(-50%); } }
.ticker-wrap:hover .ticker-track { animation-play-state: paused; }
```
Pair with edge-fade gradient masks (`linear-gradient(to right, var(--bg), transparent)` absolutely positioned at both ends) so content doesn't hard-cut at the container edge. Mark the whole tape `aria-hidden="true"` if it's decorative/duplicative of data shown elsewhere on the page — a screen reader has no use for an infinite scroll of the same numbers.

## The underlying principle: match intensity to brand register

Nothing in this file or `micro-interactions.md` has one "correct" intensity — tilt's max rotation, sheen's opacity, gradient usage frequency, cursor replacement at all or not — every one of these is a register decision. A confirmed real example: the same tilt-on-hover technique shipped at a restrained 8° on a financial product specifically to avoid reading as "gamey," while a consumer-facing personal site used a punchier default. When applying this file's patterns, pick values that match what the product is (institutional and trustworthy vs. expressive and playful), don't copy the numbers verbatim from here.
