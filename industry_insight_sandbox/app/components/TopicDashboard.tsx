"use client";

import { useEffect, useMemo, useRef, useState } from "react";


type ChartRow = {
  date: string;
  close: number | null;
  ma60: number | null;
  ma250: number | null;
  amountRatio20: number | null;
  themeNormalized: number | null;
  benchmarkNormalized: number | null;
};

type ComponentRow = {
  code: string;
  name: string;
  industry: string;
  market: string;
  weight: number | null;
  pct1d: number | null;
  ret5d: number | null;
  ret20d: number | null;
  aboveMa60: boolean;
  aboveMa250: boolean;
  amountRatio20: number | null;
};

type Stage = {
  id: string;
  number: string;
  title: string;
  subtitle: string;
  passed: boolean;
  warning?: boolean;
  items: {
    title: string;
    passed: boolean;
    value: string;
    rule: string;
    note: string;
  }[];
};

type DashboardData = {
  meta: {
    generatedAt: string;
    latestDate: string;
    weightDate: string;
    dataStart: string;
    method: string;
    sandbox: boolean;
  };
  target: {
    slug: string;
    code: string;
    name: string;
    bucket: string;
    kind: string;
    officialName: string;
    manager: string;
    indexCode: string;
    indexName: string;
    latestClose: number | null;
    latestPct: number | null;
  };
  summary: {
    label: string;
    conclusion: string;
    coreCount: number;
    coreCoverage: number | null;
    activeCount: number;
    aboveMa60Count: number;
    aboveMa250Count: number;
    strictLeaderConfirmed: boolean;
    ma60Watch?: boolean;
    ma60BreakoutToday?: boolean;
    ma60Gap?: number | null;
    ma250Gap: number | null;
    amountRatio20: number | null;
    relativeExcess120: number | null;
    topThreeNames: string[];
    topTenNames?: string[];
    topTenLimitAlert?: boolean;
    secondaryLimitAlert?: boolean;
    stagePassCount: number;
  };
  stages: Stage[];
  chart: ChartRow[];
  weights: {
    code: string;
    name: string;
    weight: number | null;
    industry: string;
  }[];
  components: ComponentRow[];
  limitEvents: {
    code: string;
    name: string;
    weightRank?: number;
    tier?: string;
    date: string;
    pct: number | null;
    continuationKnown: boolean;
    continuationPct: number | null;
    continuationOk: boolean;
  }[];
  notes: string[];
};

type RangeKey = "120" | "250" | "all";
type SortKey = "weight" | "pct1d" | "ret5d";

const LIVE_TOPIC_ROOT =
  "https://raw.githubusercontent.com/keycool/theme_watch/etf-watch-data/topics";

const COLORS = {
  grid: "rgba(148, 163, 184, 0.14)",
  text: "#8090a6",
  close: "#f4c96b",
  ma60: "#63d6bf",
  ma250: "#6da4ff",
  amount: "rgba(109, 164, 255, 0.24)",
  theme: "#f4c96b",
  benchmark: "#7f91aa",
};


function formatDate(value: string) {
  return `${value.slice(0, 4)}-${value.slice(4, 6)}-${value.slice(6, 8)}`;
}

function formatPercent(value: number | null | undefined, digits = 1) {
  if (value === null || value === undefined) return "—";
  return `${value > 0 ? "+" : ""}${value.toFixed(digits)}%`;
}

