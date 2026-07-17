"use client";

import { useEffect, useMemo, useState } from "react";
import bundledOverviewData from "../data/overview.json";


type OverviewData = typeof bundledOverviewData;
type Target = OverviewData["targets"][number];

const LIVE_OVERVIEW_URL =
  "https://raw.githubusercontent.com/keycool/theme_watch/etf-watch-data/overview.json";

const BUCKET_ORDER = [
  "科技成长与高端制造",
  "大消费与医药",
  "周期资源",
  "红利金融地产",
];

const LABEL_ORDER = ["启动确认", "接近启动", "观察中", "未启动", "趋势延续"];


function formatPercent(value: number | null | undefined, digits = 1) {
  if (value === null || value === undefined) return "—";
  return `${value > 0 ? "+" : ""}${value.toFixed(digits)}%`;
}

function formatDate(value: string) {
  return `${value.slice(0, 4)}-${value.slice(4, 6)}-${value.slice(6, 8)}`;
}

function labelClass(label: string) {
  if (label === "启动确认") return "label-confirmed";
  if (label === "接近启动") return "label-near";
  if (label === "观察中") return "label-watch";
  if (label === "趋势延续") return "label-trend";
  return "label-idle";
}

function StatusDistribution({ targets }: { targets: Target[] }) {
  const counts = LABEL_ORDER.map((label) => ({
    label,
    count: targets.filter((target) => target.label === label).length,
  }));
  const max = Math.max(...counts.map((row) => row.count), 1);

  return (
    <div className="distribution-chart">
      {counts.map((row) => (
        <div className="distribution-row" key={row.label}>
          <span>{row.label}</span>
          <div className="distribution-track">
            <i
              className={labelClass(row.label)}
              style={{ width: `${(row.count / max) * 100}%` }}
            />
          </div>
          <strong>{row.count}</strong>
        </div>
      ))}
    </div>
  );
}

function StageMatrix({ targets }: { targets: Target[] }) {
  const ranked = [...targets].sort(
    (left, right) =>
      right.stagePassCount - left.stagePassCount ||
      (right.amountRatio20 || 0) - (left.amountRatio20 || 0),
  );
  return (
    <div className="stage-matrix">
      <div className="stage-matrix-head">
        <span>目标</span>
        <span>低位</span>
        <span>突破</span>
        <span>龙头</span>
      </div>
      {ranked.slice(0, 10).map((target) => (
        <a href={`/topic/${target.slug}`} key={target.slug}>
          <span>{target.name}</span>
          {target.stageStates.map((stage) => (
            <i
              className={stage.passed ? "matrix-on" : "matrix-off"}
              key={stage.title}
              title={`${stage.title}：${stage.passed ? "通过" : "未通过"}`}
            />
          ))}
        </a>
      ))}
    </div>
  );
}

function TargetCard({ target }: { target: Target }) {
  return (
    <a className="overview-card" href={`/topic/${target.slug}`}>
      <div className="overview-card-top">
        <div>
          <span className="target-kind">
            {target.kind === "etf" ? "ETF" : "主题指数"}
          </span>
          <h3>{target.name}</h3>
          <p className="mono">{target.code}</p>
        </div>
        <span className={`overview-label ${labelClass(target.label)}`}>
          {target.label}
        </span>
      </div>
      <div className="index-identity">
        <span>判断指数</span>
        <strong>{target.indexName}</strong>
        <small>{target.indexCode}</small>
      </div>
      <div className="overview-metrics">
        <div>
          <span>当日</span>
          <strong className={(target.latestPct || 0) >= 0 ? "up" : "down"}>
            {formatPercent(target.latestPct, 2)}
          </strong>
        </div>
        <div>
          <span>距MA250</span>
          <strong className={(target.ma250Gap || 0) >= 0 ? "up" : "down"}>
            {formatPercent(target.ma250Gap)}
          </strong>
        </div>
        <div>
          <span>核心成交</span>
          <strong>{target.amountRatio20?.toFixed(2) || "—"}×</strong>
        </div>
      </div>
      <div className="stage-mini">
        {target.stageStates.map((stage, index) => (
          <div key={stage.title}>
            <i className={stage.passed ? "is-pass" : "is-fail"} />
            <span>
              {index + 1}. {stage.title}
            </span>
          </div>
        ))}
      </div>
      <div className="overview-card-bottom">
        <span>
          核心 {target.coreCount}只 / 权重{" "}
          {target.coreCoverage?.toFixed(1) || "—"}%
        </span>
        <strong>查看专题 →</strong>
      </div>
    </a>
  );
}

