import { AGENTS, AGENT_ORDER, type RunView } from "../agents";
import type { AgentActivity, AgentName as Name } from "../api";
import { AgentBadge, AgentName, EmptyState } from "./Primitives";

interface Summary {
  agent: Name;
  invocations: AgentActivity[];
  tools: string[];
  requestedBy: string[];
  delegatedTo: string[];
  live: boolean;
  liveTools: string[];
}

export function AgentSummaries({ view }: { view: RunView }) {
  if (!view.runId) {
    return (
      <section className="panel agents" aria-label="Agent summaries">
        <div className="panel__head"><h2>Agent summaries</h2></div>
        <EmptyState title="No agents dispatched yet" hint="Run the team on this ticket to see who did what." />
      </section>
    );
  }

  // Tools seen live in the event stream (covers agents that are still working).
  const liveTools = new Map<string, Set<string>>();
  view.events.forEach((e) => {
    if (e.event === "mcp_tool_call" && e.agent && e.tool) {
      if (!liveTools.has(e.agent)) liveTools.set(e.agent, new Set());
      liveTools.get(e.agent)!.add(e.tool);
    }
  });

  const summaries: Summary[] = AGENT_ORDER.filter((a) => view.involved.has(a) || liveTools.has(a)).map((agent) => {
    const inv = view.activity.filter((x) => x.agent === agent);
    const tools = new Set<string>([...inv.flatMap((x) => x.tools_used), ...(liveTools.get(agent) ?? [])]);
    return {
      agent,
      invocations: inv,
      tools: [...tools].sort(),
      requestedBy: [...new Set(inv.map((x) => x.requested_by).filter(Boolean) as string[])],
      delegatedTo: [...new Set(inv.flatMap((x) => x.delegated_to))],
      live: view.activeAgents.has(agent),
      liveTools: [...(liveTools.get(agent) ?? [])],
    };
  });

  return (
    <section className="panel agents" aria-label="Agent summaries">
      <div className="panel__head">
        <h2>Agent summaries</h2>
        <span className="panel__count">{summaries.length} agents</span>
      </div>
      <div className="agent-grid">
        {summaries.map((s, i) => {
          const m = AGENTS[s.agent];
          const said = s.invocations.map((x) => x.said).filter(Boolean) as string[];
          return (
            <article key={s.agent} className={`agent-card ${s.live ? "is-live" : ""}`}
              style={{ ["--agent" as string]: m.color, animationDelay: `${i * 60}ms` }}>
              <header className="agent-card__head">
                <AgentBadge agent={s.agent} size={34} pulse={s.live} />
                <div>
                  <AgentName agent={s.agent} />
                  <div className="agent-card__role">{m.role}</div>
                </div>
                <span className="agent-card__state">
                  {s.live ? "Working…" : s.invocations.some((x) => x.status === "failed" || x.status === "blocked") ? "Stopped" : "Done"}
                </span>
              </header>

              <div className="agent-card__said">
                {said.length ? said.map((t, j) => <p key={j}>{t}</p>) : <p className="muted">{s.live ? "Gathering facts…" : "No report recorded."}</p>}
              </div>

              <div className="agent-card__foot">
                {s.requestedBy.length > 0 && <span className="agent-card__rel">asked by {s.requestedBy.map((a) => AGENTS[a as Name]?.label ?? a).join(", ")}</span>}
                {s.delegatedTo.length > 0 && <span className="agent-card__rel">delegated to {s.delegatedTo.map((a) => AGENTS[a as Name]?.label ?? a).join(", ")}</span>}
                <div className="tools">
                  {s.tools.length ? s.tools.map((t) => <code key={t} className="tool">{t}</code>) : <span className="muted">no MCP tools</span>}
                </div>
              </div>
            </article>
          );
        })}
      </div>
    </section>
  );
}
