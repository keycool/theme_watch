from __future__ import annotations

from datetime import datetime
from html import escape
from pathlib import Path


ROOT = Path(__file__).resolve().parent
REPORT_DIR = ROOT / "reports" / "theme_watch"
OUTPUT_HTML = REPORT_DIR / "index.html"


ETF_CARDS = [
    {
        "bucket": "科技成长与高端制造",
        "code": "512480.SH",
        "name": "半导体 ETF",
        "map": "801081.SI 半导体",
        "status": "趋势延续 / 拥挤偏高",
        "note": "趋势已展开，辅助关注拥挤偏高后的回踩风险。",
        "href": "pages/theme_512480_sw_l2_watch_report.html",
    },
    {
        "bucket": "科技成长与高端制造",
        "code": "515790.SH",
        "name": "光伏 ETF",
        "map": "801735.SI 光伏设备",
        "status": "趋势延续",
        "note": "当前更偏趋势延续，辅助关注是否继续扩散。",
        "href": "pages/theme_515790_sw_l2_watch_report.html",
    },
    {
        "bucket": "科技成长与高端制造",
        "code": "515230.SH",
        "name": "软件 ETF",
        "map": "801104.SI 软件开发、801103.SI IT服务Ⅱ",
        "status": "未启动 / 拥挤正常",
        "note": "当前未启动，辅助状态偏正常。",
        "href": "pages/theme_515230_software_watch_report.html",
    },
    {
        "bucket": "科技成长与高端制造",
        "code": "159998.SZ",
        "name": "计算机 ETF",
        "map": "801101.SI 计算机设备",
        "status": "未启动 / 拥挤正常",
        "note": "当前未启动，辅助状态偏正常。",
        "href": "pages/theme_159998_computer_watch_report.html",
    },
    {
        "bucket": "大消费与医药",
        "code": "512980.SH",
        "name": "传媒 ETF",
        "map": "801767.SI 数字媒体、801765.SI 广告营销、801764.SI 游戏Ⅱ",
        "status": "未启动 / 拥挤正常",
        "note": "当前未启动，辅助状态偏正常。",
        "href": "pages/theme_512980_sw_l2_watch_report.html",
    },
    {
        "bucket": "科技成长与高端制造",
        "code": "931994.CSI",
        "name": "电网设备主题指数",
        "map": "801738.SI 电网设备",
        "status": "趋势延续",
        "note": "不是 ETF，但作为实际观察标的；当前更偏趋势延续。",
        "href": "pages/theme_931994_sw_l2_watch_report.html",
    },
    {
        "bucket": "科技成长与高端制造",
        "code": "TMT-COMM",
        "name": "通信链条对照组",
        "map": "801102.SI 通信设备、801223.SI 通信服务",
        "status": "未启动 / 观察中",
        "note": "不是核心 ETF，主要作为软件/计算机的扩散对照；当前未启动到观察中。",
        "href": "pages/theme_communication_compare_report.html",
    },
    {
        "bucket": "大消费与医药",
        "code": "159928.SZ",
        "name": "消费 ETF",
        "map": "801125.SI 白酒Ⅱ、801129.SI 调味发酵品Ⅱ、801127.SI 饮料乳品",
        "status": "未启动 / 观察中",
        "note": "当前未启动到观察中。",
        "href": "pages/theme_consumption_liquor_sw_l2_watch_report.html",
    },
    {
        "bucket": "大消费与医药",
        "code": "512690.SH",
        "name": "酒 ETF",
        "map": "801125.SI 白酒Ⅱ、801128.SI 非白酒",
        "status": "未启动",
        "note": "当前未启动，辅助等待结构修复。",
        "href": "pages/theme_consumption_liquor_sw_l2_watch_report.html",
    },
    {
        "bucket": "大消费与医药",
        "code": "512010.SH",
        "name": "医药 ETF",
        "map": "医疗服务、生物制品、化学制药、医疗器械、中药Ⅱ",
        "status": "未启动 / 观察中",
        "note": "宽基医药入口，当前未启动到观察中，辅助关注修复质量。",
        "href": "pages/theme_512010_medicine_watch_report.html",
    },
    {
        "bucket": "大消费与医药",
        "code": "512170.SH",
        "name": "医疗 ETF",
        "map": "801156.SI 医疗服务、801153.SI 医疗器械",
        "status": "未启动 / 观察中",
        "note": "当前未启动到观察中。",
        "href": "pages/theme_512170_healthcare_watch_report.html",
    },
    {
        "bucket": "大消费与医药",
        "code": "159992.SZ",
        "name": "创新药 ETF",
        "map": "801151.SI 化学制药、801152.SI 生物制品、801156.SI 医疗服务",
        "status": "未启动 / 观察中",
        "note": "当前未启动到观察中。",
        "href": "pages/theme_159992_innovative_drug_watch_report.html",
    },
    {
        "bucket": "大消费与医药",
        "code": "159996.SZ",
        "name": "家电 ETF",
        "map": "小家电、家电零部件Ⅱ、黑色家电、厨卫电器、白色家电",
        "status": "观察中",
        "note": "当前观察中，辅助关注是否站稳修复。",
        "href": "pages/theme_159996_sw_l2_watch_report.html",
    },
    {
        "bucket": "周期资源",
        "code": "159930.SZ",
        "name": "能源 ETF",
        "map": "煤炭开采、炼化及贸易、油服工程、燃气Ⅱ",
        "status": "观察中 / 拥挤正常",
        "note": "当前观察中，辅助状态偏正常。",
        "href": "pages/theme_cycle_resources_sw_l2_watch_report.html",
    },
    {
        "bucket": "周期资源",
        "code": "159697.SZ",
        "name": "石油 ETF",
        "map": "炼化及贸易、油服工程、燃气Ⅱ",
        "status": "观察中 / 拥挤正常",
        "note": "当前观察中，辅助状态偏正常。",
        "href": "pages/theme_cycle_resources_sw_l2_watch_report.html",
    },
    {
        "bucket": "周期资源",
        "code": "515220.SH",
        "name": "煤炭 ETF",
        "map": "801951.SI 煤炭开采、801952.SI 焦炭Ⅱ",
        "status": "观察中 / 拥挤正常",
        "note": "当前观察中，辅助关注过热消退。",
        "href": "pages/theme_cycle_resources_sw_l2_watch_report.html",
    },
    {
        "bucket": "周期资源",
        "code": "159870.SZ",
        "name": "化工 ETF",
        "map": "化学制品、农化制品、化学原料、冶钢原料、化学纤维",
        "status": "观察中 / 拥挤偏高",
        "note": "当前观察中但拥挤偏高，辅助关注分歧。",
        "href": "pages/theme_159870_chemical_compare_report.html",
    },
    {
        "bucket": "红利金融地产",
        "code": "515180.SH",
        "name": "易方达红利 ETF",
        "map": "煤炭开采、炼化及贸易、铁路公路、航运港口、基础建设",
        "status": "未启动 / 观察中",
        "note": "红利风格标的，行业分布较宽；当前未启动到观察中。",
        "href": "pages/theme_515180_sw_l2_watch_report.html",
    },
    {
        "bucket": "红利金融地产",
        "code": "512890.SH",
        "name": "红利低波 ETF",
        "map": "城商行Ⅱ、农商行Ⅱ、股份制银行Ⅱ、国有大型银行Ⅱ",
        "status": "观察中",
        "note": "红利低波风格标的；当前观察中，辅助关注稳定性。",
        "href": "pages/theme_512890_sw_l2_watch_report.html",
    },
    {
        "bucket": "红利金融地产",
        "code": "512880.SH",
        "name": "证券 ETF",
        "map": "801193.SI 证券Ⅱ、801191.SI 多元金融、801194.SI 保险Ⅱ",
        "status": "观察中 / 拥挤正常",
        "note": "当前观察中，辅助状态偏正常。",
        "href": "pages/theme_512880_sw_l2_watch_report.html",
    },
    {
        "bucket": "红利金融地产",
        "code": "512200.SH",
        "name": "房地产 ETF",
        "map": "房地产开发、房地产服务、装修建材、房屋建设Ⅱ、装修装饰Ⅱ",
        "status": "未启动 / 拥挤正常",
        "note": "当前未启动，辅助状态偏正常。",
        "href": "pages/theme_512200_real_estate_watch_report.html",
    },
]


