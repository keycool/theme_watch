import assert from "node:assert/strict";
import { access, readFile } from "node:fs/promises";
import test from "node:test";


const root = new URL("../", import.meta.url);

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

test("the formal target list and generated datasets stay aligned", async () => {
  const [targets, overview, topics] = await Promise.all([
    readJson("targets.json"),
    readJson("data/overview.json"),
    readJson("data/all_topics.json"),
  ]);

  const targetCodes = targets.map((item) => item.code).sort();
  const overviewCodes = overview.targets.map((item) => item.code).sort();
  const topicCodes = topics.map((item) => item.target.code).sort();

  assert.equal(targets.length, 20);
  assert.equal(targets.filter((item) => item.kind === "etf").length, 19);
  assert.equal(targets.filter((item) => item.kind === "index").length, 1);
  assert.deepEqual(overviewCodes, targetCodes);
  assert.deepEqual(topicCodes, targetCodes);
  assert.equal(new Set(overview.targets.map((item) => item.slug)).size, 20);

  for (const topic of topics) {
    assert.equal(topic.meta.sandbox, true);
    assert.ok(topic.meta.latestDate);
    assert.ok(topic.meta.weightDate);
    assert.ok(topic.target.indexCode);
    assert.ok(topic.target.indexName);
    assert.ok(topic.chart.length >= 250, `${topic.target.code} chart is too short`);
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
      ["低位收敛", "带量突破年线", "权重龙头确认"],
    );
  }
});

test("server-renders the overview and links every formal target", async () => {
  const overview = await readJson("data/overview.json");
  const response = await render("/");

  assert.equal(response.status, 200);
  assert.match(response.headers.get("content-type") ?? "", /^text\/html\b/i);

  const html = await response.text();
  assert.match(html, /<title>ETF与主题指数核心成分观察总览<\/title>/);
  assert.match(html, /20 formal project targets/);
  assert.match(html, /20个正式标的集中在同一张启动观察表中/);
  assert.match(html, /低位收敛/);
  assert.match(html, /带量突破年线/);
  assert.match(html, /权重龙头确认/);
  assert.match(html, /全部标的启动观察/);
  assert.doesNotMatch(html, /当前标签分布/);
  assert.doesNotMatch(html, /最接近闭环的目标/);

  for (const target of overview.targets) {
    assert.match(html, new RegExp(`/topic/${target.slug}`));
    assert.match(html, new RegExp(target.code.replace(".", "\\.")));
  }
});

test("orders the overview by startup status before secondary metrics", async () => {
  const source = await readFile(new URL("../app/page.tsx", import.meta.url), "utf8");

  assert.match(
    source,
    /const LABEL_ORDER = \["趋势延续", "启动确认", "接近启动", "观察中", "未启动"\]/,
  );
  assert.match(
    source,
    /labelRank\(left\.label\) - labelRank\(right\.label\)/,
  );
});

test("server-renders all 20 independent topic pages", async () => {
  const topics = await readJson("data/all_topics.json");

  for (const topic of topics) {
    const response = await render(`/topic/${topic.target.slug}`);
    assert.equal(response.status, 200, `${topic.target.code} did not render`);

    const html = await response.text();
    assert.match(html, new RegExp(topic.target.name));
    assert.match(html, new RegExp(topic.target.code.replace(".", "\\.")));
    assert.match(html, /低位收敛/);
    assert.match(html, /带量突破年线/);
    assert.match(html, /权重龙头确认/);
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
  assert.match(generator, /LOW_BELOW_MA250_WARNING_DAYS = 40/);
  assert.match(generator, /LOW_BELOW_MA250_PASS_DAYS = 60/);
  assert.match(generator, /LOW_DEEP_10_WARNING_DAYS = 12/);
  assert.match(generator, /LOW_DEEP_10_PASS_DAYS = 24/);
  assert.match(generator, /FUNDING_CONFIRM_PERCENTILE = 0\.80/);
  assert.match(generator, /CROWDING_HOT_PERCENTILE = 0\.95/);
  assert.match(
    generator,
    /跟踪指数成交额占全A成交额分位、年线突破与权重龙头持续性已经闭环/,
  );
  assert.match(
    generator,
    /below_ma250_days >= LOW_BELOW_MA250_PASS_DAYS[\s\S]*or below_ma250_10_days >= LOW_DEEP_10_PASS_DAYS/,
  );
  assert.match(
    generator,
    /below_ma250_days >= LOW_BELOW_MA250_WARNING_DAYS[\s\S]*or below_ma250_10_days >= LOW_DEEP_10_WARNING_DAYS/,
  );
  assert.match(generator, /last_three_funding_ranks >= FUNDING_CONFIRM_PERCENTILE/);
  assert.match(generator, /observation_clues\.append\("连续2日站上MA250"\)/);
  assert.match(
    generator,
    /当前观察线索：\{.*join\(observation_clues\)\}/,
  );
  assert.match(generator, /"MA60提前提示"/);
  assert.match(generator, /"次级龙头异动"/);
  assert.match(generator, /权重第4至10名近3日涨停，且次日继续收红/);
  assert.match(dashboard, /低于年线达到60日，或深跌10%达到24日/);
  assert.match(dashboard, /40日与12日分别作为提前预警/);
  assert.match(dashboard, /资金占比在过去252个交易日的历史分位/);
  assert.match(
    dashboard,
    /跟踪指数成交额占全A成交额的过去252日历史分位验证增量资金/,
  );
  assert.doesNotMatch(dashboard, /合计成交额验证增量资金/);
  assert.match(dashboard, /成分股数据未更新到专题截止日/);
  assert.match(
    dashboard,
    /aria-label="跟踪指数收盘价、MA60、MA250及跟踪指数成交额占全A成交额历史分位图"/,
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
  assert.doesNotMatch(workflow, /codex\/\*\*/);
  assert.match(workflow, /github\.ref == 'refs\/heads\/main'/);
  assert.match(workflow, /group: etf-constituent-production/);
  assert.match(workflow, /cancel-in-progress: false/);
  assert.match(workflow, /allow_rollback:/);
  assert.match(workflow, /rollback_confirmation:/);
  assert.match(workflow, /Guard manually requested production date/);
  assert.match(workflow, /Guard generated production date/);

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
  assert.doesNotMatch(workflow, /ts_code="512480\.SH"/);
  assert.doesNotMatch(workflow, /ts_code="931994\.CSI"/);
  assert.match(readiness, /for code in etf_targets:/);
  assert.match(readiness, /for code in tracking_indexes:/);
  assert.match(readiness, /pro\.etf_basic\(/);
  assert.match(readiness, /unresolved_etfs/);
});