function formatNumber(value: number | null | undefined, digits = 1) {
  if (value === null || value === undefined) return "—";
  return value.toLocaleString("zh-CN", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

function statusText(passed: boolean, warning = false) {
  if (passed) return "通过";
  return warning ? "提前预警" : "未通过";
}

function canvasSize(canvas: HTMLCanvasElement) {
  const rect = canvas.getBoundingClientRect();
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  canvas.width = Math.round(rect.width * dpr);
  canvas.height = Math.round(rect.height * dpr);
  const context = canvas.getContext("2d");
  if (!context) return null;
  context.setTransform(dpr, 0, 0, dpr, 0, 0);
  return { context, width: rect.width, height: rect.height };
}

function drawPath(
  context: CanvasRenderingContext2D,
  rows: ChartRow[],
  key: "close" | "ma60" | "ma250" | "themeNormalized" | "benchmarkNormalized",
  x: (index: number) => number,
  y: (value: number) => number,
  color: string,
  width = 2,
) {
  context.beginPath();
  let started = false;
  rows.forEach((row, index) => {
    const value = row[key];
    if (value === null) return;
    if (!started) {
      context.moveTo(x(index), y(value));
      started = true;
    } else {
      context.lineTo(x(index), y(value));
    }
  });
  context.strokeStyle = color;
  context.lineWidth = width;
  context.lineJoin = "round";
  context.lineCap = "round";
  context.stroke();
}

function PriceChart({ rows }: { rows: ChartRow[] }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || rows.length < 2) return;

    const draw = () => {
      const sized = canvasSize(canvas);
      if (!sized) return;
      const { context, width, height } = sized;
      context.clearRect(0, 0, width, height);

      const padding = { top: 18, right: 58, bottom: 34, left: 8 };
      const amountHeight = 54;
      const plotBottom = height - padding.bottom - amountHeight;
      const values = rows
        .flatMap((row) => [row.close, row.ma60, row.ma250])
        .filter((value): value is number => value !== null);
      const min = Math.min(...values);
      const max = Math.max(...values);
      const span = max - min || 1;
      const x = (index: number) =>
        padding.left +
        (index / Math.max(rows.length - 1, 1)) *
          (width - padding.left - padding.right);
      const y = (value: number) =>
        padding.top + ((max - value) / span) * (plotBottom - padding.top);

      context.font = "11px ui-monospace, SFMono-Regular, Consolas, monospace";
      context.textAlign = "left";
      context.textBaseline = "middle";
      for (let line = 0; line <= 4; line += 1) {
        const lineY =
          padding.top + (line / 4) * (plotBottom - padding.top);
        context.beginPath();
        context.moveTo(padding.left, lineY);
        context.lineTo(width - padding.right, lineY);
        context.strokeStyle = COLORS.grid;
        context.lineWidth = 1;
        context.stroke();
        const label = max - (line / 4) * span;
        context.fillStyle = COLORS.text;
        context.fillText(
          formatNumber(label, 0),
          width - padding.right + 8,
          lineY,
        );
      }

      const maxAmount = Math.max(
        ...rows.map((row) => row.amountRatio20 || 0),
        1.2,
      );
      const barWidth = Math.max(
        1,
        (width - padding.left - padding.right) / rows.length - 1,
      );
      rows.forEach((row, index) => {
        if (row.amountRatio20 === null) return;
        const barHeight =
          (row.amountRatio20 / maxAmount) * (amountHeight - 12);
        context.fillStyle =
          row.amountRatio20 >= 1.2
            ? "rgba(99, 214, 191, 0.38)"
            : COLORS.amount;
        context.fillRect(
          x(index) - barWidth / 2,
          height - padding.bottom - barHeight,
          barWidth,
          barHeight,
        );
      });

      const thresholdY =
        height - padding.bottom - (1.2 / maxAmount) * (amountHeight - 12);
      context.setLineDash([4, 4]);
      context.beginPath();
      context.moveTo(padding.left, thresholdY);
      context.lineTo(width - padding.right, thresholdY);
      context.strokeStyle = "rgba(99, 214, 191, 0.44)";
      context.stroke();
      context.setLineDash([]);

      drawPath(context, rows, "ma250", x, y, COLORS.ma250, 1.6);
      drawPath(context, rows, "ma60", x, y, COLORS.ma60, 1.6);
      drawPath(context, rows, "close", x, y, COLORS.close, 2.3);

      const labelIndexes = [0, Math.floor(rows.length / 2), rows.length - 1];
      context.textAlign = "center";
      context.textBaseline = "top";
      context.fillStyle = COLORS.text;
      labelIndexes.forEach((index) => {
        context.fillText(
          `${rows[index].date.slice(4, 6)}/${rows[index].date.slice(6, 8)}`,
          x(index),
          height - 22,
        );
      });
    };

    draw();
    const observer = new ResizeObserver(draw);
    observer.observe(canvas);
    return () => observer.disconnect();
  }, [rows]);

  return (
    <canvas
      ref={canvasRef}
      className="chart-canvas chart-canvas-large"
      aria-label="跟踪指数收盘价、MA60、MA250和核心成分成交额图"
    />
  );
}

