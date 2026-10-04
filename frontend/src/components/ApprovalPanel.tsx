import { useState } from "react";
import { api, ApiError, isHumanName, money, type ApprovalRequest, type PendingPayment, type Ticket } from "../api";
import { Spinner } from "./Primitives";

interface Props {
  ticket: Ticket;
  operator: string;
  requests: ApprovalRequest[];
  onChanged: (message: string, tone: "ok" | "warn" | "error") => Promise<void>;
}

const STATE_LABEL: Record<PendingPayment["state"], string> = {
  awaiting_approval: "Awaiting approval",
  approved: "Approved & paid",
  declined: "Declined",
  refused: "Refused (insufficient cash)",
};

export function ApprovalPanel({ ticket, operator: approver, requests, onChanged }: Props) {
  const [busy, setBusy] = useState<string | null>(null);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [confirmed, setConfirmed] = useState<Record<string, boolean>>({});

  const payments = ticket.pending_payments;
  if (payments.length === 0) return null;

  const awaiting = payments.filter((p) => p.state === "awaiting_approval").length;
  const approverValid = isHumanName(approver);
  const keyOf = (p: { kind: string; ref_id: number }) => `${p.kind}:${p.ref_id}`;
  const pendingReq = (p: PendingPayment) =>
    requests.find((r) => r.status === "pending" && r.kind === p.kind && r.ref_id === p.ref_id);

  const act = async (key: string, fn: () => Promise<{ msg: string; tone: "ok" | "warn" }>) => {
    setBusy(key);
    setErrors((e) => ({ ...e, [key]: "" }));
    try {
      const { msg, tone } = await fn();
      await onChanged(msg, tone);
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : String(err);
      setErrors((e) => ({ ...e, [key]: msg }));
      await onChanged(msg, "error");
    } finally {
      setBusy(null);
    }
  };

  return (
    <section className={`panel approvals ${awaiting ? "approvals--hot" : ""}`} aria-label="Payment approvals">
      <div className="panel__head">
        <h2>Human approval</h2>
        <span className={`approvals__count ${awaiting ? "is-hot" : ""}`}>
          {awaiting ? `${awaiting} awaiting` : "All decided"}
        </span>
      </div>
      <p className="approvals__note">
        Agents can only <b>propose</b> payments. Nothing is paid until a named human approves it here; the MCP
        payment tool refuses anything that would make cash negative.
      </p>

      {awaiting > 0 && !approverValid && (
        <div className="alert alert--warn">Enter your name as <b>Human operator</b> in the header to approve or decline.</div>
      )}

      <div className="approvals__list">
        {payments.map((p) => {
          const key = keyOf(p);
          const req = pendingReq(p);
          const amount = req?.amount ?? p.amount;
          return (
            <article key={key} className={`pay-card pay-card--${p.state}`}>
              <div className="pay-card__main">
                <div>
                  <div className="pay-card__title">
                    {p.kind === "rent" ? "Rent" : "Invoice"} #{p.ref_id} · {p.payee ?? req?.payee}
                  </div>
                  <div className="pay-card__state">{STATE_LABEL[p.state]}{p.decided_by ? ` · ${p.decided_by}` : ""}</div>
                </div>
                <div className="pay-card__amount">{money(amount)}</div>
              </div>

              {req && (
                <div className="pay-card__impact">
                  <span>Cash {money(req.cash_before)}</span>
                  <span className="pay-card__arrow">→</span>
                  <b>{money(req.cash_after)}</b>
                  <div className="pay-card__bar">
                    <i style={{ width: `${Math.max(2, (req.cash_after / Math.max(req.cash_before, 1)) * 100)}%` }} />
                  </div>
                </div>
              )}

              {p.state === "awaiting_approval" && (
                <div className="pay-card__actions">
                  {!req ? (
                    <button
                      className="btn btn--ghost"
                      disabled={busy !== null}
                      onClick={() => act(key, async () => {
                        await api.createApproval({
                          kind: p.kind, ref_id: p.ref_id, ticket_id: ticket.id, run_id: ticket.latest_run?.run_id,
                        });
                        return { msg: `Approval request opened for ${p.kind} #${p.ref_id}.`, tone: "ok" };
                      })}
                    >
                      {busy === key ? <Spinner /> : "Open approval request"}
                    </button>
                  ) : (
                    <>
                      <label className="pay-card__confirm">
                        <input
                          type="checkbox"
                          checked={!!confirmed[req.id]}
                          onChange={(e) => setConfirmed((c) => ({ ...c, [req.id]: e.target.checked }))}
                        />
                        I approve paying {money(req.amount)} to {req.payee}
                      </label>
                      <div className="pay-card__buttons">
                        <button
                          className="btn btn--approve"
                          disabled={busy !== null || !approverValid || !confirmed[req.id]}
                          onClick={() => act(key, async () => {
                            const r = await api.approve(req.id, approver.trim());
                            return { msg: `Paid ${money(req.amount)} to ${req.payee}. Cash now ${money(r.cash.balance_after)}.`, tone: "ok" };
                          })}
                        >
                          {busy === key ? <Spinner /> : "Approve & pay"}
                        </button>
                        <button
                          className="btn btn--decline"
                          disabled={busy !== null || !approverValid}
                          onClick={() => act(key, async () => {
                            await api.decline(req.id, approver.trim());
                            return { msg: `Declined ${p.kind} #${p.ref_id}. Nothing was paid.`, tone: "warn" };
                          })}
                        >
                          Decline
                        </button>
                      </div>
                    </>
                  )}
                </div>
              )}
              {errors[key] && <div className="alert alert--error">{errors[key]}</div>}
            </article>
          );
        })}
      </div>
    </section>
  );
}