def _overview_table(cards: list[dict[str, str]]) -> str:
    rows = []
    for card in cards:
        rows.append(
            f"""
<tr>
  <td><a class="target-link" href="{escape(card['href'])}">{escape(card['name'])}</a></td>
  <td class="mono">{escape(card['code'])}</td>
  <td><span class="status-pill">{escape(card['status'])}</span></td>
  <td>{escape(card['map'])}</td>
  <td><span class="table-bucket">{escape(card['bucket'])}</span></td>
  <td>{escape(card['note'])}</td>
</tr>
"""
        )

    return f"""
<section class="overview-table-section">
  <div class="section-title">
    <h1>观察标的一览表</h1>
    <p>先用表格横向比较状态、映射行业和备注；需要看图形细节时再打开观察页。</p>
  </div>
  <div class="table-wrap">
    <table class="overview-table">
      <thead>
        <tr>
          <th>标的</th>
          <th>代码</th>
          <th>当前状态</th>
          <th>映射申万二级</th>
          <th>分类</th>
          <th>备注</th>
        </tr>
      </thead>
      <tbody>{''.join(rows)}</tbody>
    </table>
  </div>
</section>
"""


def build_dashboard() -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    html = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>ETF 标的观察总览</title>
  <style>
    :root {{
      --bg: #f3ead9;
      --paper: #fffaf1;
      --ink: #17262d;
      --muted: #66727a;
      --accent: #b64b2c;
      --accent-2: #1f6f78;
      --line: rgba(70, 52, 27, 0.16);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      color: var(--ink);
      background:
        radial-gradient(circle at 12% 8%, rgba(182, 75, 44, 0.18), transparent 30rem),
        radial-gradient(circle at 86% 12%, rgba(31, 111, 120, 0.15), transparent 26rem),
        linear-gradient(135deg, #fbf5ea 0%, var(--bg) 52%, #e5d2b4 100%);
      font-family: "Microsoft YaHei", "Noto Sans CJK SC", sans-serif;
    }}
    main {{ max-width: 1240px; margin: 0 auto; padding: 42px 20px 60px; }}
    header {{ margin-bottom: 28px; }}
    header h1 {{ margin: 0 0 10px; font-size: clamp(30px, 4vw, 52px); letter-spacing: -0.05em; }}
    header p {{ margin: 0; color: var(--muted); line-height: 1.8; }}
    .nav {{ display: flex; flex-wrap: wrap; gap: 10px; margin-top: 14px; }}
    .nav a {{
      color: var(--accent-2);
      text-decoration: none;
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 8px 12px;
      background: rgba(255, 250, 241, 0.72);
    }}
    .overview-table-section {{
      margin-top: 26px;
      padding: 20px;
      border: 1px solid var(--line);
      border-radius: 24px;
      background: rgba(255, 250, 241, 0.88);
      box-shadow: 0 18px 42px rgba(77, 54, 22, 0.10);
    }}
    .section-title {{
      display: flex;
      justify-content: space-between;
      gap: 18px;
      align-items: end;
      margin-bottom: 14px;
    }}
    .section-title h1 {{ margin: 0; font-size: 24px; }}
    .section-title p {{ margin: 0; color: var(--muted); line-height: 1.6; max-width: 620px; }}
    .table-wrap {{ overflow-x: auto; border-radius: 16px; border: 1px solid rgba(70, 52, 27, 0.10); }}
    .overview-table {{
      width: 100%;
      min-width: 980px;
      border-collapse: collapse;
      background: rgba(255, 255, 255, 0.44);
      font-size: 13px;
    }}
    .overview-table th {{
      position: sticky;
      top: 0;
      z-index: 1;
      text-align: left;
      padding: 12px 12px;
      color: #415056;
      background: #f0e2c8;
      border-bottom: 1px solid var(--line);
      white-space: nowrap;
    }}
    .overview-table td {{
      padding: 12px;
      vertical-align: top;
      border-bottom: 1px solid rgba(70, 52, 27, 0.10);
      line-height: 1.55;
    }}
    .overview-table tbody tr:hover {{ background: rgba(31, 111, 120, 0.06); }}
    .table-bucket {{
      display: inline-flex;
      border-radius: 999px;
      padding: 5px 9px;
      background: rgba(31, 111, 120, 0.12);
      color: var(--accent-2);
      white-space: nowrap;
    }}
    .target-link {{ color: var(--ink); font-weight: 900; text-decoration: none; }}
    .target-link:hover {{ color: var(--accent); }}
    .status-pill {{
      display: inline-flex;
      border-radius: 999px;
      padding: 5px 9px;
      background: rgba(182, 75, 44, 0.11);
      color: var(--accent);
      white-space: nowrap;
    }}
    .mono {{ font-family: Consolas, "Liberation Mono", monospace; font-weight: 700; color: var(--accent-2); }}
    .support {{ margin-top: 34px; padding-top: 18px; border-top: 1px solid var(--line); color: var(--muted); line-height: 1.7; }}
    .support p {{ margin: 12px 0 0; }}
    @media (max-width: 860px) {{
      .section-title {{ display: block; }}
      .section-title p {{ margin-top: 8px; }}
    }}
  </style>
</head>
<body>
<main>
  <header>
    <h1>ETF 标的观察总览</h1>
    <p>首页按实际观察标的组织：先看 ETF / 指数本身，再进入它映射到的申万二级行业图形页。生成时间：{escape(generated_at)}</p>
  </header>
  {_overview_table(ETF_CARDS)}
  <footer class="support">
    <div class="nav">
      <a href="theme_watch_sop.md">SOP</a>
      <a href="daily_update_runbook.md">每日更新手册</a>
      <a href="theme_to_sw_watchlist.md">映射清单</a>
    </div>
    <p>以上内容仅用于个人研究、数据观察和策略复盘，不构成任何投资建议、买卖依据或收益承诺。</p>
  </footer>
</main>
</body>
</html>
"""
    OUTPUT_HTML.write_text(html, encoding="utf-8")
    print(f"wrote {OUTPUT_HTML}")


if __name__ == "__main__":
    build_dashboard()
