import Link from "next/link";
import StatusStrip from "./StatusStrip";


type NullableNumber = number | null;

type DashboardData = {
  meta: {
    generatedAt: string;
    latestDate: string;
    constituentDate: string;
    method: string;
    structureSource: string;
    structureObjectName: string;
    fundingObjectName: string;
    heroDescription: string;
    boundaryLabel: string;
    chartFootnote: string;
    productionIntegrated: boolean;
  };
  target: {
    code: string;
    name: string;
    officialName: string;
    indexCode: string;
    officialIndexCode: string;
    indexName: string;
    benchmarkName: string;
    latestClose: NullableNumber;
    latestPct: NullableNumber;
    feederCode: string | null;
    feederName: string | null;
    feederLatestNav?: NullableNumber;
    feederLatestDate?: string | null;
  };
  counterpart: {
    href: string;
    code: string;
    name: string;
  };
  summary: {
    label: string;
    rhythmLabel: string;
    conclusion: string;
    stagePassCount: number;
    ma60Gap: NullableNumber;
    ma250Gap: NullableNumber;
    amountRankPct: NullableNumber;
    aboveMa60Count: number;
    positive5dCount: number;
  };
  stages: {
    id: string;
    number: string;
    title: string;
    subtitle: string;
    passed: boolean;
    warning: boolean;
    items: {
      title: string;
      passed: boolean;
      value: string;
      rule: string;
      note: string;
    }[];
  }[];
  chart: {
    date: string;
    close: NullableNumber;
    ma20: NullableNumber;
    ma60: NullableNumber;
    ma250: NullableNumber;
    amountRankPct: NullableNumber;
    etfNormalized: NullableNumber;
    benchmarkNormalized: NullableNumber;
  }[];
  constituents: {
    code: string;
    name: string;
    englishName: string;
    rank: number;
    weight: NullableNumber;
    latestDate: string;
    dataFresh: boolean;
    latestClose: NullableNumber;
    pct1d: NullableNumber;
    ret5d: NullableNumber;
    ret20d: NullableNumber;
    aboveMa60: boolean;
    aboveMa250: boolean;
    volumeRatio20: NullableNumber;
  }[];
  leaderEvents: {
    code: string;
    name: string;
    rank: number;
    tier: string;
    date: string;
    pct: NullableNumber;
    dynamicThreshold: NullableNumber;
    dataFresh: boolean;
    continuationPct: NullableNumber;
    continuationOk: boolean;
    latestRetained: boolean;
    qualified: boolean;
    strictQualified: boolean;
  }[];
  notes: string[];
};

function formatDate(value: string) {
  return `${value.slice(0, 4)}-${value.slice(4, 6)}-${value.slice(6, 8)}`;
}

function formatPercent(value: NullableNumber, digits = 1) {
  if (value === null) return "—";
  return `${value > 0 ? "+" : ""}${value.toFixed(digits)}%`;
}

