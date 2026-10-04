import type { Ticket } from "../api";
import { EmptyState, Spinner, StatusChip } from "./Primitives";

const TYPE_LABEL: Record<string, string> = {
  customer_order: "Customer order",
  rent_notice: "Rent notice",
  price_override: "Price override",
};

interface Props {
  tickets: Ticket[] | null;
  error: string | null;
  selectedId: number | null;
  runningIds: Set<number>;
  onSelect: (id: number) => void;
}

export function TicketList({ tickets, error, selectedId, runningIds, onSelect }: Props) {
  return (
    <aside className="panel tickets" aria-label="Tickets">
      <div className="panel__head">
        <h2>Ticket queue</h2>
        {tickets && <span className="panel__count">{tickets.length}</span>}
      </div>

      {error && <div className="alert alert--error">{error}</div>}
      {!tickets && !error && <div className="loading-row"><Spinner /> Loading tickets…</div>}
      {tickets?.length === 0 && <EmptyState title="No tickets" />}

      <ul className="ticket-list">
        {tickets?.map((t, i) => {
          const running = t.running || runningIds.has(t.id);
          const waiting = t.pending_payments.filter((p) => p.state === "awaiting_approval").length;
          return (
            <li key={t.id} style={{ animationDelay: `${i * 70}ms` }}>
              <button
                className={`ticket-card ticket-card--${t.status} ${selectedId === t.id ? "is-selected" : ""} ${running ? "is-running" : ""}`}
                onClick={() => onSelect(t.id)}
                aria-pressed={selectedId === t.id}
              >
                <div className="ticket-card__top">
                  <span className="ticket-card__id">#{t.id}</span>
                  <StatusChip status={t.status} running={running} />
                </div>
                <div className="ticket-card__subject">{t.subject}</div>
                <div className="ticket-card__meta">
                  <span>{TYPE_LABEL[t.type] ?? t.type}</span>
                  <span>·</span>
                  <span>{t.requester}</span>
                </div>
                <div className="ticket-card__tags">
                  {t.sku && <span className="tag">{t.sku}</span>}
                  {t.size && <span className="tag">size {t.size}</span>}
                  {t.qty != null && <span className="tag">qty {t.qty}</span>}
                  {t.lease_id != null && <span className="tag">lease {t.lease_id}</span>}
                  {t.invoice_id != null && <span className="tag">inv {t.invoice_id}</span>}
                </div>
                {waiting > 0 && !running && (
                  <div className="ticket-card__alert">⚠ {waiting} payment{waiting > 1 ? "s" : ""} awaiting approval</div>
                )}
                {running && <div className="ticket-card__progress" aria-hidden="true" />}
              </button>
            </li>
          );
        })}
      </ul>
    </aside>
  );
}
