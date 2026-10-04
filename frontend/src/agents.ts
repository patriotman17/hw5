import type { AgentActivity, AgentName, AuditEvent, Decision } from "./api";

export interface AgentMeta {
  name: AgentName;
  label: string;
  role: string;
  color: string;
  glyph: string; // single SVG path, 24x24 box
}

// Each agent gets its own hue and glyph so it is recognisable everywhere it appears.
export const AGENTS: Record<AgentName, AgentMeta> = {
  boss: {
    name: "boss", label: "Boss", role: "Owns the ticket · final call", color: "#ff2b3f",
    glyph: "M4 17 L6 7 L10 11 L12 5 L14 11 L18 7 L20 17 Z M5 19 H19",
  },
  inventory: {
    name: "inventory", label: "Inventory", role: "Stock · sizes · restock", color: "#ff8a3d",
    glyph: "M3 8 L12 3 L21 8 V17 L12 22 L3 17 Z M3 8 L12 13 L21 8 M12 13 V22",
  },
  accounting: {
    name: "accounting", label: "Accounting", role: "Cash · invoices · margins", color: "#e9c46a",
    glyph: "M12 3 V21 M16.5 7 C16.5 5 14.5 4.5 12 4.5 C9.5 4.5 7.5 5.8 7.5 7.8 C7.5 12 16.5 10 16.5 15 C16.5 17.4 14.4 18.6 12 18.6 C9.4 18.6 7.4 17.6 7.2 15.4",
  },
  facilities: {
    name: "facilities", label: "Facilities", role: "Lease · rent · landlord", color: "#a78bfa",
    glyph: "M3 11 L12 4 L21 11 M5 9.5 V20 H19 V9.5 M10 20 V14 H14 V20",
  },
  customer_service: {
    name: "customer_service", label: "Customer Service", role: "Drafts · customer impact", color: "#3dd6d0",
    glyph: "M4 5 H20 V16 H11 L6 20 V16 H4 Z M8 9.5 H16 M8 12.5 H13",
  },
};

export const AGENT_ORDER: AgentName[] = ["boss", "inventory", "accounting", "facilities", "customer_service"];

export const agentMeta = (a: string | null | undefined): AgentMeta | null =>
  a && a in AGENTS ? AGENTS[a as AgentName] : null;

export interface Edge {
  id: string;
  from: AgentName;
  to: AgentName;
  task?: string;
  state: "active" | "done" | "failed";
}

export interface RunView {
  runId: string | null;
  running: boolean;
  failed: string | null;
  events: AuditEvent[];
  edges: Edge[];
  activeAgents: Set<AgentName>;
  involved: Set<AgentName>;
  activity: AgentActivity[];
  decision: Decision | null;
  usage: AuditEvent["usage"] | null;
}

/** Derive the latest run for a ticket from its recent audit events. */
export function buildRunView(events: AuditEvent[], activity: AgentActivity[]): RunView {
  const start = [...events].reverse().find((e) => e.event === "ticket_run_started");
  const empty: RunView = {
    runId: null, running: false, failed: null, events: [], edges: [], activeAgents: new Set(),
    involved: new Set(), activity: [], decision: null, usage: null,
  };
  if (!start) return empty;

  const runEvents = events.filter((e) => e.run_id === start.run_id);
  const done = runEvents.find((e) => e.event === "ticket_run_completed");
  const failed = runEvents.find((e) => e.event === "ticket_run_failed");

  // Pair each delegation_started with the first matching finish after it.
  const finishes = runEvents.filter((e) =>
    ["delegation_completed", "delegation_failed", "delegation_blocked"].includes(e.event),
  );
  const used = new Set<number>();
  const edges: Edge[] = [];
  for (const e of runEvents) {
    if (e.event !== "delegation_started" || !e.agent || !e.to_agent) continue;
    const fin = finishes.find(
      (f) => !used.has(f.seq) && f.seq > e.seq && f.agent === e.agent && f.to_agent === e.to_agent,
    );
    if (fin) used.add(fin.seq);
    edges.push({
      id: `${e.seq}`, from: e.agent, to: e.to_agent, task: e.task,
      state: !fin ? (done || failed ? "failed" : "active") : fin.event === "delegation_completed" ? "done" : "failed",
    });
  }
  // Blocked delegations never "start"; still show them.
  for (const f of finishes) {
    if (f.event === "delegation_blocked" && f.agent && f.to_agent) {
      edges.push({ id: `b${f.seq}`, from: f.agent, to: f.to_agent, task: f.task, state: "failed" });
    }
  }

  const running = !done && !failed;
  const activeAgents = new Set<AgentName>();
  if (running) {
    activeAgents.add("boss");
    edges.filter((x) => x.state === "active").forEach((x) => activeAgents.add(x.to));
  }
  const involved = new Set<AgentName>(["boss"]);
  edges.forEach((x) => { involved.add(x.from); involved.add(x.to); });

  return {
    runId: start.run_id,
    running,
    failed: failed?.error ?? null,
    events: runEvents,
    edges,
    activeAgents,
    involved,
    activity: activity.filter((a) => a.run_id === start.run_id),
    decision: done?.decision ?? null,
    usage: done?.usage ?? null,
  };
}
