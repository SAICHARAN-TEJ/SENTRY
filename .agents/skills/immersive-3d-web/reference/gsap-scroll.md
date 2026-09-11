# GSAP ScrollTrigger — scroll-driven animation

Source: gsap.com/docs/v3/Plugins/ScrollTrigger

This is the engine behind almost every "site scrolls, 3D scene reacts" experience (pinned hero sections, scrubbed camera moves, snapped chapters).

## Setup

```js
gsap.registerPlugin(ScrollTrigger);

gsap.to(".box", {
  scrollTrigger: ".box",
  x: 500
});
```

## Core config properties

| Property | Purpose |
|---|---|
| `trigger` | element whose position determines when the animation starts |
| `start` | when it activates (default `"top bottom"`) |
| `end` | when it deactivates (default `"bottom top"`) |
| `scrub` | **the key one for 3D** — links animation progress directly to scroll position instead of playing on a timer; `true` or a number (smoothing seconds) |
| `pin` | locks the trigger element in place while its scroll range is active — how "scroll through a fixed 3D scene" sections work |
| `toggleActions` | controls play/pause/resume/reverse at the four enter/leave boundaries |
| `snap` | snaps scroll position to increments or timeline labels — chapter-style navigation |
| `markers` | visual debug markers for start/end — turn on while building, off for production |
| `onEnter`, `onLeave`, `onUpdate` | callbacks; `onUpdate` is where you typically read `self.progress` to drive a Three.js camera or object |

## Pattern for driving a 3D scene from scroll

`scrub` is what makes this useful for 3D: instead of a one-shot animation, the scroll position *is* the animation's playhead. In an R3F context, don't animate Three.js props via GSAP's DOM tweening — read `ScrollTrigger`'s progress and apply it inside `useFrame` or an `onUpdate` callback, since Three.js object properties aren't DOM/CSS properties GSAP targets natively:

```js
ScrollTrigger.create({
  trigger: "#scene-wrapper",
  start: "top top",
  end: "bottom bottom",
  scrub: 1,
  onUpdate: (self) => {
    // self.progress is 0→1 across the pinned range
    cameraRef.current.position.z = lerp(5, 1, self.progress);
  }
});
```

`pin: true` on the trigger keeps the `<Canvas>` fixed on screen while the rest of the page scrolls past/through it — the standard "scrolljacked hero" structure.

## Performance note

ScrollTrigger "prioritizes performance by pre-calculating positions rather than continuously monitoring elements" — but a 3D scene reacting to `onUpdate` every scroll tick still has to re-render every frame. Keep whatever `onUpdate` touches cheap (position/rotation writes), not something that reallocates geometry or materials — see `patterns-and-antipatterns.md`.

Use `matchMedia()` (GSAP's responsive config, not just CSS) to swap out or disable scroll-driven 3D entirely on mobile viewports where the perf budget is tighter — this is a load-bearing pattern for "powerful 3D site" workflows, not an edge case.
