import { type ReactNode } from "react";
import { ExternalLink } from "lucide-react";
import { Link } from "react-router-dom";
import type { ChildOrder, Trade, TradeReconciliation } from "../../api/client";
import { ROUTES } from "../../lib/routes";
import { useGeneralSettings } from "../../hooks/useGeneralSettings";
import type { AppInstantStyle } from "../../lib/formatTime";
import { reasonCategoryLabel, tradeReasonPresentation } from "../../lib/tradeReasons";
import {
  analysisRunId,
  directionClassName,
  directionLabel,
  exploreHrefForTrade,
  formatPnl,
  formatPrice,
  formatUnits,
  orderPrice,
  pnlClassName,
  reconciliationBadgeClassName,
  reconciliationBadgeLabel,
  tradeDuration,
  tradeExitPrice,
  tradeIsCancelled,
  tradeIsOpen,
  tradeLastModifiedAt,
  tradeRealizedPl,
  tradeStatusKey,
  tradeStatusLabel,
} from "../../lib/trades";

type TradeDetailPanelProps = {
  trade: Trade;
  reconciliation: TradeReconciliation | null;
  onClose: () => void;
  formatInstant?: (
    value: string | number | Date | null | undefined,
    style?: AppInstantStyle,
  ) => string;
};

function DetailRow({
  label,
  value,
  valueClassName,
}: {
  label: string;
  value: ReactNode;
  valueClassName?: string;
}) {
  return (
    <div className="analysis-detail-row">
      <dt className="analysis-detail-label">{label}</dt>
      <dd className={["analysis-detail-value", valueClassName].filter(Boolean).join(" ")}>
        {value}
      </dd>
    </div>
  );
}

function childOrderSummary(
  order: number | ChildOrder | null | undefined,
  flatPrice?: number | null,
): string {
  const price = formatPrice(orderPrice(order, flatPrice));
  if (order == null || typeof order === "number") {
    return price;
  }
  const parts = [price];
  if (order.state?.trim()) parts.push(order.state);
  if (order.broker_order_id?.trim()) parts.push(`#${order.broker_order_id}`);
  if (order.filling_event_id?.trim()) parts.push(`fill ${order.filling_event_id}`);
  if (order.cancelling_event_id?.trim()) parts.push(`cancel ${order.cancelling_event_id}`);
  return parts.join(" · ");
}

function formatConfidence(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return "—";
  if (value >= 0 && value <= 1) return `${Math.round(value * 100)}%`;
  return String(value);
}

function formatRiskPct(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return "—";
  return `${value}%`;
}

function reasonCode(trade: Trade): string | null {
  if (trade.state === "closed" || trade.state === "cancelled") {
    return trade.close_reason?.trim() || null;
  }
  return trade.execution_reason?.trim() || trade.reason_display?.code?.trim() || null;
}

