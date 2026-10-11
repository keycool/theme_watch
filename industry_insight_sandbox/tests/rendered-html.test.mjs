import assert from "node:assert/strict";
import { access, readFile } from "node:fs/promises";
import test from "node:test";


const root = new URL("../", import.meta.url);
const maStateCodes = new Set([
  "above_ma250",
  "above_ma60",
  "above_ma20",
  "below_ma20_converged",
  "below_ma20",
]);
const maStackPattern =
  /^(MA20>MA60>MA250|MA20>MA250>MA60|MA60>MA20>MA250|MA60>MA250>MA20|MA250>MA20>MA60|MA250>MA60>MA20|MA--)$/;

async function readJson(path) {
  return JSON.parse(await readFile(new URL(path, root), "utf8"));
}

const workerPromise = (async () => {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("test", `${process.pid}-${Date.now()}`);
  const { default: worker } = await import(workerUrl.href);
  return worker;
})();

async function render(path = "/") {
  const worker = await workerPromise;
  return worker.fetch(
    new Request(`http://localhost${path}`, {
      headers: { accept: "text/html" },
    }),
    {
      ASSETS: {
        fetch: async () => new Response("Not found", { status: 404 }),
      },
    },
    {
      waitUntil() {},
      passThroughOnException() {},
    },
  );
}