function RelativeChart({ rows }: { rows: ChartRow[] }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || rows.length < 2) return;

    const draw = () => {
      const sized = canvasSize(canvas);
      if (!sized) return;
      const { context, width, height } = sized;
      context.clearRect(0, 0, width, height);
      const padding = { top: 18, right: 42, bottom: 30, left: 8 };
      const values = rows
        .flatMap((row) => [row.themeNormalized, row.benchmarkNormalized])
        .filter((value): value is number => value !== null);
      const min = Math.min(...values);
      const max = Math.max(...values);
      const span = max - min || 1;
      const x = (index: number) =>
        padding.left +
        (index / Math.max(rows.length - 1, 1)) *
          (width - padding.left - padding.right);
      const y = (value: number) =>
        padding.top +
        ((max - value) / span) *
          (height - padding.top - padding.bottom);

      context.font = "10px ui-monospace, SFMono-Regular, Consolas, monospace";
      for (let line = 0; line <= 3; line += 1) {
        const lineY =
          padding.top +
          (line / 3) * (height - padding.top - padding.bottom);
        context.beginPath();
        context.moveTo(padding.left, lineY);
        context.lineTo(width - padding.right, lineY);
        context.strokeStyle = COLORS.grid;
        context.stroke();
        context.fillStyle = COLORS.text;
        context.textAlign = "left";
        context.textBaseline = "middle";
        context.fillText(
          formatNumber(max - (line / 3) * span, 0),
          width - padding.right + 7,
          lineY,
        );
      }

      drawPath(
        context,
        rows,
        "benchmarkNormalized",
        x,
        y,
        COLORS.benchmark,
        1.6,
      );
      drawPath(context, rows, "themeNormalized", x, y, COLORS.theme, 2.2);
    };

    draw();
    const observer = new ResizeObserver(draw);
    observer.observe(canvas);
    return () => observer.disconnect();
  }, [rows]);

  return (
    <canvas
      ref={canvasRef}
      className="chart-canvas"
      aria-label="中证半导体与沪深300归一化走势对比图"
    />
  );
}

