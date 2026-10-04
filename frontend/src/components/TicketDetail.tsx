import type { ApprovalRequest, Ticket } from "../api";
import type { RunView } from "../agents";
import { AgentSummaries } from "./AgentSummaries";
import { ApprovalPanel } from "./ApprovalPanel";
import { DecisionPanel } from "./DecisionPanel";
import { DelegationFlow } from "./DelegationFlow";
import { Spinner, StatusChip } from "./Primitives";

interface Props {
  ticket: Ticket;
  operator: string;
  view: RunView;
  running: boolean;
  requests: ApprovalRequest[];
  onRun: () => void;
  onChanged: (message: string, tone: "ok" | "warn" | "error") => Promise<void>;
}

export function TicketDetail({ ticket, operator, view, running, requests, onRun, onChanged }: Props) {
  return (
    <main className="detail">
      <section className={`panel hero hero--${running ? "running" : ticket.status}`}>
        <div className="hero__info">
          <div className="hero__kicker">
            Ticket #{ticket.id} · {ticket.type.replace("_", " ")} · from {ticket.requester}
          </div>
          <h2 className="hero__title">{ticket.subject}</h2>
          {ticket.notes && <p className="hero__notes">“{ticket.notes}”</p>}
          <div className="hero__status">
            <StatusChip status={ticket.status} running={running} />
            <span className="hero__reason">{running ? "The agent team is working this ticket…" : ticket.status_reason}</span>
          </div>
        </div>

        <button className={`btn btn--saber ${running ? "is-running" : ""}`} onClick={onRun} disabled={running}>
          <span className="btn--saber__blade" aria-hidden="true" />
          {running ? <><Spinner /> Agents at work</> : ticket.latest_run ? "Run the team again" : "Dispatch the agent team"}
        </button>
        {view.usage && !running && (
          <div className="hero__usage">
            Last run · {view.usage.total_tokens.toLocaleString()} tokens · {view.usage.requests} model calls · {view.usage.tool_calls} tool calls
          </div>
        )}
      </section>

      {view.failed && !running && <div className="alert alert--error">Last run failed: {view.failed}</div>}

      <DelegationFlow view={view} />
      <ApprovalPanel ticket={ticket} operator={operator} requests={requests} onChanged={onChanged} />
      {view.decision && !view.running && (
        <DecisionPanel decision={view.decision} ticket={ticket} operator={operator} onChanged={onChanged} />
      )}
      <AgentSummaries view={view} />
    </main>
  );
}
