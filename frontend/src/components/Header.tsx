import { useEffect, useState } from "react";
import { isHumanName, money, type Cash } from "../api";
import { AnimatedNumber, HelmetLogo, Spinner } from "./Primitives";

interface Props {
  operator: string;
  onOperator: (name: string) => void;
  cash: Cash | null;
  cashError: string | null;
  onReset: () => Promise<void>;
  resetting: boolean;
  anyRunning: boolean;
}

export function Header({ operator, onOperator, cash, cashError, onReset, resetting, anyRunning }: Props) {
  const [armed, setArmed] = useState(false);
  useEffect(() => {
    if (!armed) return;
    const t = setTimeout(() => setArmed(false), 4000);
    return () => clearTimeout(t);
  }, [armed]);

  const low = cash != null && cash.balance < 500;

  return (
    <header className="header">
      <div className="header__brand">
        <HelmetLogo size={46} />
        <div>
          <h1 className="header__title">Campus Customs <span>Sith Ops</span></h1>
          <p className="header__sub">
            Agent command deck · desk date <b>{cash?.desk_date ?? "…"}</b>
          </p>
        </div>
      </div>

      <div className="header__right">
        <label className={`operator ${operator && !isHumanName(operator) ? "is-invalid" : ""}`}>
          <span>Human operator</span>
          <input value={operator} placeholder="Your name" onChange={(e) => onOperator(e.target.value)} />
        </label>
        <div className={`cash ${low ? "cash--low" : ""}`} aria-live="polite">
          <span className="cash__label">Checking balance</span>
          <span className="cash__value">
            {cash ? <AnimatedNumber value={cash.balance} format={money} /> : cashError ? "—" : <Spinner />}
          </span>
          <span className="cash__meta">
            {cashError
              ? cashError
              : cash
                ? `Open invoices ${money(cash.open_invoice_total)} · as of ${cash.as_of}`
                : "Loading…"}
          </span>
        </div>

        <button
          className={`btn btn--reset ${armed ? "btn--armed" : ""}`}
          disabled={resetting || anyRunning}
          title={anyRunning ? "Wait for running tickets to finish" : "Restore the shop database to its original values"}
          onClick={async () => {
            if (!armed) return setArmed(true);
            setArmed(false);
            await onReset();
          }}
        >
          {resetting ? <><Spinner /> Resetting…</> : armed ? "Confirm reset?" : "Reset shop"}
        </button>
      </div>
      <div className="header__saber" aria-hidden="true" />
    </header>
  );
}
