import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { api, ApiError, type Order, type OrderSummary } from "../api";
import { Icon } from "../components/Icon";
import { formatINR } from "../format";
import { Shell } from "../Shell";
import { when } from "./Videos";

type Filter = "new" | "packed" | "delivered" | "all";
const NEXT: Partial<Record<Order["status"], Order["status"]>> = { new: "packed", packed: "delivered" };

function OrderCard({ order, onChange }: { order: Order; onChange: (o: Order, s: OrderSummary) => void }) {
  const { t, i18n } = useTranslation();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const update = async (body: Record<string, unknown>) => {
    setBusy(true);
    setError("");
    try {
      const res = await api<{ order: Order; summary: OrderSummary }>(`/api/v1/orders/${order.id}`, { method: "PATCH", json: body });
      onChange(res.order, res.summary);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("app.offline"));
    } finally {
      setBusy(false);
    }
  };

  const next = NEXT[order.status];
  return (
    <article className={`order ${order.status}`} aria-labelledby={`o-${order.id}`}>
      <div className="order-head">
        <strong id={`o-${order.id}`}>{t("orders.number", { number: order.number })}</strong>
        <span className="muted small">{when(order.created_at, i18n.language)}</span>
      </div>
      <div className="row">
        <span className={order.status === "new" ? "pill warn" : order.status === "cancelled" ? "pill plain" : "pill"}>
          {t(`orders.status_${order.status}`)}
        </span>
        <span className={order.paid ? "pill" : "pill plain"}>{order.paid ? t("orders.paid") : t("orders.not_paid")}</span>
      </div>
      {order.customer_name || order.note ? (
        <p className="small">
          {order.customer_name ? <strong>{order.customer_name}</strong> : null}
          {order.customer_name && order.note ? ": " : null}
          {order.note}
        </p>
      ) : null}
      <ul className="order-lines list-plain">
        {order.items.map((line) => (
          <li key={line.id}>
            <span>{t("orders.line", { qty: line.qty, title: line.title })}</span>
            <span className="num">{formatINR(line.qty * line.price_inr)}</span>
          </li>
        ))}
      </ul>
      <div className="order-total">
        <span>{t("orders.total")}</span>
        <span className="num">{order.total_display}</span>
      </div>
      {order.status !== "cancelled" ? (
        <div className="row">
          {next ? (
            <button type="button" className="btn small primary" disabled={busy} onClick={() => void update({ status: next })}>
              <Icon name="check" size={18} />
              {t(`orders.mark_${next}`)}
            </button>
          ) : null}
          <button type="button" className="btn small" disabled={busy} onClick={() => void update({ paid: !order.paid })}>
            {order.paid ? t("orders.mark_unpaid") : t("orders.mark_paid")}
          </button>
          {order.status === "new" ? (
            <button type="button" className="btn small quiet" disabled={busy}
              onClick={() => window.confirm(t("orders.cancel_confirm")) && void update({ status: "cancelled" })}>
              {t("orders.cancel")}
            </button>
          ) : null}
        </div>
      ) : null}
      {error ? <p className="error" role="alert">{error}</p> : null}
    </article>
  );
}

export function Orders() {
  const { t } = useTranslation();
  const [filter, setFilter] = useState<Filter>("new");
  const [orders, setOrders] = useState<Order[] | null>(null);
  const [summary, setSummary] = useState<OrderSummary | null>(null);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      const data = await api<{ orders: Order[]; summary: OrderSummary }>(`/api/v1/orders?status=${filter}`);
      setOrders(data.orders);
      setSummary(data.summary);
      setError("");
    } catch {
      setError(t("app.offline"));
    }
  }, [filter, t]);

  useEffect(() => {
    void load();
    const timer = window.setInterval(() => void load(), 20_000);
    return () => window.clearInterval(timer);
  }, [load]);

  const changed = (order: Order, s: OrderSummary) => {
    setSummary(s);
    setOrders((list) => {
      if (!list) return list;
      const kept = filter === "all" || order.status === filter;
      return kept ? list.map((o) => (o.id === order.id ? order : o)) : list.filter((o) => o.id !== order.id);
    });
  };

  return (
    <Shell title={t("orders.title")}>
      {summary ? (
        <div className="ledger-strip" role="group" aria-label={t("orders.today")}>
          <div>
            <span className="num">{summary.today_orders}</span>
            <span className="label">{t("orders.today_count")}</span>
          </div>
          <div>
            <span className="num">{formatINR(summary.today_total_inr)}</span>
            <span className="label">{t("orders.today_sales")}</span>
          </div>
          <div>
            <span className="num">{formatINR(summary.today_paid_inr)}</span>
            <span className="label">{t("orders.today_paid")}</span>
          </div>
        </div>
      ) : null}
      <div className="chips" role="group" aria-label={t("orders.show")}>
        {(["new", "packed", "delivered", "all"] as Filter[]).map((f) => (
          <button type="button" key={f} className="chip" aria-pressed={filter === f} onClick={() => setFilter(f)}>
            {f === "all" ? t("orders.f_all") : t(`orders.f_${f}`, { count: summary?.counts[f] ?? 0 })}
          </button>
        ))}
      </div>
      {error ? <p className="error" role="alert">{error}</p> : null}
      {orders === null && !error ? <p className="muted">{t("app.loading")}</p> : null}
      {orders && orders.length === 0 ? (
        <div className="panel">
          <p>{filter === "new" ? t("orders.none_new") : t("orders.none")}</p>
          <p className="muted small">{t("orders.how")}</p>
          <Link className="btn" to="/share"><Icon name="qr" />{t("orders.share_shop")}</Link>
        </div>
      ) : null}
      <div className="order-list">
        {(orders ?? []).map((o) => <OrderCard key={o.id} order={o} onChange={changed} />)}
      </div>
    </Shell>
  );
}
