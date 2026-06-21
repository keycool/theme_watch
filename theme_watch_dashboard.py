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
        "note": "趋势已展开，更适合观察回踩和拥挤度，不应误判为刚启动。",
        "href": "pages/theme_512480_sw_l2_watch_report.html",
    },
    {
        "bucket": "科技成长与高端制造",
        "code": "515790.SH",
        "name": "光伏 ETF",
        "map": "801735.SI 光伏设备",
        "status": "趋势延续",
        "note": "和电网设备同属电力设备大链条，但单独观察。",
        "href": "pages/theme_515790_sw_l2_watch_report.html",
    },
    {
        "bucket": "科技成长与高端制造",
        "code": "515230.SH",
        "name": "软件 ETF",
        "map": "801104.SI 软件开发、801103.SI IT服务Ⅱ",
        "status": "未启动 / 拥挤正常",
        "note": "软件开发和 IT 服务为核心，不再和计算机设备混成一个大组。",
        "href": "pages/theme_515230_software_watch_report.html",
    },
    {
        "bucket": "科技成长与高端制造",
        "code": "159998.SZ",
        "name": "计算机 ETF",
        "map": "801101.SI 计算机设备",
        "status": "未启动 / 拥挤正常",
        "note": "单独观察设备链，通信链条只作为扩散对照。",
        "href": "pages/theme_159998_computer_watch_report.html",
    },
    {
        "bucket": "大消费与医药",
        "code": "512980.SH",
        "name": "传媒 ETF",
        "map": "801767.SI 数字媒体、801765.SI 广告营销、801764.SI 游戏Ⅱ",
        "status": "未启动 / 拥挤正常",
        "note": "传媒链条集中，部分二级未纳入主扫描池。",
        "href": "pages/theme_512980_sw_l2_watch_report.html",
    },
    {
        "bucket": "科技成长与高端制造",
        "code": "931994.CSI",
        "name": "电网设备主题指数",
        "map": "801738.SI 电网设备",
        "status": "趋势延续",
        "note": "不是 ETF，但作为实际观察标的纳入首页。",
        "href": "pages/theme_931994_sw_l2_watch_report.html",
    },
    {
        "bucket": "科技成长与高端制造",
        "code": "TMT-COMM",
        "name": "通信链条对照组",
        "map": "801102.SI 通信设备、801223.SI 通信服务",
        "status": "未启动 / 观察中",
        "note": "归入科技成长板块，但仍作为软件/计算机的扩散对照，不作为独立 ETF 入口。",
        "href": "pages/theme_communication_compare_report.html",
    },
    {
        "bucket": "大消费与医药",
        "code": "159928.SZ",
        "name": "消费 ETF",
        "map": "801125.SI 白酒Ⅱ、801129.SI 调味发酵品Ⅱ、801127.SI 饮料乳品",
        "status": "未启动 / 观察中",
        "note": "和酒 ETF 高度重叠，入口单列，详情共用消费酒观察页。",
        "href": "pages/theme_consumption_liquor_sw_l2_watch_report.html",
    },
    {
        "bucket": "大消费与医药",
        "code": "512690.SH",
        "name": "酒 ETF",
        "map": "801125.SI 白酒Ⅱ、801128.SI 非白酒",
        "status": "未启动",
        "note": "消费酒链条的窄基入口，详情共用消费酒观察页。",
        "href": "pages/theme_consumption_liquor_sw_l2_watch_report.html",
    },
    {
        "bucket": "大消费与医药",
        "code": "512010.SH",
        "name": "医药 ETF",
        "map": "医疗服务、生物制品、化学制药、医疗器械、中药Ⅱ",
        "status": "未启动 / 观察中",
        "note": "宽基医药入口，适合看医药生物整体修复。",
        "href": "pages/theme_512010_medicine_watch_report.html",
    },
    {
        "bucket": "大消费与医药",
        "code": "512170.SH",
        "name": "医疗 ETF",
        "map": "801156.SI 医疗服务、801153.SI 医疗器械",
        "status": "未启动 / 观察中",
        "note": "更偏医疗服务和医疗器械，和创新药链条分开观察。",
        "href": "pages/theme_512170_healthcare_watch_report.html",
    },
    {
        "bucket": "大消费与医药",
        "code": "159992.SZ",
        "name": "创新药 ETF",
        "map": "801151.SI 化学制药、801152.SI 生物制品、801156.SI 医疗服务",
        "status": "未启动 / 观察中",
        "note": "更偏创新药和 CXO 服务链。",
        "href": "pages/theme_159992_innovative_drug_watch_report.html",
    },
    {
        "bucket": "大消费与医药",
        "code": "159996.SZ",
        "name": "家电 ETF",
        "map": "小家电、家电零部件Ⅱ、黑色家电、厨卫电器、白色家电",
        "status": "观察中",
        "note": "按家电内部链条展示，不机械采用相关性前五。",
        "href": "pages/theme_159996_sw_l2_watch_report.html",
    },
    {
        "bucket": "周期资源",
        "code": "159930.SZ",
        "name": "能源 ETF",
        "map": "煤炭开采、炼化及贸易、油服工程、燃气Ⅱ",
        "status": "观察中 / 拥挤正常",
        "note": "行业属性更强；和易方达红利在煤炭、炼化、交运等高股息资源资产上有重叠。",
        "href": "pages/theme_cycle_resources_sw_l2_watch_report.html",
    },
    {
        "bucket": "周期资源",
        "code": "159697.SZ",
        "name": "石油 ETF",
        "map": "炼化及贸易、油服工程、燃气Ⅱ",
        "status": "观察中 / 拥挤正常",
        "note": "纳入周期资源页，和煤炭/能源一起看资源链。",
        "href": "pages/theme_cycle_resources_sw_l2_watch_report.html",
    },
    {
        "bucket": "周期资源",
        "code": "515220.SH",
        "name": "煤炭 ETF",
        "map": "801951.SI 煤炭开采、801952.SI 焦炭Ⅱ",
        "status": "观察中 / 拥挤正常",
        "note": "更像高股息/资源防御端，重点防止过热消退。",
        "href": "pages/theme_cycle_resources_sw_l2_watch_report.html",
    },
    {
        "bucket": "周期资源",
        "code": "159870.SZ",
        "name": "化工 ETF",
        "map": "化学制品、农化制品、化学原料、冶钢原料、化学纤维",
        "status": "观察中 / 拥挤偏高",
        "note": "和能源/煤炭拆开，作为基础化工对照。",
        "href": "pages/theme_159870_chemical_compare_report.html",
    },
    {
        "bucket": "红利金融地产",
        "code": "515180.SH",
        "name": "易方达红利 ETF",
        "map": "煤炭开采、炼化及贸易、铁路公路、航运港口、基础建设",
        "status": "未启动 / 观察中",
        "note": "偏高股息资源/交运/基建组合；和能源 ETF 有重叠，但这里主要作为红利风格观察。",
        "href": "pages/theme_515180_sw_l2_watch_report.html",
    },
    {
        "bucket": "红利金融地产",
        "code": "512890.SH",
        "name": "红利低波 ETF",
        "map": "城商行Ⅱ、农商行Ⅱ、股份制银行Ⅱ、国有大型银行Ⅱ",
        "status": "观察中",
        "note": "和红利 ETF 风格相近，但行业结构不同，不合并。",
        "href": "pages/theme_512890_sw_l2_watch_report.html",
    },
    {
        "bucket": "红利金融地产",
        "code": "512880.SH",
        "name": "证券 ETF",
        "map": "801193.SI 证券Ⅱ、801191.SI 多元金融、801194.SI 保险Ⅱ",
        "status": "观察中 / 拥挤正常",
        "note": "软件/计算机已排除到独立观察页。",
        "href": "pages/theme_512880_sw_l2_watch_report.html",
    },
    {
        "bucket": "红利金融地产",
        "code": "512200.SH",
        "name": "房地产 ETF",
        "map": "房地产开发、房地产服务、装修建材、房屋建设Ⅱ、装修装饰Ⅱ",
        "status": "未启动 / 拥挤正常",
        "note": "改用 Tushare 涨跌幅字段后，和房地产开发相关性约 0.98，已从低相关校验转为正式观察。",
        "href": "pages/theme_512200_real_estate_watch_report.html",
    },
]


