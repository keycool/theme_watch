export type MovingAverageLifecycleData = {
  label: string;
  separationPct: number | null;
  separationRankPct: number | null;
  dynamicThresholdPct: number | null;
  separationObservationCount: number;
  safetyMarginPassed: boolean;
  convergenceDays: number;
  deathCrossDate: string | null;
  warmUpDate: string | null;
  initialStartDate: string | null;
  trendConfirmedDate: string | null;
  initialStartToday: boolean;
  trendConfirmedToday: boolean;
  initialStartActive: boolean;
  trendConfirmedActive: boolean;
  initialStartInvalidated: boolean;
  capitalInterface: string;
  executionOwner: string;
  strategyExecutesOrders: boolean;
};

function formatPercent(value: number | null) {
  return value === null ? "—" : `${value.toFixed(1)}%`;
}

function formatDate(value: string | null) {
  if (!value) return "—";
  return `${value.slice(0, 4)}-${value.slice(4, 6)}-${value.slice(6, 8)}`;
}

function capitalLabel(value: string) {
  if (value === "scale_in_eligible") return "可衔接趋势确认资金";
  if (value === "starter_position_eligible") return "可衔接初始资金";
  return "仅观察";
}

export default function MovingAverageLifecycle({
  lifecycle,
}: {
  lifecycle: MovingAverageLifecycleData;
}) {
  return (
    <section className="ma-lifecycle shell">
      <div className="ma-lifecycle-heading">
        <div>
          <p className="eyebrow">MOVING AVERAGE LIFECYCLE</p>
          <h2>均线启动生命周期</h2>
        </div>
        <span className={lifecycle.safetyMarginPassed ? "passed" : ""}>
          {lifecycle.label}
        </span>
      </div>
      <div className="ma-lifecycle-grid">
        <article>
          <small>MA60 / MA250 安全边际</small>
          <strong>{formatPercent(lifecycle.separationPct)}</strong>
          <p>
            历史分位 {formatPercent(lifecycle.separationRankPct)} · 动态门槛{" "}
            {formatPercent(lifecycle.dynamicThresholdPct)}
          </p>
        </article>
        <article>
          <small>低位有序收敛</small>
          <strong>{lifecycle.convergenceDays}/30日</strong>
          <p>要求至少20日满足 收盘 &lt; MA20 &lt; MA60</p>
        </article>
        <article>
          <small>信号路径</small>
          <strong>
            {formatDate(lifecycle.warmUpDate)} →{" "}
            {formatDate(lifecycle.initialStartDate)} →{" "}
            {formatDate(lifecycle.trendConfirmedDate)}
          </strong>
          <p>MA20转暖 → MA60初始启动 → MA250当日趋势确认</p>
        </article>
        <article>
          <small>外部资金接口</small>
          <strong>{capitalLabel(lifecycle.capitalInterface)}</strong>
          <p>本策略只输出信号，不执行交易或资金分配。</p>
        </article>
      </div>
    </section>
  );
}