test("the unified target universe and generated datasets stay aligned", async () => {
  const [
    targets,
    hkTargets,
    overview,
    topics,
    allocationHandoff,
    signalFollowup,
  ] = await Promise.all([
    readJson("targets.json"),
    readJson("hk_qdii_targets.json"),
    readJson("data/overview.json"),
    readJson("data/all_topics.json"),
    readJson("data/allocation_handoff.json"),
    readJson("data/signal_followup.json"),
  ]);

  const targetCodes = [...targets, ...hkTargets].map((item) => item.code).sort();
  const coreCodes = targets.map((item) => item.code).sort();
  const overviewCodes = overview.targets.map((item) => item.code).sort();
  const topicCodes = topics.map((item) => item.target.code).sort();

  assert.equal(targets.length, 23);
  assert.equal(hkTargets.length, 0);
  assert.equal(targets.filter((item) => item.kind === "etf").length, 22);
  assert.equal(targets.filter((item) => item.kind === "index").length, 1);
  assert.ok(
    [
      "159930.SZ",
      "159697.SZ",
      "515220.SH",
      "512400.SH",
      "515880.SH",
      "159611.SZ",
    ].every((code) => coreCodes.includes(code)),
  );
  assert.deepEqual(overviewCodes, targetCodes);
  assert.deepEqual(topicCodes, coreCodes);
  assert.equal(overview.meta.targetCount, 23);
  assert.equal(overview.meta.hkQdiiCount, 0);
  assert.equal(allocationHandoff.meta.schemaVersion, "2.0");
  assert.equal(allocationHandoff.meta.targetCount, 23);
  assert.equal(allocationHandoff.meta.allocationMode, "event_driven_satellite");
  assert.equal(allocationHandoff.meta.allocationUnitOwner, "external_monitor");
  assert.equal(allocationHandoff.meta.strategyExecutesOrders, false);
  assert.equal(allocationHandoff.meta.positionSizingProvided, false);
  assert.equal(allocationHandoff.meta.fixedCnyAmountProvided, false);
  assert.equal(
    allocationHandoff.meta.leaderConfirmationRole,
    "industry_state_confirmation_only",
  );
  assert.equal(allocationHandoff.meta.leaderStockChaseAllowed, false);
  assert.deepEqual(
    allocationHandoff.targets.map((item) => item.code).sort(),
    targetCodes,
  );
  assert.ok(
    allocationHandoff.targets.every((item) => maStateCodes.has(item.maStateCode)),
  );
  // 2026-10-11 接口中性化（schema 2.0）：不再输出 action/单位/指令/优先级。
  assert.ok(
    allocationHandoff.targets.every(
      (item) => !("action" in item) && !("positionSignal" in item),
    ),
  );
  assert.ok(
    allocationHandoff.targets.every(
      (item) =>
        typeof item.stateInputs === "object" &&
        Array.isArray(item.reasonCodes) &&
        item.reasonCodes.length > 0,
    ),
  );
  assert.ok(
    allocationHandoff.targets.every(
      (item) => typeof item.guards?.longCycleHistoryReady === "boolean",
    ),
  );
  assert.ok(
    allocationHandoff.targets.every(
      (item) => typeof item.guards?.weightFresh === "boolean",
    ),
  );
  assert.equal(signalFollowup.meta.schemaVersion, "1.1");
  assert.equal(signalFollowup.meta.decisionUse, false);
  assert.equal(signalFollowup.meta.lookaheadAllowed, false);
  assert.deepEqual(Object.keys(signalFollowup.latestStates).sort(), targetCodes);
  assert.equal(new Set(overview.targets.map((item) => item.slug)).size, 23);
  assert.ok(
    overview.targets.every((item) => maStateCodes.has(item.maStateCode)),
  );
  assert.ok(
    overview.targets.every((item) =>
      maStackPattern.test(item.maStackCode ?? ""),
    ),
  );
  assert.ok(
    overview.targets.every(
      (item) => item.observation?.position?.windowDays > 0,
    ),
  );
  const nonferrous = topics.find((item) => item.target.code === "512400.SH");
  assert.equal(nonferrous?.target.indexCode, "000819.SH");
  assert.equal(nonferrous?.target.indexName, "中证有色金属");
  const communication = topics.find((item) => item.target.code === "515880.SH");
  assert.equal(communication?.target.indexCode, "931160.CSI");
  assert.equal(communication?.target.indexName, "中证通信设备");
  const electricPower = topics.find((item) => item.target.code === "159611.SZ");
  assert.equal(electricPower?.target.indexCode, "H30199.CSI");
  assert.equal(electricPower?.target.indexName, "中证电力指数");
  for (const target of overview.targets.filter((item) =>
    coreCodes.includes(item.code),
  )) {
    assert.equal(typeof target.belowMa250FiveDays, "number");
    assert.equal(typeof target.maStackCode, "string");
  }

  for (const topic of topics) {
    assert.equal(topic.meta.sandbox, true);
    assert.ok(topic.meta.latestDate);
    assert.ok(topic.meta.weightDate);
    assert.ok(topic.target.indexCode);
    assert.ok(topic.target.indexName);
    assert.equal(typeof topic.summary.belowMa250FiveDays, "number");
    assert.ok(maStateCodes.has(topic.summary.maLifecycle.stateCode));
    assert.ok(
      maStackPattern.test(topic.summary.maLifecycle.maStackCode ?? ""),
    );
    assert.equal(
      typeof topic.summary.observation.position.windowDays,
      "number",
    );
    assert.equal(
      topic.summary.maLifecycle.strategyExecutesOrders,
      false,
    );
    assert.ok(topic.chart.length >= 250, `${topic.target.code} chart is too short`);
    assert.ok(
      topic.chart.every((row) => Object.hasOwn(row, "ma20")),
      `${topic.target.code} chart is missing MA20`,
    );
    assert.equal(typeof topic.chart.at(-1)?.ma20, "number");
    assert.ok(
      topic.components.length >= 3,
      `${topic.target.code} has too few core components`,
    );
    for (const component of topic.components) {
      assert.equal(typeof component.latestDate, "string");
      assert.equal(typeof component.dataFresh, "boolean");
      assert.ok(component.latestDate <= topic.meta.latestDate);
    }
    for (const event of topic.limitEvents) {
      assert.equal(typeof event.dataFresh, "boolean");
      if (!event.dataFresh) assert.equal(event.qualified, false);
    }
    assert.equal(topic.stages.length, 3);
    assert.deepEqual(
      topic.stages.map((stage) => stage.title),
      ["价格位置", "均线与成交额", "核心成分股"],
    );
    const fundingItem = topic.stages
      .find((stage) => stage.id === "breakout")
      ?.items.find((item) => item.title === "成交额分位持续");
    assert.match(fundingItem?.value ?? "", /（\d\/3达标）$/);
  }
});

