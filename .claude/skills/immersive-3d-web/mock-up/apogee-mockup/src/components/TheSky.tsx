import { useInViewReveal } from "../hooks/useInViewReveal";

const POINTS = [
  { n: "01", title: "Zero light pollution", body: "Bortle class 1 site, two hours from the nearest streetlight — the Milky Way casts a visible shadow on a clear night." },
  { n: "02", title: "Research-grade optics", body: "A 14\" reflector on a computerized equatorial mount, the same class of instrument used by university observation programs." },
  { n: "03", title: "A guide who knows the sky", body: "Working astronomers, not tour guides — ask what a Herbig-Haro object is and you'll get a real answer." },
];

function Point({ point, index }: { point: (typeof POINTS)[number]; index: number }) {
  const { ref, className } = useInViewReveal<HTMLDivElement>();
  return (
    <div ref={ref} className={`${className} border-t border-line pt-6`} style={{ transitionDelay: `${index * 0.12}s` }}>
      <span className="font-display text-sm text-gold/70 italic">{point.n}</span>
      <h3 className="font-display mt-3 text-xl text-star">{point.title}</h3>
      <p className="mt-3 text-sm leading-relaxed text-star/55">{point.body}</p>
    </div>
  );
}

export function TheSky() {
  const heading = useInViewReveal<HTMLDivElement>();

  return (
    <section id="the-sky" className="relative border-t border-line bg-void px-6 py-28 md:px-16 md:py-36">
      <div className="mx-auto max-w-5xl">
        <div ref={heading.ref} className={heading.className}>
          <p className="text-[11px] font-semibold tracking-[0.3em] text-gold uppercase">The sky</p>
          <h2 className="font-display mt-4 max-w-xl text-[clamp(2rem,4.5vw,3.25rem)] leading-tight text-star">
            Why the view actually holds up.
          </h2>
        </div>

        <div className="mt-16 grid gap-10 md:grid-cols-3 md:gap-8">
          {POINTS.map((p, i) => (
            <Point key={p.n} point={p} index={i} />
          ))}
        </div>
      </div>
    </section>
  );
}
