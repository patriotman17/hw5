import { AGENTS, AGENT_ORDER, type Edge, type RunView } from "../agents";
import type { AgentName } from "../api";

const POS: Record<AgentName, { x: number; y: number }> = {
  boss: { x: 320, y: 62 },
  inventory: { x: 92, y: 214 },
  accounting: { x: 246, y: 250 },
  facilities: { x: 394, y: 250 },
  customer_service: { x: 548, y: 214 },
};
const R = 29;

function edgePath(e: Edge, nth: number) {
  const a = POS[e.from], b = POS[e.to];
  const mx = (a.x + b.x) / 2, my = (a.y + b.y) / 2;
  const dx = b.x - a.x, dy = b.y - a.y;
  const len = Math.hypot(dx, dy) || 1;
  // Bend each repeated edge a little more so parallel delegations stay visible.
  const bend = 26 + nth * 22;
  const cx = mx - (dy / len) * bend, cy = my + (dx / len) * bend;
  return `M ${a.x} ${a.y} Q ${cx} ${cy} ${b.x} ${b.y}`;
}

export function DelegationFlow({ view }: { view: RunView }) {
  const seen = new Map<string, number>();
  const edges = view.edges.map((e) => {
    const k = `${e.from}-${e.to}`;
    const nth = seen.get(k) ?? 0;
    seen.set(k, nth + 1);
    return { ...e, d: edgePath(e, nth) };
  });
  const active = edges.filter((e) => e.state === "active").length;

  return (
    <section className="panel flow" aria-label="Delegation flow">
      <div className="panel__head">
        <h2>Delegation flow</h2>
        <span className="flow__legend">
          {view.runId ? (
            <>
              {edges.length} delegation{edges.length === 1 ? "" : "s"}
              {active > 0 && <b className="flow__live"> · {active} in flight</b>}
            </>
          ) : (
            "No run yet"
          )}
        </span>
      </div>

      <svg className="flow__svg" viewBox="0 0 640 300" role="img" aria-label="Agents and the delegations between them">
        <defs>
          <filter id="flow-glow" x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation="3.2" result="b" />
            <feMerge><feMergeNode in="b" /><feMergeNode in="SourceGraphic" /></feMerge>
          </filter>
          {edges.map((e) => (
            <linearGradient key={e.id} id={`g-${e.id}`} gradientUnits="userSpaceOnUse"
              x1={POS[e.from].x} y1={POS[e.from].y} x2={POS[e.to].x} y2={POS[e.to].y}>
              <stop offset="0" stopColor={AGENTS[e.from].color} />
              <stop offset="1" stopColor={AGENTS[e.to].color} />
            </linearGradient>
          ))}
        </defs>

        {/* faint lattice of every possible link: full connectivity */}
        <g className="flow__lattice">
          {AGENT_ORDER.flatMap((a, i) =>
            AGENT_ORDER.slice(i + 1).map((b) => (
              <line key={`${a}${b}`} x1={POS[a].x} y1={POS[a].y} x2={POS[b].x} y2={POS[b].y} />
            )),
          )}
        </g>

        {edges.map((e) => (
          <g key={e.id} className={`flow__edge flow__edge--${e.state}`}>
            <title>{`${AGENTS[e.from].label} → ${AGENTS[e.to].label}${e.task ? `: ${e.task}` : ""}`}</title>
            <path d={e.d} className="flow__edge-base" stroke={`url(#g-${e.id})`} />
            <path d={e.d} className="flow__edge-flow" stroke={`url(#g-${e.id})`} filter="url(#flow-glow)" />
            {e.state === "active" && (
              <circle r="4.5" className="flow__particle" fill={AGENTS[e.to].color} filter="url(#flow-glow)">
                <animateMotion dur="1.4s" repeatCount="indefinite" path={e.d} />
              </circle>
            )}
          </g>
        ))}

        {AGENT_ORDER.map((name) => {
          const m = AGENTS[name], p = POS[name];
          const isActive = view.activeAgents.has(name);
          const involved = view.involved.has(name) || !view.runId;
          return (
            <g key={name} className={`flow__node ${isActive ? "is-active" : ""} ${involved ? "" : "is-idle"}`}
              transform={`translate(${p.x} ${p.y})`} style={{ ["--agent" as string]: m.color }}>
              {isActive && <circle r={R + 6} className="flow__pulse" />}
              <circle r={R} className="flow__disc" />
              <circle r={R} className="flow__ring" />
              <path d={m.glyph} transform="translate(-13 -13) scale(1.08)" className="flow__glyph" />
              <text y={R + 17} className="flow__label">{m.label}</text>
            </g>
          );
        })}
      </svg>
    </section>
  );
}