export default function Home() {
  const [overviewData, setOverviewData] = useState<OverviewData>(
    bundledOverviewData,
  );
  const [bucket, setBucket] = useState("全部");
  const [label, setLabel] = useState("全部");
  const [query, setQuery] = useState("");

  useEffect(() => {
    let cancelled = false;
    fetch(`${LIVE_OVERVIEW_URL}?v=${Date.now()}`, { cache: "no-store" })
      .then((response) => {
        if (!response.ok) throw new Error(`Live overview HTTP ${response.status}`);
        return response.json() as Promise<OverviewData>;
      })
      .then((liveData) => {
        if (!cancelled && liveData.meta?.targetCount === 20) {
          setOverviewData(liveData);
        }
      })
      .catch(() => {
        // Keep the bundled snapshot when the live data branch is unavailable.
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const targets = overviewData.targets;
  const filtered = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    return targets.filter(
      (target) =>
        (bucket === "全部" || target.bucket === bucket) &&
        (label === "全部" || target.label === label) &&
        (!normalized ||
          target.name.toLowerCase().includes(normalized) ||
          target.code.toLowerCase().includes(normalized) ||
          target.indexName.toLowerCase().includes(normalized)),
    );
  }, [bucket, label, query, targets]);

  const grouped = BUCKET_ORDER.map((name) => ({
    name,
    targets: filtered
      .filter((target) => target.bucket === name)
      .sort((left, right) => left.order - right.order),
  })).filter((group) => group.targets.length);

  const watchCount = targets.filter((target) =>
    ["启动确认", "接近启动", "观察中"].includes(target.label),
  ).length;
  const trendCount = targets.filter(
    (target) => target.label === "趋势延续",
  ).length;

  return (
    <main>
      <header className="topbar">
        <div className="brand-lockup">
          <span className="brand-mark" aria-hidden="true">
            IW
          </span>
          <div>
            <strong>Industry Watch Lab</strong>
            <small>20 formal project targets</small>
          </div>
        </div>
        <div className="sandbox-badge">
          <span />
          封闭沙盒 · 不接入生产
        </div>
      </header>

      <section className="overview-hero shell">
        <div>
          <p className="eyebrow">PROJECT TARGET UNIVERSE / DIRECT CONSTITUENT VIEW</p>
          <h1>
            项目目标ETF与指数
            <br />
            <span>核心成分观察总览</span>
          </h1>
          <p>
            清单严格来自现有项目正式配置：19只ETF与1个主题指数。点击任一标题进入专题，
            直接查看跟踪指数、权重成分股成交、前三龙头和三层启动条件。
          </p>
        </div>
        <div className="overview-stat-grid">
          <article>
            <span>正式目标</span>
            <strong>{overviewData.meta.targetCount}</strong>
            <small>{overviewData.meta.etfCount} ETF + {overviewData.meta.indexCount} 指数</small>
          </article>
          <article>
            <span>启动观察</span>
            <strong>{watchCount}</strong>
            <small>观察中 / 接近 / 确认</small>
          </article>
          <article>
            <span>趋势延续</span>
            <strong>{trendCount}</strong>
            <small>已脱离低位启动区</small>
          </article>
          <article>
            <span>数据日期</span>
            <strong className="date-stat">
              {formatDate(targets[0].latestDate)}
            </strong>
            <small>权重日 {formatDate(targets[0].weightDate)}</small>
          </article>
        </div>
      </section>

      <section className="overview-insights shell">
        <article className="panel">
          <div className="panel-heading">
            <div>
              <p className="eyebrow">STATUS DISTRIBUTION</p>
              <h2>当前标签分布</h2>
            </div>
          </div>
          <StatusDistribution targets={targets} />
        </article>
        <article className="panel">
          <div className="panel-heading">
            <div>
              <p className="eyebrow">THREE-STAGE MATRIX</p>
              <h2>最接近闭环的目标</h2>
            </div>
          </div>
          <StageMatrix targets={targets} />
        </article>
      </section>

      <section className="overview-controls shell">
        <div className="filter-group">
          {["全部", ...BUCKET_ORDER].map((value) => (
            <button
              className={bucket === value ? "active" : ""}
              key={value}
              onClick={() => setBucket(value)}
              type="button"
            >
              {value}
            </button>
          ))}
        </div>
        <div className="overview-control-right">
          <select value={label} onChange={(event) => setLabel(event.target.value)}>
            <option>全部</option>
            {LABEL_ORDER.map((value) => (
              <option key={value}>{value}</option>
            ))}
          </select>
          <input
            aria-label="搜索ETF、指数或代码"
            onChange={(event) => setQuery(event.target.value)}
            placeholder="搜索名称 / 代码 / 跟踪指数"
            type="search"
            value={query}
          />
        </div>
      </section>

      <section className="overview-groups shell">
        {grouped.map((group) => (
          <div className="overview-group" key={group.name}>
            <div className="group-heading">
              <h2>{group.name}</h2>
              <span>{group.targets.length} 个目标</span>
            </div>
            <div className="overview-card-grid">
              {group.targets.map((target) => (
                <TargetCard key={target.slug} target={target} />
              ))}
            </div>
          </div>
        ))}
        {!grouped.length && (
          <div className="overview-empty">没有符合当前筛选条件的目标。</div>
        )}
      </section>

      <footer className="footer shell">
        <div>
          <strong>范围说明</strong>
          <p>
            数据目标来自现有项目正式配置，不含人工通信对照组。生成时间{" "}
            {overviewData.meta.generatedAt}。
          </p>
        </div>
        <div className="footer-notes">
          <p>每个专题独立使用对应ETF的真实跟踪指数和最新月度权重。</p>
          <p>核心成分优先覆盖60%指数权重，最多取20只，实际覆盖率逐页展示。</p>
          <p>申万二级不参与本沙盒专题标签，只保留为成分股行业文字参照。</p>
          <p>以上内容仅用于策略研究与观察，不构成投资建议。</p>
        </div>
      </footer>
    </main>
  );
}
