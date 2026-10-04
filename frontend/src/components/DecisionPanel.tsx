import { useState } from "react";
import { api, ApiError, isHumanName, type Decision, type Ticket } from "../api";
import { Spinner } from "./Primitives";

interface Props {
  decision: Decision;
  ticket: Ticket;
  operator: string;
  onChanged: (message: string, tone: "ok" | "warn" | "error") => Promise<void>;
}

const defaultNote = (action: string) =>
  /draft/i.test(action)
    ? "Reviewed and approved the draft for the owner to send. Not sent by the system."
    : "";

export function DecisionPanel({ decision, ticket, operator, onChanged }: Props) {
  const [open, setOpen] = useState(false);
  const [notes, setNotes] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const checks = decision.rule_checks ?? [];
  const outstanding = ticket.outstanding_actions;
  const signed = ticket.signed_off_actions ?? [];
  const waiting = ticket.waiting_actions ?? [];
  const canSign = isHumanName(operator) && !!ticket.latest_run;

  const signOff = async (action: string) => {
    const note = (notes[action] ?? defaultNote(action)).trim();
    setBusy(action);
    setError(null);
    try {
      const t = await api.signOff(ticket.id, {
        run_id: ticket.latest_run!.run_id, action, signed_off_by: operator.trim(), note,
      });
      await onChanged(`Signed off: ${action.slice(0, 70)}… — ticket is now ${t.status}.`, t.status === "resolved" ? "ok" : "warn");
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : String(e);
      setError(msg);
      await onChanged(msg, "error");
    } finally {
      setBusy(null);
    }
  };

  return (
    <section className="panel decision" aria-label="Boss decision">
      <div className="panel__head">
        <h2>Boss decision</h2>
        <span className="decision__badge">Recommendation · pending human review</span>
      </div>

      <p className="decision__rec">{decision.recommendation}</p>

      {(outstanding.length > 0 || signed.length > 0) && (
        <div className="decision__block">
          <h3>Human actions {outstanding.length ? `· ${outstanding.length} to sign off` : "· all signed off"}</h3>
          {outstanding.length > 0 && !canSign && (
            <div className="alert alert--warn">Enter your name as <b>Human operator</b> in the header to sign off actions.</div>
          )}
          <ul className="signoffs">
            {outstanding.map((a) => (
              <li key={a} className="signoff">
                <p className="signoff__action">{a}</p>
                <div className="signoff__row">
                  <input
                    className="signoff__note"
                    placeholder="What did you decide or do?"
                    value={notes[a] ?? defaultNote(a)}
                    onChange={(e) => setNotes((n) => ({ ...n, [a]: e.target.value }))}
                  />
                  <button
                    className="btn btn--approve"
                    disabled={!canSign || busy !== null || !(notes[a] ?? defaultNote(a)).trim()}
                    onClick={() => signOff(a)}
                  >
                    {busy === a ? <Spinner /> : "Sign off"}
                  </button>
                </div>
              </li>
            ))}
            {signed.map((s) => (
              <li key={s.action} className="signoff is-done">
                <p className="signoff__action">✓ {s.action}</p>
                <p className="signoff__by">{s.signed_off_by}: {s.note || "signed off"}</p>
              </li>
            ))}
          </ul>
          {error && <div className="alert alert--error">{error}</div>}
        </div>
      )}

      {waiting.length > 0 && (
        <div className="decision__block">
          <h3>Waiting on others · no sign-off needed now</h3>
          <ul className="signoffs">
            {waiting.map((w) => (
              <li key={w.action} className="signoff is-waiting">
                <p className="signoff__action">{w.action}</p>
                <p className="signoff__by">⏳ Waiting on: {w.waiting_on}</p>
              </li>
            ))}
          </ul>
        </div>
      )}

      {decision.drafts.length > 0 && (
        <div className="decision__block">
          <h3>Drafts</h3>
          {decision.drafts.map((d, i) => (
            <details key={i} className="draft">
              <summary>
                <span className="draft__stamp">Draft · not sent</span>
                <span className="draft__to">To {d.recipient} ({d.audience})</span>
                <span className="draft__subj">{d.subject}</span>
              </summary>
              <pre className="draft__body">{d.body}</pre>
            </details>
          ))}
        </div>
      )}

      {checks.length > 0 && (
        <div className="decision__rules">
          {checks.map((r, i) => (
            <span key={i} className={`rule rule--${r.status}`} title={r.note}>{r.rule}</span>
          ))}
        </div>
      )}

      <button className="btn btn--link" onClick={() => setOpen((o) => !o)}>
        {open ? "Hide rationale & facts" : "Show rationale & facts"}
      </button>
      {open && (
        <div className="decision__more">
          <p>{decision.rationale}</p>
          <ul className="facts">
            {decision.facts.map((f, i) => (
              <li key={i}><span>{f.statement}</span><code>{f.source}</code></li>
            ))}
          </ul>
          {decision.missing_data.length > 0 && (
            <>
              <h3>Missing data (not invented)</h3>
              <ul>{decision.missing_data.map((m, i) => <li key={i}>{m}</li>)}</ul>
            </>
          )}
        </div>
      )}
    </section>
  );
}