def _group_cards(cards: list[dict[str, str]]) -> str:
    grouped: dict[str, list[dict[str, str]]] = {}
    for card in cards:
        grouped.setdefault(card["bucket"], []).append(card)

    sections: list[str] = []
    for bucket, bucket_cards in grouped.items():
        rendered_cards = []
        for card in bucket_cards:
            rendered_cards.append(
                f"""
<article class="theme-card">
  <div class="card-top">
    <span class="group-tag">{escape(bucket)}</span>
    <a href="{escape(card['href'])}">打开观察页</a>
  </div>
  <p class="code">{escape(card['code'])}</p>
  <h2>{escape(card['name'])}</h2>
  <dl>
    <dt>映射申万二级</dt><dd>{escape(card['map'])}</dd>
    <dt>当前状态</dt><dd>{escape(card['status'])}</dd>
    <dt>备注</dt><dd>{escape(card['note'])}</dd>
  </dl>
</article>
"""
            )
        sections.append(
            f"""
<section>
  <h1>{escape(bucket)}</h1>
  <div class="grid">{''.join(rendered_cards)}</div>
</section>
"""
        )
    return "\n".join(sections)


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
    .nav {{ display: flex; flex-wrap: wrap; gap: 10px; margin-top: 18px; }}
    .nav a {{
      color: var(--accent-2);
      text-decoration: none;
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 8px 12px;
      background: rgba(255, 250, 241, 0.72);
    }}
    section {{ margin-top: 30px; }}
    section > h1 {{ margin: 0 0 14px; font-size: 22px; }}
    .grid {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }}
    .theme-card {{
      padding: 18px;
      border: 1px solid var(--line);
      border-radius: 22px;
      background: rgba(255, 250, 241, 0.9);
      box-shadow: 0 18px 42px rgba(77, 54, 22, 0.10);
    }}
    .card-top {{ display: flex; justify-content: space-between; gap: 14px; align-items: center; }}
    .group-tag {{
      display: inline-flex;
      border-radius: 999px;
      padding: 6px 10px;
      background: rgba(31, 111, 120, 0.12);
      color: var(--accent-2);
      font-size: 12px;
    }}
    .card-top a {{ color: var(--accent); text-decoration: none; font-weight: 700; }}
    .code {{ margin: 16px 0 4px; color: var(--accent-2); font-weight: 800; letter-spacing: 0.02em; }}
    h2 {{ margin: 0 0 12px; font-size: 24px; }}
    dl {{ margin: 0; display: grid; grid-template-columns: 100px 1fr; gap: 8px 12px; }}
    dt {{ color: var(--muted); }}
    dd {{ margin: 0; line-height: 1.55; }}
    .support {{ margin-top: 44px; padding-top: 10px; border-top: 1px solid var(--line); }}
    @media (max-width: 860px) {{
      .grid {{ grid-template-columns: 1fr; }}
      dl {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
<main>
  <header>
    <h1>ETF 标的观察总览</h1>
    <p>首页按实际观察标的组织：先看 ETF / 指数本身，再进入它映射到的申万二级行业图形页。生成时间：{escape(generated_at)}</p>
    <div class="nav">
      <a href="theme_watch_sop.md">SOP</a>
      <a href="daily_update_runbook.md">每日更新手册</a>
      <a href="theme_to_sw_watchlist.md">映射清单</a>
    </div>
  </header>
  {_group_cards(ETF_CARDS)}
</main>
</body>
</html>
"""
    OUTPUT_HTML.write_text(html, encoding="utf-8")
    print(f"wrote {OUTPUT_HTML}")


if __name__ == "__main__":
    build_dashboard()
