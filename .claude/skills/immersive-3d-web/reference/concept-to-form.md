# Concept-to-form: deriving the hero object from the site, not from habit

Source: self-observed anti-pattern, not official docs. Four site mockups built in one session under this skill — a watch brand, a bouldering gym, a bladesmith, a monitoring SaaS — defaulted to the same family of shape: a faceted polyhedron or torus-based form floating center-screen, regardless of what each site was actually about. Flagged by the person the skill was being used for, not caught internally — worth stating plainly rather than glossing over.

**Read this before `three-core.md` when starting a build from scratch.** Everything else in this skill is about *how* to build a 3D hero well; this file is about deciding *what* to build before any of that matters.

## The anti-pattern, named

Three.js's built-in geometries (`icosahedronGeometry`, `torusGeometry`, `torusKnotGeometry`, `dodecahedronGeometry`) are cheap, reliable, and always look "premium 3D hero" — which is exactly why they're a trap. They require zero authoring effort and zero subject-matter reasoning, so it's easy to reach for one as a safe default and never ask whether it actually means anything for *this* site. A faceted icosahedron sitting in a hero looks equally at home on a watch brand, a knife maker, and a SaaS dashboard — which is the problem, not a feature. If the same object would work unchanged on three unrelated sites, it isn't doing conceptual work, it's decoration wearing a "3D" costume.

## The rule

**Before writing any geometry code, write one sentence: "This scene shows ___, moving like ___, because ___."** If the blank can't be filled with something specific to this site's subject — not "something premium/3D/impressive" — the build hasn't actually started yet, no matter how good the lighting rig ends up looking.

Two separate things need deriving from the subject, not defaulted:

1. **Form** — what shape, if any, has a real relationship to what the site is about. Sometimes literal (a torus knot for a climbing/rope brand — genuinely fits, no metaphor required). Sometimes structural/metaphorical (orbiting rings for a scheduling product, since "things circling on a schedule" is the actual concept, not decoration). And sometimes there's no good object, and the right call is **no hero object at all** — a video/photo background (`hero-dressing.md`), an aurora/gradient backdrop, or the actual product UI in a tilted card, is a legitimate outcome of this exercise, not a failure to find a shape.
2. **Motion** — the *character* of movement should borrow from how the real-world referent actually moves, not from "slow elegant rotation" as a universal default. A planet drifts on a stately, non-uniform orbital plane. A signal or heartbeat pulses sharply then rests, it doesn't idle-spin. A flame or liquid has turbulence and asymmetry. A mechanical instrument (gears, escapements) moves in abrupt, precise steps, not a continuous smooth spin. Reusing the same slow-continuous-rotation across an astronomy site and a fintech dashboard is the motion equivalent of the icosahedron trap — the object changed, the *behavior* didn't.

## A starting-point table, not a lookup table

These are prompts to reason from, not defaults to swap in. The moment one of these gets applied without asking whether it actually fits the specific brief, it's the same mistake wearing a longer list.

| Subject | Form to consider | Motion character |
|---|---|---|
| Astronomy / space / observatory | Orbiting spheres, ring systems, starfield parallax | Slow, gravitational, non-uniform speed (faster near closest approach) |
| Climbing / rope / knots | Torus knots, tangled/looped curves | Organic sway, not rigid-body rotation |
| Precision instruments / watches | Gears, concentric rings, escapement-style stepped motion | Abrupt mechanical ticks, not continuous smooth spin |
| Audio / music / sound | Waveforms, frequency bars, ripples timed to a beat | Rhythmic, pulses on an interval — not a constant loop |
| Finance / data / monitoring | Line charts, network graphs, node clusters | Gentle independent per-node drift at rest (each node its own phase/speed — a system quietly breathing), sharp pulse on events — not a bulk rotation, and not literally frozen either |
| Nature / wellness / organic goods | Blob/metaball shapes, particle flocking, noise-driven fluid distortion | Slow breathing, irregular organic easing, never mechanically uniform |
| Fashion / physical products | The actual product as a 3D asset, if one exists, over an abstract stand-in | Product-photography turntable — deliberate and slow |
| Software / SaaS / abstract tech | Often best served by **no** literal hero object — an aurora/gradient backdrop or the real product UI instead | — |

That last row matters in practice: a monitoring-SaaS build in this same session reached for "a glowing core with radar-style ping rings" as its hero object — a reach for meaning that isn't really there, since uptime monitoring has no natural 3D referent. An aurora-gradient hero with the actual product screenshot tilted in a glass card (both already documented in `hero-dressing.md`/`micro-interactions.md`) would have served that brief better than one more floating shape.

## "Calm at rest" is not "frozen" — a real over-correction

The same build, once it *was* switched to a network graph (a genuinely on-brief form), got fixed a second time for the opposite mistake: every node held its exact static position, with only the rare incident-pulse ever moving. It looked broken, not calm — a network with zero motion anywhere reads as "the page failed to load," not "a system quietly at rest."

The actual fix wasn't reintroducing the bulk rotation this file argues against — it was giving each node its own small, independent drift: a low-amplitude sine offset with a per-node random phase and speed, so the *shape* stays still overall but every individual point is visibly, quietly alive. This is a different kind of motion than a spinning hero object, not a smaller amount of the same kind — one is decoration applied to the whole shape for effect, the other is texture that happens to exist at the level of each individual part, closer to how a real distributed system (many independent things, each doing their own small thing) actually looks. When a subject's "resting" motion character is described as calm/subtle/ambient, default to *distributed* per-element micro-motion over *global* stillness — a scene with literally nothing moving is very rarely the right read, even for a "calm" brief.

## Applying this to a retrofit

When adding 3D to an *existing* site (`retrofit.md`), the subject is already fixed — read the existing copy/branding/product first and derive the form from that, rather than proposing a generic scene and writing copy to match it afterward.
