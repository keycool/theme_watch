export type ObservationBlock = {
  position: {
    maStackCode: string | null;
    ma20GapPct: number | null;
    ma60GapPct: number | null;
    ma250GapPct: number | null;
    ma60GapRankPct: number | null;
    ma250GapRankPct: number | null;
    closeRankPct: number | null;
    drawdownFromWindowHighPct: number | null;
    windowDays: number;
  };
  duration: {
    aboveMa60Days: number;
    aboveMa250Days: number;
    belowMa60Days: number;
    ma60CrossUpDate: string | null;
    firstAboveMa250Date: string | null;
    ma60CrossUpDaysAgo: number | null;
  };
  breadth: {
    coreCount: number;
    coreCoveragePct: number | null;
    activeCount: number;
    // 港股 QDII 没有「站上 MA250 的成分股数」这一项，留 null 而不是补 0
    aboveMa60Count: number | null;
    aboveMa250Count: number | null;
    aboveMa60Pct: number | null;
    aboveMa250Pct: number | null;
  };
  strength: {
    amountRatio20: number | null;
    amountRatio20RankPct: number | null;
    absorptionRankPct: number | null;
    etfAmountRankPct: number | null;
    relativeExcess120Pct: number | null;
  };
  // 横截面读数：区分「全市场一起跌」与「单独被砸」（2026-09-18 急跌验证中唯一显著的结论）。
  // 纯观察，不含买卖含义；历史横截面无法补算，仅从首次生成日起积累。
  context?: {
    marketRet5MedianPct: number | null;
    ownRet5Pct: number | null;
    // 取值枚举：market_wide（全市场一起跌）/ single_name（单独被砸）/ none
    // 这里用 string 而非字面量联合，是因为 JSON 直连导入时 TS 只能推断出 string，
    // 与既有的 maStackCode / stateCode 处理保持一致。
    declineRegime: string;
    declineThresholdPct: number;
    sampleCount: number;
    contextAsOf: string;
  };
};

export type MovingAverageLifecycleData = {
  maStackCode: string;
  stateCode: string;
  aboveMa20: boolean;
  aboveMa60: boolean;
  aboveMa250: boolean;
  separationPct: number | null;
  separationRankPct: number | null;
  dynamicThresholdPct: number | null;
  separationObservationCount: number;
  convergenceDays: number;
  ma60BelowMa250Date: string | null;
  ma20CrossUpDate: string | null;
  ma60CrossUpDate: string | null;
  firstAboveMa250Date: string | null;
  ma60CrossUpToday: boolean;
  aboveMa250Today: boolean;
  stateAboveMa60: boolean;
  stateAboveMa250: boolean;
  ma60CrossUpInvalidated: boolean;
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

// 均线排列的命名：只描述三条均线的相对顺序，不含方向预测。
// 多头排列 = 短均线在上（MA20>MA60>MA250）；空头排列 = 长均线在上；其余为交错。
export function maAlignmentLabel(maStackCode: string | null | undefined): string {
  if (maStackCode === "MA20>MA60>MA250") return "多头排列";
  if (maStackCode === "MA250>MA60>MA20") return "空头排列";
  return "交错排列";
}

// 均线读数是收盘价走完之后的派生结果：图表在前，这里只留三格摘要并沉到页面底部。
export default function MovingAverageLifecycle({
  lifecycle,
}: {
  lifecycle: MovingAverageLifecycleData;
}) {
  return (
    <section className="ma-lifecycle shell">
      <div className="ma-lifecycle-heading">
        <div>
          <p className="eyebrow">MOVING AVERAGE GEOMETRY / DERIVED READOUT</p>
          <h2>均线几何位置</h2>
        </div>
        <span className="mono">
          {maAlignmentLabel(lifecycle.maStackCode)} · {lifecycle.maStackCode}
        </span>
      </div>
      <div className="ma-lifecycle-grid">
        <article>
          <small>收盘价相对均线</small>
          <strong>
            MA20 {lifecycle.aboveMa20 ? "上方" : "下方"} · MA60{" "}
            {lifecycle.aboveMa60 ? "上方" : "下方"} · MA250{" "}
            {lifecycle.aboveMa250 ? "上方" : "下方"}
          </strong>
          <p>排列顺序 {lifecycle.maStackCode}</p>
        </article>
        <article>
          <small>MA60 / MA250 间距</small>
          <strong>{formatPercent(lifecycle.separationPct)}</strong>
          <p>
            历史分位 {formatPercent(lifecycle.separationRankPct)} · 动态门槛{" "}
            {formatPercent(lifecycle.dynamicThresholdPct)}
          </p>
        </article>
        <article>
          <small>均线上穿日期</small>
          <strong>
            {formatDate(lifecycle.ma20CrossUpDate)} →{" "}
            {formatDate(lifecycle.ma60CrossUpDate)} →{" "}
            {formatDate(lifecycle.firstAboveMa250Date)}
          </strong>
          <p>MA20 → MA60 → MA250</p>
        </article>
      </div>
      <p className="ma-lifecycle-note">
        均线相对关系由收盘价计算得出，是价格走势的派生读数而非先行原因；
        本页只输出读数
        {lifecycle.strategyExecutesOrders ? "" : "，不执行交易"}
        。
      </p>
    </section>
  );
}