function formatNumber(value: NullableNumber, digits = 3) {
  if (value === null) return "—";
  return value.toLocaleString("zh-CN", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

function statusText(passed: boolean, warning: boolean) {
  if (passed) return "通过";
  return warning ? "提前预警" : "未通过";
}

function pathFor(
  rows: DashboardData["chart"],
  key: "close" | "ma20" | "ma60" | "ma250" | "etfNormalized" | "benchmarkNormalized",
  min: number,
  max: number,
) {
  const values = rows
    .map((row, index) => ({ value: row[key], index }))
    .filter(
      (item): item is { value: number; index: number } =>
        item.value !== null,
    );
  const span = max - min || 1;
  return values
    .map(({ value, index }, position) => {
      const x = (index / Math.max(rows.length - 1, 1)) * 1000;
      const y = 280 - ((value - min) / span) * 250;
      return `${position ? "L" : "M"}${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
}

function LineChart({
  rows,
  comparison = false,
  primaryName,
  benchmarkName,
}: {
  rows: DashboardData["chart"];
  comparison?: boolean;
  primaryName: string;
  benchmarkName: string;
}) {
  const keys = comparison
    ? (["etfNormalized", "benchmarkNormalized"] as const)
    : (["close", "ma20", "ma60", "ma250"] as const);
  const values = rows
    .flatMap((row) => keys.map((key) => row[key]))
    .filter((value): value is number => value !== null);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const colors = comparison
    ? ["#f4c96b", "#7f91aa"]
    : ["#f4c96b", "#e88ccf", "#63d6bf", "#6da4ff"];

  return (
    <svg
      aria-label={
        comparison
          ? `${primaryName}与${benchmarkName}归一化走势`
          : `${primaryName}收盘、MA20、MA60与MA250走势`
      }
      className="hk-line-chart"
      role="img"
      viewBox="0 0 1000 300"
    >
      {[30, 92.5, 155, 217.5, 280].map((y) => (
        <line
          key={y}
          stroke="rgba(148, 163, 184, 0.14)"
          x1="0"
          x2="1000"
          y1={y}
          y2={y}
        />
      ))}
      {keys.map((key, index) => (
        <path
          d={pathFor(rows, key, min, max)}
          fill="none"
          key={key}
          stroke={colors[index]}
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={index === 0 ? 3 : 2}
        />
      ))}
    </svg>
  );
}

export default function HKQdiiDashboard({
  dashboardData,
}: {
  dashboardData: DashboardData;
}) {
  const chartRows = dashboardData.chart.slice(-250);

  return (
    <main>
      <header className="topbar">
        <Link className="brand-lockup" href="/">
          <span className="brand-mark" aria-hidden="true">
            HK
          </span>
          <div>
            <strong>Industry Watch Lab</strong>
            <small>Unified HK QDII watch</small>
          </div>
        </Link>
        <div className="topbar-actions">
          <Link className="back-link" href={dashboardData.counterpart.href}>
            {`切换：${dashboardData.counterpart.name}`}
          </Link>
          <Link className="back-link" href="/">
            ← 返回全部专题
          </Link>
          <StatusStrip
            generatedAt={dashboardData.meta.generatedAt}
            latestDate={dashboardData.meta.latestDate}
          />
        </div>
      </header>

      <section className="hero shell hk-hero">
        <div className="hero-copy">
          <p className="eyebrow">
            {dashboardData.target.code} / UNIFIED HK CONSUMER WATCH
          </p>
          <h1>
            {dashboardData.target.name}
            <br />
            <span>行业启动观察</span>
          </h1>
          <p className="hero-description">
            {dashboardData.meta.heroDescription}
          </p>
          <div className="hk-boundary">
            {dashboardData.meta.boundaryLabel}
          </div>
        </div>
        <div className="hero-status">
          <p>本期判断</p>
          <strong>{dashboardData.summary.label}</strong>
          <small>短期节奏 · {dashboardData.summary.rhythmLabel}</small>
          <span>{dashboardData.summary.conclusion}</span>
        </div>
      </section>

      <section className="identity-grid shell">
        <article className="identity-card identity-main">
          <div>
            <p className="eyebrow">QDII ETF</p>
            <h2>{dashboardData.target.name}</h2>
            <p className="mono">{dashboardData.target.code}</p>
            {dashboardData.target.feederCode && (
              <p className="mono">
                联接基金 {dashboardData.target.feederCode}
              </p>
            )}
          </div>
          <div className="price-block">
            <strong>{formatNumber(dashboardData.target.latestClose)}</strong>
            <span
              className={
                (dashboardData.target.latestPct || 0) >= 0 ? "up" : "down"
              }
            >
              {formatPercent(dashboardData.target.latestPct, 2)}
            </span>
            {dashboardData.target.feederLatestNav !== undefined &&
              dashboardData.target.feederLatestNav !== null && (
                <small>
                  联接净值{" "}
                  {formatNumber(dashboardData.target.feederLatestNav, 4)}
                </small>
              )}
          </div>
        </article>
        <article className="identity-card">
          <p className="metric-label">真实跟踪指数</p>
          <strong>{dashboardData.target.indexName}</strong>
          <span className="mono">
            {dashboardData.target.indexCode} /{" "}
            {dashboardData.target.officialIndexCode}
          </span>
        </article>
        <article className="identity-card">
          <p className="metric-label">
            {dashboardData.meta.structureObjectName}距MA250
          </p>
          <strong
            className={
              (dashboardData.summary.ma250Gap || 0) >= 0 ? "up" : "down"
            }
          >
            {formatPercent(dashboardData.summary.ma250Gap)}
          </strong>
          <span>距MA60 {formatPercent(dashboardData.summary.ma60Gap)}</span>
        </article>
        <article className="identity-card">
          <p className="metric-label">
            {dashboardData.meta.fundingObjectName}成交额分位
          </p>
          <strong>
            {dashboardData.summary.amountRankPct === null
              ? "—"
              : `${dashboardData.summary.amountRankPct.toFixed(0)}%`}
          </strong>
          <span>自身过去252个交易日历史分位</span>
        </article>
      </section>

      <section className="process shell" aria-label="港股QDII三层启动条件">
        <div className="section-heading">
          <div>
            <p className="eyebrow">THREE-LAYER CONFIRMATION</p>
            <h2>港股专用口径的三层闭环</h2>
          </div>
          <p>
            低位规则保留原策略弹性路径；量价层使用ETF自身行情；港股没有统一涨停板，
            龙头层改用5%绝对涨幅、个股95%收益分位、次日延续与前十大群体广度共同确认。
          </p>
        </div>
        <div className="stage-grid">
          {dashboardData.stages.map((stage) => (
            <article
              className={`stage-card ${
                stage.passed ? "passed" : stage.warning ? "warning" : ""
              }`}
              key={stage.id}
            >
              <div className="stage-header">
                <span className="stage-number">{stage.number}</span>
                <div>
                  <h3>{stage.title}</h3>
                  <p>{stage.subtitle}</p>
                </div>
                <span
                  className={`status-chip ${
                    stage.passed
                      ? "is-pass"
                      : stage.warning
                        ? "is-warning"
                        : "is-fail"
                  }`}
                >
                  {statusText(stage.passed, stage.warning)}
                </span>
              </div>
              <div className="condition-list">
                {stage.items.map((item) => (
                  <div className="condition-row" key={item.title}>
                    <i
                      className={`condition-dot ${
                        item.passed ? "is-pass" : "is-fail"
                      }`}
                    />
                    <div className="condition-copy">
                      <div className="condition-title-line">
                        <strong>{item.title}</strong>
                        <span>{item.value}</span>
                      </div>
                      <p>{item.rule}</p>
                      <small>{item.note}</small>
                    </div>
                  </div>
                ))}
              </div>
            </article>
          ))}
        </div>
      </section>

      <section className="analytics shell hk-analytics">
        <article className="panel">
          <div className="panel-heading">
            <div>
              <p className="eyebrow">
                {dashboardData.meta.structureSource === "tracking_index"
                  ? "TRACKING INDEX STRUCTURE"
                  : "ETF PRICE PROXY"}
              </p>
              <h2>{dashboardData.meta.structureObjectName}、MA20、MA60与MA250</h2>
            </div>
          </div>
          <div className="chart-legend">
            <span>
              <i style={{ background: "#f4c96b" }} />
              {dashboardData.meta.structureObjectName}
            </span>
            <span><i style={{ background: "#e88ccf" }} />MA20</span>
            <span><i style={{ background: "#63d6bf" }} />MA60</span>
            <span><i style={{ background: "#6da4ff" }} />MA250</span>
          </div>
          <LineChart
            benchmarkName={dashboardData.target.benchmarkName}
            primaryName={dashboardData.meta.structureObjectName}
            rows={chartRows}
          />
          <p className="chart-footnote">
            {dashboardData.meta.chartFootnote} MA20仅生成短期节奏标签，不参与三层条件与主启动标签判定。
          </p>
        </article>
        <article className="panel">
          <div className="panel-heading">
            <div>
              <p className="eyebrow">RELATIVE TEMPERATURE</p>
              <h2>相对{dashboardData.target.benchmarkName}</h2>
            </div>
          </div>
          <div className="relative-legend">
            <span>
              <i style={{ background: "#f4c96b" }} />
              {dashboardData.target.indexName}
            </span>
            <span><i style={{ background: "#7f91aa" }} />恒生指数</span>
          </div>
          <LineChart
            benchmarkName={dashboardData.target.benchmarkName}
            comparison
            primaryName={dashboardData.target.indexName}
            rows={chartRows}
          />
          <div className="relative-note">
            <strong>当前完成 {dashboardData.summary.stagePassCount}/3 层</strong>
            <p>{dashboardData.summary.conclusion}</p>
          </div>
        </article>
      </section>

      <section className="components shell">
        <div className="section-heading table-heading">
          <div>
            <p className="eyebrow">OFFICIAL TOP-10 CONSTITUENTS</p>
            <h2>{`${dashboardData.target.indexName}前十大成分状态`}</h2>
          </div>
          <span className="data-date">
            官方名单日期 {formatDate(dashboardData.meta.constituentDate)}
          </span>
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>官方排序</th>
                <th>成分股</th>
                <th>指数权重</th>
                <th>当日</th>
                <th>近5日</th>
                <th>近20日</th>
                <th>成交量 / MA20</th>
                <th>MA60</th>
                <th>数据新鲜度</th>
              </tr>
            </thead>
            <tbody>
              {dashboardData.constituents.map((row) => (
                <tr key={row.code}>
                  <td className="mono-cell">#{row.rank}</td>
                  <td>
                    <div className="stock-name">
                      <strong>{row.name}</strong>
                      <span>{row.code} · {row.englishName}</span>
                    </div>
                  </td>
                  <td className="mono-cell">
                    {row.weight === null
                      ? "未披露"
                      : formatPercent(row.weight, 2)}
                  </td>
                  <td className={(row.pct1d || 0) >= 0 ? "up" : "down"}>
                    {formatPercent(row.pct1d, 2)}
                  </td>
                  <td className={(row.ret5d || 0) >= 0 ? "up" : "down"}>
                    {formatPercent(row.ret5d, 2)}
                  </td>
                  <td className={(row.ret20d || 0) >= 0 ? "up" : "down"}>
                    {formatPercent(row.ret20d, 2)}
                  </td>
                  <td className="mono-cell">
                    {row.volumeRatio20 === null
                      ? "—"
                      : `${row.volumeRatio20.toFixed(2)}×`}
                  </td>
                  <td>
                    <span
                      className={`matrix-status ${
                        row.aboveMa60 ? "is-pass" : "is-fail"
                      }`}
                    >
                      {row.aboveMa60 ? "线上" : "线下"}
                    </span>
                  </td>
                  <td>
                    <span
                      className={`matrix-status ${
                        row.dataFresh ? "is-pass" : "is-fail"
                      }`}
                    >
                      {row.dataFresh ? "当日" : formatDate(row.latestDate)}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="holdings shell hk-leader-section">
        <article className="panel leader-panel">
          <div className="panel-heading">
            <div>
              <p className="eyebrow">HK LEADER EVENTS</p>
              <h2>港股龙头强势事件</h2>
            </div>
          </div>
          {dashboardData.leaderEvents.length ? (
            <div className="event-list">
              {dashboardData.leaderEvents.map((event) => (
                <div className="event-card" key={`${event.code}-${event.date}`}>
                  <div className="event-top">
                    <div>
                      <strong>{event.name}</strong>
                      <span>官方第{event.rank} · {event.tier}</span>
                    </div>
                    <b>{formatPercent(event.pct, 2)}</b>
                  </div>
                  <p>
                    动态门槛 {formatPercent(event.dynamicThreshold, 2)}；
                    次日 {formatPercent(event.continuationPct, 2)}；
                    {event.strictQualified
                      ? "前三龙头严格确认通过。"
                      : event.qualified
                        ? "仅作为第4至10名预警。"
                        : "持续性或新鲜度未通过。"}
                  </p>
                </div>
              ))}
            </div>
          ) : (
            <div className="empty-state">
              最近观察窗口没有成分股同时满足“涨幅≥5%且达到自身120日收益95%分位”。
            </div>
          )}
          <div className="leader-summary">
            <div>
              <span>站上MA60</span>
              <strong>{dashboardData.summary.aboveMa60Count}/10</strong>
            </div>
            <div>
              <span>近5日上涨</span>
              <strong>{dashboardData.summary.positive5dCount}/10</strong>
            </div>
            <div>
              <span>严格事件</span>
              <strong>
                {dashboardData.leaderEvents.filter(
                  (event) => event.strictQualified,
                ).length}
              </strong>
            </div>
          </div>
        </article>
      </section>

      <footer className="footer shell">
        <div>
          <strong>统一生产口径</strong>
          <p>
            数据日期 {formatDate(dashboardData.meta.latestDate)}；该页面已加入统一
            仪表盘、定时任务与生产发布，策略计算继续使用港股专用规则。
          </p>
        </div>
        <div className="footer-notes">
          {dashboardData.notes.map((note) => (
            <p key={note}>{note}</p>
          ))}
        </div>
      </footer>
    </main>
  );
}