function StageCard({
  stage,
}: {
  stage: Stage;
}) {
  const stateClass = stage.passed ? "passed" : stage.warning ? "warning" : "failed";
  const statusClass = stage.passed
    ? "is-pass"
    : stage.warning
      ? "is-warning"
      : "is-fail";

  return (
    <article className={`stage-card ${stateClass}`}>
      <div className="stage-header">
        <span className="stage-number">{stage.number}</span>
        <div>
          <p className="eyebrow">{stage.subtitle}</p>
          <h3>{stage.title}</h3>
        </div>
        <span className={`status-chip ${statusClass}`}>
          {statusText(stage.passed, stage.warning)}
        </span>
      </div>
      <div className="condition-list">
        {stage.items.map((item) => (
          <div className="condition-row" key={item.title}>
            <span
              className={`condition-dot ${item.passed ? "is-pass" : "is-fail"}`}
              aria-hidden="true"
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
  );
}

function WeightBars({ data }: { data: DashboardData["weights"] }) {
  const maxWeight = Math.max(...data.map((row) => row.weight || 0));
  return (
    <div className="weight-bars">
      {data.slice(0, 10).map((row, index) => (
        <div className="weight-row" key={row.code}>
          <span className="weight-rank">{String(index + 1).padStart(2, "0")}</span>
          <div className="weight-name">
            <strong>{row.name}</strong>
            <small>{row.code}</small>
          </div>
          <div className="weight-track" aria-label={`${row.name}权重${row.weight}%`}>
            <span
              style={{ width: `${((row.weight || 0) / maxWeight) * 100}%` }}
            />
          </div>
          <strong className="weight-value">{formatPercent(row.weight)}</strong>
        </div>
      ))}
    </div>
  );
}

export default function TopicDashboard({
  dashboardData: bundledDashboardData,
}: {
  dashboardData: DashboardData;
}) {
  const [dashboardData, setDashboardData] = useState(bundledDashboardData);
  const [range, setRange] = useState<RangeKey>("250");
  const [sortBy, setSortBy] = useState<SortKey>("weight");

  useEffect(() => {
    let cancelled = false;
    const slug = bundledDashboardData.target.slug;
    fetch(`${LIVE_TOPIC_ROOT}/${slug}.json?v=${Date.now()}`, {
      cache: "no-store",
    })
      .then((response) => {
        if (!response.ok) throw new Error(`Live topic HTTP ${response.status}`);
        return response.json() as Promise<DashboardData>;
      })
      .then((liveData) => {
        if (!cancelled && liveData.target?.slug === slug) {
          setDashboardData(liveData);
        }
      })
      .catch(() => {
        // Keep the bundled snapshot when the live data branch is unavailable.
      });
    return () => {
      cancelled = true;
    };
  }, [bundledDashboardData.target.slug]);

  const visibleChart = useMemo(() => {
    if (range === "all") return dashboardData.chart;
    return dashboardData.chart.slice(-Number(range));
  }, [dashboardData.chart, range]);

  const sortedComponents = useMemo(() => {
    return [...dashboardData.components].sort((left, right) => {
      const leftValue = left[sortBy] ?? -Infinity;
      const rightValue = right[sortBy] ?? -Infinity;
      return rightValue - leftValue;
    });
  }, [dashboardData.components, sortBy]);

  const ma250Gap = dashboardData.summary.ma250Gap;

  return (
    <main>
      <header className="topbar">
        <a className="brand-lockup" href="/">
          <span className="brand-mark" aria-hidden="true">
            IW
          </span>
          <div>
            <strong>Industry Watch Lab</strong>
            <small>ETF constituent sandbox</small>
          </div>
        </a>
        <div className="topbar-actions">
          <a className="back-link" href="/">
            ← 返回全部专题
          </a>
          <div className="sandbox-badge">
            <span />
            封闭沙盒 · 不接入生产
          </div>
        </div>
      </header>

      <section className="hero shell">
        <div className="hero-copy">
          <p className="eyebrow">ETF DIRECT OBSERVATION / METHOD PROTOTYPE</p>
          <h1>
            从ETF跟踪指数出发，
            <br />
            直接观察<span>权重成分股</span>
          </h1>
          <p className="hero-description">
            取消“ETF → 申万二级”的强制中间映射。价格结构看跟踪指数，
            增量资金看核心成分合计成交额，市场共识看指数权重龙头。
          </p>
        </div>
        <div className="hero-status">
          <p>本期判断</p>
          <strong>{dashboardData.summary.label}</strong>
          <span>{dashboardData.summary.conclusion}</span>
        </div>
      </section>

      <section className="identity-grid shell">
        <article className="identity-card identity-main">
          <div>
            <p className="eyebrow">{dashboardData.target.bucket}</p>
            <h2>{dashboardData.target.name}</h2>
            <p className="mono">{dashboardData.target.code}</p>
          </div>
          <div className="price-block">
            <strong>{formatNumber(dashboardData.target.latestClose, 3)}</strong>
            <span className={(dashboardData.target.latestPct || 0) >= 0 ? "up" : "down"}>
              {formatPercent(dashboardData.target.latestPct, 2)}
            </span>
          </div>
        </article>
        <article className="identity-card">
          <p className="metric-label">跟踪指数</p>
          <strong>{dashboardData.target.indexName}</strong>
          <span className="mono">{dashboardData.target.indexCode}</span>
        </article>
        <article className="identity-card">
          <p className="metric-label">核心成分篮子</p>
          <strong>{dashboardData.summary.coreCount} 只</strong>
          <span>累计权重 {formatPercent(dashboardData.summary.coreCoverage)}</span>
        </article>
        <article className="identity-card">
          <p className="metric-label">指数距年线</p>
          <strong className={ma250Gap !== null && ma250Gap >= 0 ? "up" : "down"}>
            {formatPercent(ma250Gap)}
          </strong>
          <span>MA250仍为严格确认边界</span>
        </article>
      </section>

      <section className="process shell" aria-label="三层启动确认链路">
        <div className="section-heading">
          <div>
            <p className="eyebrow">THREE-LAYER CONFIRMATION</p>
            <h2>启动条件必须串联闭环</h2>
          </div>
          <p>
            低位收敛按四项标准同时判断；MA60和前十大权重股异动只做提前预警。
            只有MA250正式突破与前三龙头持续性完成，才能进入“启动确认”。
          </p>
        </div>
        <div className="stage-grid">
          {dashboardData.stages.map((stage) => (
            <StageCard stage={stage} key={stage.id} />
          ))}
        </div>
      </section>

      <section className="analytics shell">
        <article className="panel chart-panel">
          <div className="panel-heading">
            <div>
              <p className="eyebrow">TRACKING INDEX STRUCTURE</p>
              <h2>{dashboardData.target.indexName} · 趋势与成交</h2>
            </div>
            <div className="range-switch" aria-label="图表周期">
              {(
                [
                  ["120", "120日"],
                  ["250", "250日"],
                  ["all", "全部"],
                ] as const
              ).map(([value, label]) => (
                <button
                  className={range === value ? "active" : ""}
                  key={value}
                  onClick={() => setRange(value)}
                  type="button"
                >
                  {label}
                </button>
              ))}
            </div>
          </div>
          <div className="chart-legend">
            <span><i style={{ background: COLORS.close }} />收盘</span>
            <span><i style={{ background: COLORS.ma60 }} />MA60</span>
            <span><i style={{ background: COLORS.ma250 }} />MA250</span>
            <span><i className="bar-legend" />核心成分成交额 / MA20</span>
          </div>
          <PriceChart rows={visibleChart} />
          <p className="chart-footnote">
            成交柱来自优先覆盖指数权重60%、最多20只的核心成分股合计成交额；虚线位置为
            1.20×放量阈值。数据截至 {formatDate(dashboardData.meta.latestDate)}。
          </p>
        </article>

        <article className="panel relative-panel">
          <div className="panel-heading">
            <div>
              <p className="eyebrow">RELATIVE TEMPERATURE</p>
              <h2>相对沪深300</h2>
            </div>
          </div>
          <div className="relative-legend">
            <span><i style={{ background: COLORS.theme }} />{dashboardData.target.indexName}</span>
            <span><i style={{ background: COLORS.benchmark }} />沪深300</span>
          </div>
          <RelativeChart rows={visibleChart} />
          <div className="relative-note">
            <strong>为何显示“{dashboardData.summary.label}”</strong>
            <p>{dashboardData.summary.conclusion}</p>
          </div>
        </article>
      </section>

      <section className="holdings shell">
        <article className="panel weights-panel">
          <div className="panel-heading">
            <div>
              <p className="eyebrow">CURRENT INDEX WEIGHTS</p>
              <h2>主要成分股权重</h2>
            </div>
            <span className="data-date">
              权重日 {formatDate(dashboardData.meta.weightDate)}
            </span>
          </div>
          <WeightBars data={dashboardData.weights} />
        </article>

        <article className="panel leader-panel">
          <div className="panel-heading">
            <div>
              <p className="eyebrow">TOP-10 WEIGHTED LEADER WATCH</p>
              <h2>标志性龙头事件</h2>
            </div>
          </div>
          {dashboardData.limitEvents.length ? (
            <div className="event-list">
              {dashboardData.limitEvents.map((event) => {
                const rank = event.weightRank ?? 1;
                const isStrictLeader = rank <= 3;
                return (
                <div className="event-card" key={`${event.code}-${event.date}`}>
                  <div className="event-top">
                    <div>
                      <strong>{event.name}</strong>
                      <span>
                        权重第{rank} · {event.tier ?? "核心龙头"} · {event.code}
                      </span>
                    </div>
                    <b>{formatPercent(event.pct, 2)}</b>
                  </div>
                  <div className="event-flow">
                    <span className="event-node is-hit">
                      {formatDate(event.date)} 涨停
                    </span>
                    <i />
                    <span
                      className={`event-node ${
                        event.continuationOk ? "is-pass" : "is-fail"
                      }`}
                    >
                      次日 {formatPercent(event.continuationPct, 2)}
                    </span>
                  </div>
                  <p>
                    {isStrictLeader
                      ? event.continuationOk
                        ? "前三权重龙头涨停后继续收红，严格持续性通过。"
                        : "前三权重龙头已涨停，但次日延续尚未确认。"
                      : event.continuationOk
                        ? "第4至10名权重股涨停后延续，触发增强观察提示。"
                        : "第4至10名权重股出现涨停，触发早期异动提示。"}
                  </p>
                </div>
                );
              })}
            </div>
          ) : (
            <div className="empty-state">
              前10大权重股近20个交易日没有出现涨停事件。
            </div>
          )}
          <div className="leader-summary">
            <div>
              <span>强势核心</span>
              <strong>
                {dashboardData.summary.activeCount}/{dashboardData.summary.coreCount}
              </strong>
            </div>
            <div>
              <span>站上MA60</span>
              <strong>
                {dashboardData.summary.aboveMa60Count}/{dashboardData.summary.coreCount}
              </strong>
            </div>
            <div>
              <span>站上MA250</span>
              <strong>
                {dashboardData.summary.aboveMa250Count}/{dashboardData.summary.coreCount}
              </strong>
            </div>
          </div>
        </article>
      </section>

      <section className="components shell">
        <div className="section-heading table-heading">
          <div>
            <p className="eyebrow">CORE CONSTITUENT MATRIX</p>
            <h2>核心成分状态矩阵</h2>
          </div>
          <div className="sort-switch">
            <span>排序</span>
            {(
              [
                ["weight", "权重"],
                ["pct1d", "当日"],
                ["ret5d", "5日"],
              ] as const
            ).map(([value, label]) => (
              <button
                className={sortBy === value ? "active" : ""}
                key={value}
                onClick={() => setSortBy(value)}
                type="button"
              >
                {label}
              </button>
            ))}
          </div>
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>成分股</th>
                <th>指数权重</th>
                <th>当日</th>
                <th>近5日</th>
                <th>近20日</th>
                <th>成交 / MA20</th>
                <th>MA60</th>
                <th>MA250</th>
              </tr>
            </thead>
            <tbody>
              {sortedComponents.map((row) => (
                <tr key={row.code}>
                  <td>
                    <div className="stock-name">
                      <strong>{row.name}</strong>
                      <span>{row.code} · {row.industry}</span>
                    </div>
                  </td>
                  <td className="mono-cell">{formatPercent(row.weight, 2)}</td>
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
                    {row.amountRatio20 === null
                      ? "—"
                      : `${row.amountRatio20.toFixed(2)}×`}
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
                        row.aboveMa250 ? "is-pass" : "is-fail"
                      }`}
                    >
                      {row.aboveMa250 ? "线上" : "线下"}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="method shell">
        <div className="section-heading">
          <div>
            <p className="eyebrow">METHOD BOUNDARY</p>
            <h2>新旧逻辑如何分工</h2>
          </div>
        </div>
        <div className="method-grid">
          <article>
            <span>主判断对象</span>
            <h3>ETF跟踪指数</h3>
            <p>用于低位结构、MA60、MA250和趋势位置判断。</p>
          </article>
          <article>
            <span>资金验证对象</span>
            <h3>核心成分股篮子</h3>
            <p>优先累计覆盖指数权重60%，最多取20只，合计成交额验证增量资金。</p>
          </article>
          <article>
            <span>龙头确认对象</span>
            <h3>指数权重前3</h3>
            <p>观察涨停事件和次日延续，不再使用申万市值龙头替代。</p>
          </article>
          <article className="muted-method">
            <span>辅助参照</span>
            <h3>申万二级行业</h3>
            <p>保留行业归属和横向比较功能，但不决定本页启动标签。</p>
          </article>
        </div>
      </section>

      <footer className="footer shell">
        <div>
          <strong>数据说明</strong>
          <p>
            数据来源：Tushare ETF基础信息、ETF日线、指数日线、指数月度权重及A股日线。
            生成时间 {dashboardData.meta.generatedAt}。
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
