import { useEffect, useState } from "react";
import { Tilt } from "./Tilt";
import { useCountUp } from "../hooks/useCountUp";
import { useInViewReveal } from "../hooks/useInViewReveal";

type Stat = {
  key: string;
  label: string;
  value: number;
  suffix: string;
  format: (n: number) => string;
};

const STATS: Stat[] = [
  { key: "uptime", label: "Uptime, 30 days", value: 99.98, suffix: "%", format: (n) => n.toFixed(2) },
  { key: "latency", label: "Avg response time", value: 128, suffix: "ms", format: (n) => Math.round(n).toString() },
  { key: "monitors", label: "Active monitors", value: 240, suffix: "", format: (n) => Math.round(n).toString() },
  { key: "incidents", label: "Incidents resolved", value: 37, suffix: "", format: (n) => Math.round(n).toString() },
];

function KPICard({
  stat,
  loading,
  selected,
  onSelect,
}: {
  stat: Stat;
  loading: boolean;
  selected: boolean;
  onSelect: (key: string) => void;
}) {
  const display = useCountUp(stat.value, !loading);

  if (loading) {
    return (
      <div className="animate-pulse-slow rounded-2xl border border-line bg-panel p-6">
        <div className="mb-4 h-3 w-24 rounded bg-panel-hover" />
        <div className="h-8 w-20 rounded bg-panel-hover" />
      </div>
    );
  }

  return (
    <Tilt max={5}>
      <button
        type="button"
        onClick={() => onSelect(stat.key)}
        className={`glow-ring lift-card w-full rounded-2xl border border-line bg-panel p-6 text-left transition-colors focus-visible:outline-none ${
          selected ? "selected" : "hover:bg-panel-hover"
        }`}
      >
        <div className="flex items-center justify-between">
          <p className="text-[11px] font-semibold tracking-[0.18em] text-dim uppercase">{stat.label}</p>
          {selected && <span className="animate-pulse-slow h-1.5 w-1.5 rounded-full bg-signal" />}
        </div>
        <p className="font-mono mt-3 text-3xl font-semibold text-mist">
          {stat.format(display)}
          <span className="ml-1 text-lg text-dim">{stat.suffix}</span>
        </p>
      </button>
    </Tilt>
  );
}

export function KPISection() {
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<string | null>(null);
  const heading = useInViewReveal<HTMLDivElement>();

  useEffect(() => {
    const t = setTimeout(() => setLoading(false), 900);
    return () => clearTimeout(t);
  }, []);

  return (
    <section id="product" className="relative border-t border-line bg-void px-6 py-28 md:px-16 md:py-36">
      <div className="mx-auto max-w-5xl">
        <div ref={heading.ref} className={heading.className}>
          <p className="text-[11px] font-semibold tracking-[0.3em] text-signal uppercase">Live right now</p>
          <h2 className="font-display mt-4 max-w-xl text-[clamp(2rem,4.5vw,3.25rem)] leading-tight text-mist">
            The numbers behind the badge.
          </h2>
          <p className="mt-4 max-w-lg text-sm text-dim">Click a metric to see it highlighted across the dashboard — this is exactly what your team sees on day one.</p>
        </div>

        <div className="mt-16 grid grid-cols-2 gap-4 md:grid-cols-4">
          {STATS.map((stat) => (
            <KPICard
              key={stat.key}
              stat={stat}
              loading={loading}
              selected={selected === stat.key}
              onSelect={(key) => setSelected((cur) => (cur === key ? null : key))}
            />
          ))}
        </div>
      </div>
    </section>
  );
}