function TradeDetailSection({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) {
  return (
    <section className="trade-detail-section" aria-labelledby={`trade-detail-${title}`}>
      <h3 className="trade-detail-section-title" id={`trade-detail-${title}`}>
        {title}
      </h3>
      {children}
    </section>
  );
}

export default function TradeDetailPanel({
  trade,
  reconciliation,
  onClose,
  formatInstant: formatInstantProp,
}: TradeDetailPanelProps) {
  const { formatInstant: formatInstantFromSettings } = useGeneralSettings();
  const formatInstant = formatInstantProp ?? formatInstantFromSettings;

  const status = tradeStatusKey(trade);
  const isOpen = tradeIsOpen(trade);
  const isCancelled = tradeIsCancelled(trade);
  const market = isOpen && reconciliation ? reconciliation.ledger_market[trade.id] : undefined;
  const exitPrice = tradeExitPrice(trade);
  const realizedPl = tradeRealizedPl(trade);
  const lastModified = tradeLastModifiedAt(trade);
  const reason = tradeReasonPresentation(trade);
  const runId = analysisRunId(trade);
  const badge =
    isOpen && reconciliation
      ? reconciliation.ledger_badges[trade.id] ?? reconciliation.lot_badges?.[trade.id]
      : undefined;
  const syncedAt =
    typeof (trade as Trade & { synced_at?: string | null }).synced_at === "string"
      ? (trade as Trade & { synced_at?: string | null }).synced_at
      : null;

  const currentPrice = isOpen ? market?.current_price : exitPrice;
  const pnlValue = isOpen ? market?.unrealized_pl : realizedPl;
  const pnlLabel = isOpen ? "Unrealized P/L" : "Realized P/L";

  return (
    <div className="trade-detail-panel-scroll">
      <TradeDetailSection title="Overview">
        <dl className="analysis-detail-list">
          <DetailRow label="Status" value={tradeStatusLabel(status)} />
          <DetailRow label="Pair" value={trade.pair} />
          <DetailRow
            label="Direction"
            value={
              <span className={directionClassName(trade.direction)}>
                {directionLabel(trade.direction)}
              </span>
            }
          />
          <DetailRow label="Strategy" value={trade.strategy_name} />
          <DetailRow label="Asset class" value={trade.asset_class || "—"} />
          <DetailRow label="Exchange" value={trade.exchange_id ?? "—"} />
        </dl>
      </TradeDetailSection>

      <TradeDetailSection title="Position">
        <dl className="analysis-detail-list">
          <DetailRow label="Entry" value={formatPrice(trade.entry_price)} />
          <DetailRow
            label={isOpen ? "Current price" : "Exit price"}
            value={formatPrice(currentPrice)}
          />
          <DetailRow label="Units" value={formatUnits(trade.units)} />
          <DetailRow
            label={pnlLabel}
            value={formatPnl(pnlValue)}
            valueClassName={pnlClassName(pnlValue)}
          />
          <DetailRow
            label="Duration"
            value={
              isOpen || isCancelled
                ? "—"
                : tradeDuration(trade.open_time, trade.close_time ?? null)
            }
          />
        </dl>
      </TradeDetailSection>

      <TradeDetailSection title="Orders">
        <dl className="analysis-detail-list">
          <DetailRow
            label="Stop loss"
            value={childOrderSummary(trade.stop_loss, trade.stop_loss_price)}
          />
          <DetailRow
            label="Take profit"
            value={childOrderSummary(trade.take_profit, trade.take_profit_price)}
          />
        </dl>
      </TradeDetailSection>

      <TradeDetailSection title="Timing">
        <dl className="analysis-detail-list">
          <DetailRow
            label="Opened"
            value={trade.open_time ? formatInstant(trade.open_time) : "—"}
          />
          {!isOpen && (
            <DetailRow
              label="Closed"
              value={trade.close_time ? formatInstant(trade.close_time) : "—"}
            />
          )}
          <DetailRow
            label="Last modified"
            value={lastModified ? formatInstant(lastModified) : "—"}
          />
          {syncedAt && <DetailRow label="Last synced" value={formatInstant(syncedAt)} />}
        </dl>
      </TradeDetailSection>

      <TradeDetailSection title="Reason">
        <dl className="analysis-detail-list">
          <DetailRow label="Label" value={reason.label ?? reason.short} />
          <DetailRow label="Category" value={reasonCategoryLabel(reason.category) || "—"} />
          <DetailRow label="Code" value={reasonCode(trade) ?? "—"} />
        </dl>
      </TradeDetailSection>

      <TradeDetailSection title="Broker">
        <dl className="analysis-detail-list">
          <DetailRow
            label="Broker lot ID"
            value={trade.broker_lot_id ?? "—"}
          />
          {isOpen && badge && reconciliationBadgeLabel(badge) && (
            <DetailRow
              label="Reconciliation"
              value={
                <span className={reconciliationBadgeClassName(badge)}>
                  {reconciliationBadgeLabel(badge)}
                </span>
              }
            />
          )}
          <DetailRow label="Confidence" value={formatConfidence(trade.confidence)} />
          <DetailRow label="Risk" value={formatRiskPct(trade.risk_pct)} />
          <DetailRow label="Exit mode" value={trade.exit_mode || "—"} />
        </dl>
      </TradeDetailSection>

      <TradeDetailSection title="Actions">
        <div className="trade-detail-actions">
          <Link
            to={exploreHrefForTrade(trade)}
            className="btn btn-secondary btn-sm"
            onClick={onClose}
          >
            <ExternalLink size={14} aria-hidden="true" />
            Explore pair
          </Link>
          {trade.strategy_id && (
            <Link
              to={ROUTES.research.strategyEdit(trade.strategy_id)}
              className="btn btn-secondary btn-sm"
              onClick={onClose}
            >
              Edit strategy
            </Link>
          )}
          {runId && (
            <Link
              to={ROUTES.research.analysisRun(runId)}
              className="btn btn-secondary btn-sm"
              onClick={onClose}
            >
              View analysis run
            </Link>
          )}
        </div>
      </TradeDetailSection>
    </div>
  );
}
