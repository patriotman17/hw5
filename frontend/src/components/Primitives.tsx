import { useEffect, useRef, useState } from "react";
import type { TicketStatus } from "../api";
import { agentMeta } from "../agents";

/** Original inline-SVG Sith helmet (drawn from simple shapes; no franchise artwork). */
export function HelmetLogo({ size = 44, glow = true }: { size?: number; glow?: boolean }) {
  return (
    <svg className={`helmet ${glow ? "helmet--glow" : ""}`} width={size} height={size} viewBox="0 0 100 100" aria-hidden="true">
      <defs>
        <linearGradient id="hl-dome" x1="0" y1="0" x2="0.35" y2="1">
          <stop offset="0" stopColor="#4a4b55" />
          <stop offset="0.35" stopColor="#17171c" />
          <stop offset="1" stopColor="#050506" />
        </linearGradient>
        <linearGradient id="hl-eye" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#ff5a68" />
          <stop offset="1" stopColor="#7a0612" />
        </linearGradient>
      </defs>
      {/* dome + flared skirt */}
      <path
        d="M50 7 C33 7 24 17 22 33 L20 47 C19 50 18 52 16 55 C10 63 6 70 4 77 C8 83 13 88 18 92 C20 84 24 78 31 73 L38 92 L50 98 L62 92 L69 73 C76 78 80 84 82 92 C87 88 92 83 96 77 C94 70 90 63 84 55 C82 52 81 50 80 47 L78 33 C76 17 67 7 50 7 Z"
        fill="url(#hl-dome)" stroke="#e0182d" strokeWidth="1.3" strokeLinejoin="round"
      />
      {/* center ridge */}
      <path d="M47.2 8 L47.6 44 L46.4 49 M52.8 8 L52.4 44 L53.6 49" stroke="#5c5d68" strokeWidth="1" fill="none" />
      {/* brow */}
      <path d="M27 51 C35 44 43 44 47 49 M73 51 C65 44 57 44 53 49" stroke="#b9bac4" strokeOpacity=".55" strokeWidth="1.4" fill="none" strokeLinecap="round" />
      {/* eyes */}
      <path className="helmet__eye" d="M31 53 C37 50 43 51 47 56 L44 61 C39 60 34 59 31 57 Z" fill="url(#hl-eye)" />
      <path className="helmet__eye" d="M69 53 C63 50 57 51 53 56 L56 61 C61 60 66 59 69 57 Z" fill="url(#hl-eye)" />
      {/* cheek lines */}
      <path d="M33 64 C37 65 41 66 44 65 M67 64 C63 65 59 66 56 65" stroke="#8d8e98" strokeOpacity=".6" strokeWidth="1.1" fill="none" />
      {/* mouth grille */}
      <path d="M50 64 L39 80 L61 80 Z" fill="#0b0b0e" stroke="#9a9ba5" strokeOpacity=".7" strokeWidth="1" strokeLinejoin="round" />
      <g stroke="#e0182d" strokeWidth="1.3" strokeLinecap="round">
        <path d="M45 75 V79 M48.3 71 V79 M51.7 71 V79 M55 75 V79" />
      </g>
      <path d="M40 84 H60 L50 90 Z" fill="#111115" stroke="#6d6e78" strokeWidth=".8" />
    </svg>
  );
}

export function AgentBadge({ agent, size = 30, pulse = false }: { agent: string | null | undefined; size?: number; pulse?: boolean }) {
  const meta = agentMeta(agent);
  if (!meta) return <span className="agent-badge agent-badge--system" style={{ width: size, height: size }}>◆</span>;
  return (
    <span
      className={`agent-badge ${pulse ? "agent-badge--pulse" : ""}`}
      style={{ width: size, height: size, ["--agent" as string]: meta.color }}
      title={meta.label}
    >
      <svg viewBox="0 0 24 24" width={size * 0.58} height={size * 0.58} aria-hidden="true">
        <path d={meta.glyph} fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    </span>
  );
}

export function AgentName({ agent }: { agent: string | null | undefined }) {
  const meta = agentMeta(agent);
  return <span className="agent-name" style={{ ["--agent" as string]: meta?.color ?? "#9b97a0" }}>{meta?.label ?? agent ?? "system"}</span>;
}

const STATUS_LABEL: Record<TicketStatus, string> = { open: "Open", pending: "Pending", resolved: "Resolved" };

export function StatusChip({ status, running = false }: { status: TicketStatus; running?: boolean }) {
  if (running) return <span className="chip chip--running"><i className="chip__dot" />Running</span>;
  return <span className={`chip chip--${status}`}><i className="chip__dot" />{STATUS_LABEL[status]}</span>;
}

/** Smoothly tweens between numeric values (used for the cash balance). */
export function AnimatedNumber({ value, format }: { value: number; format: (n: number) => string }) {
  const [shown, setShown] = useState(value);
  const from = useRef(value);
  useEffect(() => {
    const start = performance.now();
    const a = from.current;
    const dur = 900;
    let raf = 0;
    const tick = (t: number) => {
      const p = Math.min(1, (t - start) / dur);
      const eased = 1 - Math.pow(1 - p, 3);
      setShown(a + (value - a) * eased);
      if (p < 1) raf = requestAnimationFrame(tick);
      else from.current = value;
    };
    raf = requestAnimationFrame(tick);
    return () => { cancelAnimationFrame(raf); from.current = value; };
  }, [value]);
  return <>{format(shown)}</>;
}

export function Spinner({ label }: { label?: string }) {
  return <span className="saber-spinner" role="status" aria-label={label ?? "Loading"}><i /></span>;
}

export function EmptyState({ title, hint }: { title: string; hint?: string }) {
  return (
    <div className="empty">
      <HelmetLogo size={34} glow={false} />
      <p className="empty__title">{title}</p>
      {hint && <p className="empty__hint">{hint}</p>}
    </div>
  );
}
