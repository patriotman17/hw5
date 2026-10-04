import type { AuditEvent } from "../api";
import { AGENTS } from "../agents";
import { AgentBadge, EmptyState, Spinner } from "./Primitives";

const label = (a: string | null | undefined) => (a && a in AGENTS ? AGENTS[a as keyof typeof AGENTS].label : a ?? "System");

function describe(e: AuditEvent): { title: string; body?: string; tone?: "good" | "bad" | "tool" | "hand" } {
  switch (e.event) {
    case "ticket_run_started": return { title: "Boss took the ticket", tone: "hand" };
    case "mcp_tool_call": return { title: `${label(e.agent)} called`, body: e.tool, tone: "tool" };
    case "mcp_tool_error": return { title: `${label(e.agent)} tool error`, body: `${e.tool}: ${e.error}`, tone: "bad" };
    case "mcp_tool_blocked": return { title: `${label(e.agent)} blocked from a tool`, body: e.tool, tone: "bad" };
    case "delegation_started": return { title: `${label(e.agent)} → ${label(e.to_agent)}`, body: e.task, tone: "hand" };
    case "delegation_completed": return { title: `${label(e.to_agent)} reported to ${label(e.agent)}`, body: e.summary, tone: "good" };
    case "delegation_cache_hit": return { title: `${label(e.agent)} reused ${label(e.to_agent)}'s report`, tone: "hand" };
    case "delegation_failed":
    case "delegation_blocked": return { title: `${label(e.agent)} → ${label(e.to_agent)} ${e.event === "delegation_failed" ? "failed" : "blocked"}`, body: e.error ?? e.reason, tone: "bad" };
    case "output_rejected": return { title: `${label(e.agent)}'s answer sent back by a rule check`, body: e.reason, tone: "bad" };
    case "ticket_run_completed": return { title: "Boss decided", body: e.recommendation, tone: "good" };
    case "ticket_run_failed": return { title: "Run failed", body: e.error, tone: "bad" };
    case "payment_approval_requested": return { title: "Approval requested", body: `${e.kind} #${e.ref_id}`, tone: "hand" };
    default: return { title: e.event.replaceAll("_", " ") };
  }
}

const time = (ts: string) => new Date(ts).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });

export function EventFeed({ events, live, loading, error }: { events: AuditEvent[]; live: boolean; loading: boolean; error: string | null }) {
  const items = [...events].reverse().slice(0, 80);
  return (
    <aside className="panel feed" aria-label="Live event feed">
      <div className="panel__head">
        <h2>Event feed</h2>
        {live ? <span className="live-pill"><i />Live</span> : <span className="panel__count">{events.length}</span>}
      </div>
      {error && <div className="alert alert--error">{error}</div>}
      {loading && !events.length && <div className="loading-row"><Spinner /> Loading events…</div>}
      {!loading && !events.length && !error && <EmptyState title="Silence on the deck" hint="Events appear here as agents work." />}
      <ol className="feed__list" aria-live="polite">
        {items.map((e) => {
          const d = describe(e);
          return (
            <li key={e.seq} className={`feed__item feed__item--${d.tone ?? "plain"}`}
              style={{ ["--agent" as string]: AGENTS[(e.to_agent && e.event === "delegation_completed" ? e.to_agent : e.agent) as keyof typeof AGENTS]?.color ?? "#6d6a75" }}>
              <AgentBadge agent={e.event === "delegation_completed" ? e.to_agent : e.agent} size={24} />
              <div className="feed__text">
                <div className="feed__title">
                  {d.title} {d.tone === "tool" && d.body && <code className="tool">{d.body}</code>}
                </div>
                {d.body && d.tone !== "tool" && <div className="feed__body">{d.body}</div>}
              </div>
              <time className="feed__time">{time(e.timestamp)}</time>
            </li>
          );
        })}
      </ol>
    </aside>
  );
}
