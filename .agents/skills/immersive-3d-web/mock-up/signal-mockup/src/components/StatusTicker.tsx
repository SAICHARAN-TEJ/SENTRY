const ENTRIES = [
  { name: "api.acme.io", status: "operational" as const, latency: "142ms" },
  { name: "checkout.rivet.app", status: "operational" as const, latency: "89ms" },
  { name: "cdn.northlane.dev", status: "degraded" as const, latency: "410ms" },
  { name: "auth.fintra.co", status: "operational" as const, latency: "61ms" },
  { name: "db-primary.orbitpay", status: "operational" as const, latency: "23ms" },
  { name: "queue.harborsync", status: "operational" as const, latency: "156ms" },
];

const STATUS_COLOR: Record<string, string> = {
  operational: "bg-good",
  degraded: "bg-warn",
  down: "bg-bad",
};

function Entry({ item }: { item: (typeof ENTRIES)[number] }) {
  return (
    <span className="inline-flex items-center gap-2 px-5 whitespace-nowrap">
      <span className={`h-1.5 w-1.5 rounded-full ${STATUS_COLOR[item.status]}`} />
      <span className="font-mono text-xs font-medium text-mist">{item.name}</span>
      <span className="font-mono text-[11px] text-dim">{item.latency}</span>
      <span className="text-line select-none">·</span>
    </span>
  );
}

// Duplicated-content infinite marquee — see immersive-3d-web skill,
// reference/state-and-feedback.md: the second copy is exactly where the
// first started, so the -50% loop has no reset-jump.
export function StatusTicker() {
  return (
    <div
      className="ticker-wrap relative overflow-hidden border-b border-line bg-panel/40 py-2 backdrop-blur-sm"
      aria-hidden="true"
    >
      <div className="absolute inset-y-0 left-0 z-10 w-16 bg-gradient-to-r from-void to-transparent" />
      <div className="absolute inset-y-0 right-0 z-10 w-16 bg-gradient-to-l from-void to-transparent" />
      <div className="ticker-track">
        {[0, 1].map((dup) => (
          <div key={dup} className="flex items-center">
            {ENTRIES.map((item, i) => (
              <Entry key={`${dup}-${i}`} item={item} />
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}