test("server-renders the overview and links every unified target", async () => {
  const overview = await readJson("data/overview.json");
  const response = await render("/");

  assert.equal(response.status, 200);
  assert.match(response.headers.get("content-type") ?? "", /^text\/html\b/i);

  const html = await response.text();
  assert.match(html, /<title>ETF与主题指数核心成分读数总览<\/title>/);
  assert.match(html, /23 formal project targets/);
  assert.match(html, />LIVE</);
  assert.match(html, /数据截止/);
  assert.match(html, /生成于/);
  assert.doesNotMatch(html, /封闭沙盒 · 不接入生产/);
  assert.match(html, /23个正式标的集中在同一张读数表中/);
  assert.match(html, /价格位置/);
  assert.match(html, /均线与成交额/);
  assert.match(html, /核心成分股/);
  assert.match(html, /今日均线位置读数/);
  assert.match(html, /均线位置 \/ 排列/);
  assert.doesNotMatch(html, /当前标签分布/);
  assert.doesNotMatch(html, /最接近闭环的目标/);

  for (const target of overview.targets) {
    assert.match(html, new RegExp(target.route));
    assert.match(html, new RegExp(target.code.replace(".", "\\.")));
  }
});

test("keeps localhost previews on the bundled strategy snapshot", async () => {
  const [home, topic] = await Promise.all([
    readFile(new URL("../app/page.tsx", import.meta.url), "utf8"),
    readFile(
      new URL("../app/components/TopicDashboard.tsx", import.meta.url),
      "utf8",
    ),
  ]);

  assert.match(home, /window\.location\.hostname/);
  assert.match(topic, /window\.location\.hostname/);
  assert.match(home, /\["localhost", "127\.0\.0\.1", "0\.0\.0\.0"\]/);
  assert.match(topic, /\["localhost", "127\.0\.0\.1", "0\.0\.0\.0"\]/);
});

test("orders the overview by startup status before secondary metrics", async () => {
  const source = await readFile(new URL("../app/page.tsx", import.meta.url), "utf8");

  assert.match(
    source,
    /const MA_STATE_ORDER = \[\s*"above_ma250",\s*"above_ma60",\s*"above_ma20",\s*"below_ma20_converged",\s*"below_ma20",\s*\]/,
  );
  assert.match(
    source,
    /maStateRank\(left\.maStateCode\) - maStateRank\(right\.maStateCode\)/,
  );
});

test("server-renders all 23 independent topic pages", async () => {
  const topics = await readJson("data/all_topics.json");

  for (const topic of topics) {
    const response = await render(`/topic/${topic.target.slug}`);
    assert.equal(response.status, 200, `${topic.target.code} did not render`);

    const html = await response.text();
    assert.match(html, />LIVE</);
    assert.match(html, /数据截止/);
    assert.match(html, /生成于/);
    assert.doesNotMatch(html, /封闭沙盒 · 不接入生产/);
    assert.match(html, new RegExp(topic.target.name));
    assert.match(html, new RegExp(topic.target.code.replace(".", "\\.")));
    assert.match(html, /价格位置/);
    assert.match(html, /均线与成交额/);
    assert.match(html, /核心成分股/);
    assert.match(html, /MA20/);
    assert.match(html, /均线几何位置/);
    assert.match(html, /不执行交易/);
    assert.match(html, /主要成分股权重/);
    assert.match(html, /核心成分状态矩阵/);
    assert.match(html, /返回全部专题/);
  }
});

