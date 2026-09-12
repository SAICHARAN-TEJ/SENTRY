import { Tilt } from "./Tilt";
import { useInViewReveal } from "../hooks/useInViewReveal";

const EXPERIENCES = [
  { name: "Private Viewing", duration: "2 hours", desc: "One dome, one telescope, one guide — built around whatever's actually up that night.", price: "From $340" },
  { name: "Astrophotography Session", duration: "4 hours", desc: "Long-exposure setup on our 14\" reflector, RAW files delivered the next morning.", price: "From $620" },
  { name: "Group Expedition", duration: "3 hours", desc: "Up to 8 guests, three telescopes, a guided tour of the visible sky.", price: "From $180 / person" },
];

function ExperienceCard({ item, index }: { item: (typeof EXPERIENCES)[number]; index: number }) {
  const { ref, className } = useInViewReveal<HTMLDivElement>();

  return (
    <div ref={ref} className={className} style={{ transitionDelay: `${index * 0.1}s` }}>
      <Tilt max={5}>
        <div className="glow-ring lift-card glass-card rounded-2xl p-8">
          <span className="font-mono text-[11px] tracking-[0.14em] text-gold uppercase">{item.duration}</span>
          <h3 className="font-display mt-3 text-2xl text-star">{item.name}</h3>
          <p className="mt-3 text-sm leading-relaxed text-star/60">{item.desc}</p>
          <div className="mt-6 flex items-center justify-between border-t border-line pt-4">
            <span className="font-mono text-sm text-gold">{item.price}</span>
            <a href="#top" className="nav-link text-[11px] tracking-[0.14em] text-star/60 uppercase hover:text-gold">
              Reserve →
            </a>
          </div>
        </div>
      </Tilt>
    </div>
  );
}

export function Experiences() {
  const heading = useInViewReveal<HTMLDivElement>();

  return (
    <section id="experiences" className="relative border-t border-line bg-void px-6 py-28 md:px-16 md:py-36">
      <div className="mx-auto max-w-5xl">
        <div ref={heading.ref} className={heading.className}>
          <p className="text-[11px] font-semibold tracking-[0.3em] text-gold uppercase">Experiences</p>
          <h2 className="font-display mt-4 max-w-xl text-[clamp(2rem,4.5vw,3.25rem)] leading-tight text-star">
            Three ways to look up.
          </h2>
        </div>

        <div className="mt-16 grid gap-6 md:grid-cols-3">
          {EXPERIENCES.map((item, i) => (
            <ExperienceCard key={item.name} item={item} index={i} />
          ))}
        </div>
      </div>
    </section>
  );
}
