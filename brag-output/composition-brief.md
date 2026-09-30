# Hyperframes Composition Brief: SUBPIXEL-SENTRY

## Objective
Create a short launch-style brag video for SUBPIXEL-SENTRY.

## Output
- Composition directory: `brag-output-2026-09-30-120605/composition/`
- Rendered video: `brag-output-2026-09-30-120605/brag.mp4`
- Format: landscape — 1920x1080
- Duration: 23 seconds

## Source Material
- Project root: `e:\SENTRY`
- Primary files read: `index.html`, `css/console.css`, `css/spacex-theme.css`, `README.md`
- Product name: SUBPIXEL-SENTRY
- Tagline / strongest claim: Trust, but verify the AI.
- Key UI or visual moment to recreate: The tactical 3D DEM, the split-slider reconstruction reveal, and the red CRITICAL anomaly alert with the Evidence Dossier.
- Copy that must appear verbatim:
  - TRUST, BUT VERIFY.
  - CRITICAL: Target signature matched
  - Find the unseen. Prove it's real.

## Creative Direction
- Tone preset: cinematic
- Creative direction: Tactical military intelligence film, high-stakes and serious.
- Interpretation: Wide shots, big typography, dramatic reveals, and restrained but impactful motion.
- Angle: Military-grade precision and absolute distrust of AI. We don't just generate higher resolution; we mathematically interrogate it.
- Hook: A dramatic, sweeping shot over the 3D Himalayan tactical DEM, with the stark, uppercase title "TRUST, BUT VERIFY." fading in. 
- Outro / punchline: The system locks down. "Find the unseen. Prove it's real." Logo out.
- Avoid:
  - Generic SaaS language
  - Abstract filler visuals
  - Unrelated visual redesign

## Visual Identity
- Background: #000000
- Text: #f0f0fa
- Accent: #d32f2f
- Display font: Barlow
- Body font: IBM Plex Mono
- Visual references from the project: The pure black interface with harsh 1px borders, cartographic spectral data overlays.

## Storyboard
Use the storyboard in `brag-output-2026-09-30-120605/brag-plan.md` as the creative contract.

Scene summary:
1. The Hook — 4s — The 3D tactical DEM. Text "TRUST, BUT VERIFY." slams in.
2. The Mission — 5s — Console UI, selecting bands and running reconstruction. Cursor interaction.
3. The Reveal — 6s — Split-slider wiping across screen showing 10m to 2.5m resolution improvement.
4. The Interrogation — 5s — Red "CRITICAL" alert box and Evidence Dossier sliding in.
5. The Outro — 3s — UI fades out, 3D terrain remains, final text "Find the unseen. Prove it's real. SUBPIXEL-SENTRY."

## Audio
- Audio role: cinematic support
- Audio arc: A tense build-up, resolving to heavy impacts on key moments.
- Music: happy-beats-business-moves-vol-12-by-ende-dot-app.mp3
- Music treatment: Low volume (0.2), swelling up slightly on the split-slider reveal, cutting sharply or ducking slightly on the red alert.
- Music cue guidance: Detect at composition via `hyperframes beats`. Target strong beats for "TRUST, BUT VERIFY." (Scene 1) and the red alert (Scene 4).
- Audio-reactive treatment: subtle; use RMS to gently pulse the 3D terrain exposure/glow.
- Audio-coupled moments:
  - Scene 1 — Text slams in on a beat.
  - Scene 4 — Red alert pop with a sharp alarm hit.
- SFX selection guidance: Deep, heavy, impactful. Use `impactBell_heavy_*` for major moments, `interface/click_*` for the cursor, and a sharp hit for the red alert.
- SFX analysis guidance: C:\Users\M SAI CHARAN TEJ\.gemini\config\skills\brag\assets\sfx\sfx-analysis.md
- Exact SFX choice: Hyperframes should choose filenames, timestamps, density, and volume based on the implemented animation.
- Audio files: copy the chosen music and any Hyperframes-selected SFX into `brag-output-2026-09-30-120605/composition/assets/`

## Hyperframes Instructions
Load the composition-building Hyperframes domain skills — `hyperframes-core` (composition contract + `data-*` timing), `hyperframes-animation` (motion), `hyperframes-creative` (design spec, beats, audio-reactive), `hyperframes-keyframes` (seek-safe keyframes), and `hyperframes-cli` (lint/check/render). /brag is its own workflow: do not enter the `hyperframes` entry-point intent interview and do not route into its generic promo / launch-video workflow. Prefer native Hyperframes conventions over anything in `/brag`.

Requirements:
- Show at least one real UI, copy, or visual element from the source project.
- Keep all text readable in the final render.
- Keep the video within 15-25 seconds.
- Include the planned music/SFX layer unless audio was explicitly disabled or documented as intentionally silent.
- Treat `/brag` audio notes as guidance, not a fixed cue sheet. Choose SFX after the visual animation exists.
- Treat music cue metadata as optional timing hints. Hyperframes decides exact animation timing and should ignore cues that hurt readability, scene pacing, or the product story.
- Major reveals may move toward nearby strong cues within about 0.15s. Smaller entrances may align to nearby beat points within about 0.10s. Use only 1-3 strong cue locks in a 15-25s video unless the edit clearly benefits from more.
- Use SFX to support motion and interaction: card sounds for card-like reveals, short announcement cues for major payoffs, key/click sounds for text or user actions, and restraint when the edit is already busy.
- Honor planned music treatment such as fade-outs, ducking, beat-aligned reveals, or letting a final SFX ring over the music, using the best Hyperframes-supported implementation.
- When music is present and the treatment is not `none`, consider Hyperframes audio-reactive workflow: extract audio data and use RMS/frequency bands for subtle, brand-specific motion. Good targets are glow, depth, background warmth, card presence, title emphasis, or other existing visual elements. Avoid waveform/equalizer visuals, musical-note graphics, generic particle systems, strobing, or heavy pulsing.
- Use local assets for audio and any required runtime/media dependencies when possible.
- Run `hyperframes check` before render — it is brag's single gate.