test("keeps low-position, funding, and leader alerts below strict confirmation", async () => {
  const [generator, dashboard] = await Promise.all([
    readFile(new URL("../generate_dashboard_data.py", import.meta.url), "utf8"),
    readFile(
      new URL("../app/components/TopicDashboard.tsx", import.meta.url),
      "utf8",
    ),
  ]);

  assert.match(generator, /LEADER_WATCH_COUNT = 10/);
  assert.match(generator, /market_trade_dates\[-event_window:\]/);
  assert.match(generator, /component_latest_date == window_dates\[-1\]/);
  assert.match(generator, /next_market_date = \(/);
  assert.match(generator, /continuation_known = bool\(/);
  assert.match(generator, /LOW_BELOW_MA250_5_WARNING_DAYS = 40/);
  assert.match(generator, /LOW_BELOW_MA250_5_PASS_DAYS = 60/);
  assert.match(generator, /LOW_DEEP_10_WARNING_DAYS = 12/);
  assert.match(generator, /LOW_DEEP_10_PASS_DAYS = 24/);
  assert.match(generator, /LOW_DEEP_10_WARNING_MIN_BELOW_DAYS = 24/);
  assert.match(generator, /LOW_DEEP_10_PASS_MIN_BELOW_DAYS = 40/);
  assert.match(generator, /MA60_OBSERVATION_MIN_GAP = -0\.03/);
  assert.match(generator, /FUNDING_CONFIRM_PERCENTILE = 0\.80/);
  assert.match(generator, /CROWDING_HOT_PERCENTILE = 0\.95/);
  assert.doesNotMatch(generator, /"conclusion":/);
  assert.doesNotMatch(generator, /"label":/);
  assert.match(
    generator,
    /below_ma250_5_days >= LOW_BELOW_MA250_5_PASS_DAYS[\s\S]*or deep_path_passed/,
  );
  assert.match(
    generator,
    /below_ma250_5_days >= LOW_BELOW_MA250_5_WARNING_DAYS[\s\S]*or deep_path_warning/,
  );
  // 2026-09-21：方向性判断函数已删除，观察层只产几何读数与历史分位
  assert.doesNotMatch(generator, /def evaluate_strategy_label/);
  assert.doesNotMatch(generator, /def evaluate_short_term_rhythm/);
  assert.doesNotMatch(
    generator,
    /"观察中"|"未启动"|"启动确认"|"接近启动"|"趋势延续"/,
  );
  assert.match(generator, /last_three_funding_ranks >= FUNDING_CONFIRM_PERCENTILE/);
  assert.doesNotMatch(generator, /observation_clues/);
  assert.match(generator, /"距MA60 区间"/);
  assert.match(generator, /"第4至10名异动记录"/);
  assert.match(generator, /权重第4至10名近3日涨停，且次日继续收红/);
  assert.match(dashboard, /收盘低于MA250至少5%的天数，60日与40日两档刻度/);
  assert.match(dashboard, /第二组读数：收盘相对MA60 \/ MA250的位置/);
  assert.match(generator, /跟踪指数收盘距MA60不低于-3%/);
  assert.match(dashboard, /成交额占比在过去252个交易日的历史分位/);
  assert.match(
    dashboard,
    /跟踪指数成交额占全A成交额的过去252日历史分位验证增量资金/,
  );
  assert.doesNotMatch(dashboard, /合计成交额验证增量资金/);
  assert.match(dashboard, /成分股数据未更新到专题截止日/);
  assert.match(
    dashboard,
    /aria-label="跟踪指数收盘价、MA20、MA60、MA250及跟踪指数成交额占全A成交额历史分位图"/,
  );
  assert.doesNotMatch(dashboard, /核心成分成交额图/);
  assert.match(dashboard, /前三权重近5日、其余前十大权重近3日没有有效涨停事件/);
});

test("keeps executable site code self-contained inside the sandbox", async () => {
  const executableFiles = [
    "app/page.tsx",
    "app/layout.tsx",
    "app/components/TopicDashboard.tsx",
    "app/topic/[slug]/page.tsx",
    "generate_dashboard_data.py",
  ];
  const contents = await Promise.all(
    executableFiles.map((path) => readFile(new URL(path, root), "utf8")),
  );
  const executable = contents.join("\n");

  assert.match(contents[1], /lang="zh-CN"/);
  assert.match(contents[0], /import Link from "next\/link"/);
  assert.match(contents[2], /import Link from "next\/link"/);
  assert.doesNotMatch(contents[0], /<a\s/);
  assert.doesNotMatch(contents[2], /<a\s/);
  assert.doesNotMatch(
    executable,
    /(?:import|from|require|spawn|exec|run_path)[^\n]*(?:run_theme_watch|run_sw_l2|\.cache_scan_v2|reports[\\/]theme_watch)/i,
  );

  await assert.rejects(
    access(new URL("app/_sites-preview/SkeletonPreview.tsx", root)),
  );
});

test("keeps production publication on main and after Vercel succeeds", async () => {
  const workflow = await readFile(
    new URL("../.github/workflows/etf-constituent-daily.yml", root),
    "utf8",
  );

  assert.match(workflow, /push:\s+branches:\s+- main/);
  assert.match(workflow, /cron: "5 21 \* \* 1-5"\s+timezone: "Asia\/Shanghai"/);
  assert.match(workflow, /cron: "30 22 \* \* 1-5"\s+timezone: "Asia\/Shanghai"/);
  assert.doesNotMatch(workflow, /codex\/\*\*/);
  assert.match(workflow, /github\.ref == 'refs\/heads\/main'/);
  assert.match(workflow, /group: etf-constituent-production/);
  assert.match(workflow, /cancel-in-progress: false/);
  assert.match(workflow, /allow_rollback:/);
  assert.match(workflow, /rollback_confirmation:/);
  assert.match(workflow, /Guard manually requested production date/);
  assert.match(workflow, /Guard generated production date/);
  assert.match(
    workflow,
    /cp industry_insight_sandbox\/data\/allocation_handoff\.json/,
  );
  assert.match(workflow, /Restore published signal follow-up history/);
  assert.match(
    workflow,
    /cp industry_insight_sandbox\/data\/signal_followup\.json/,
  );

  const vercelDeployIndex = workflow.indexOf(
    "- name: Deploy observation site to Vercel",
  );
  const dataPublishIndex = workflow.indexOf("- name: Publish live webpage data");
  assert.ok(vercelDeployIndex >= 0);
  assert.ok(dataPublishIndex > vercelDeployIndex);
});

test("checks every formal target and resolved tracking index before schedule", async () => {
  const workflow = await readFile(
    new URL("../.github/workflows/etf-constituent-daily.yml", root),
    "utf8",
  );
  const readiness = await readFile(
    new URL("check_tushare_readiness.py", root),
    "utf8",
  );

  assert.match(workflow, /Checkout readiness target universe/);
  assert.match(workflow, /check_tushare_readiness\.py/);
  assert.match(workflow, /max_attempts=3/);
  assert.match(workflow, /wait_seconds=600/);
  assert.match(workflow, /cron: "5 21 \* \* 1-5"/);
  assert.match(workflow, /cron: "30 22 \* \* 1-5"/);
  assert.match(workflow, /sleep "\$wait_seconds"/);
  assert.match(workflow, /\$reason" != "daily_data_incomplete"/);
  assert.match(workflow, /\$already_current" == "true"/);
  assert.doesNotMatch(workflow, /ts_code="512480\.SH"/);
  assert.doesNotMatch(workflow, /ts_code="931994\.CSI"/);
  assert.match(readiness, /for code in etf_targets:/);
  assert.match(readiness, /for code in tracking_indexes:/);
  assert.match(readiness, /for code in global_indexes:/);
  assert.match(workflow, /--hk-targets industry_insight_sandbox\/hk_qdii_targets\.json/);
  // 港股 QDII 已停用：发布步骤不得再拷贝 hk_qdii 数据目录。
  assert.doesNotMatch(workflow, /cp -R industry_insight_sandbox\/data\/hk_qdii/);
  assert.match(readiness, /pro\.etf_basic\(/);
  assert.match(readiness, /unresolved_etfs/);
  assert.match(readiness, /completed_calendar_end/);
  assert.match(readiness, /latest_unpublished_trade_date/);
  assert.match(readiness, /live_overview_is_current/);
  assert.match(readiness, /emit\("reason", "already_current"\)/);
});
