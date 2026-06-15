from __future__ import annotations

from datetime import datetime
from html import escape
from pathlib import Path


ROOT = Path(__file__).resolve().parent
REPORT_DIR = ROOT / "reports" / "theme_watch"
OUTPUT_HTML = REPORT_DIR / "index.html"


THEMES = [
    {
        "group": "电力设备",
        "title": "电网设备主题",
        "etfs": "931994.CSI",
        "core": "801738.SI 电网设备",
        "status": "趋势延续型偏强",
        "note": "电网设备映射非常纯，和光伏同属电力设备但不合并。",
        "href": "pages/theme_931994_sw_l2_watch_report.html",
    },
    {
        "group": "电力设备",
        "title": "光伏主题",
        "etfs": "515790.SH",
        "core": "801735.SI 光伏设备",
        "status": "趋势延续型偏强",
        "note": "光伏设备相关性 0.9761，单独观察。",
        "href": "pages/theme_515790_sw_l2_watch_report.html",
    },
    {
        "group": "科技成长",
        "title": "半导体主题",
        "etfs": "512480.SH",
        "core": "801081.SI 半导体",
        "status": "趋势延续型偏强 / 过热预警",
        "note": "趋势已经展开，更多是跟踪和拥挤度观察。",
        "href": "pages/theme_512480_sw_l2_watch_report.html",
    },
    {
        "group": "科技成长",
        "title": "软件计算机主题组",
        "etfs": "515230.SH / 159998.SZ",
        "core": "801104.SI 软件开发、801103.SI IT服务Ⅱ、801101.SI 计算机设备",
        "status": "未启动",
        "note": "从证券扩散对象中拆出，独立观察计算机链条。",
        "href": "pages/theme_fintech_computer_compare_report.html",
    },
    {
        "group": "科技成长",
        "title": "传媒主题",
        "etfs": "512980.SH",
        "core": "801767.SI 数字媒体、801765.SI 广告营销、801764.SI 游戏Ⅱ",
        "status": "未启动为主",
        "note": "传媒链条集中，部分二级未纳入主扫描池。",
        "href": "pages/theme_512980_sw_l2_watch_report.html",
    },
    {
        "group": "消费医药",
        "title": "消费酒主题组",
        "etfs": "159928.SZ / 512690.SH",
        "core": "801125.SI 白酒Ⅱ、801129.SI 调味发酵品Ⅱ",
        "status": "白酒未启动，调味发酵品观察中",
        "note": "消费 ETF 和酒 ETF top5 完全重叠，已合并。",
        "href": "pages/theme_consumption_liquor_sw_l2_watch_report.html",
    },
    {
        "group": "消费医药",
        "title": "医药医疗主题组",
        "etfs": "512010.SH / 512170.SH",
        "core": "801156.SI 医疗服务、801153.SI 医疗器械",
        "status": "未启动",
        "note": "医药和医疗 top5 高度重叠，已合并。",
        "href": "pages/theme_healthcare_sw_l2_watch_report.html",
    },
    {
        "group": "消费医药",
        "title": "家电主题",
        "etfs": "159996.SZ",
        "core": "801113.SI 小家电、801116.SI 家电零部件Ⅱ、801111.SI 白色家电",
        "status": "白色家电观察中",
        "note": "专题页按家电内部链条展示，不机械采用相关性前五。",
        "href": "pages/theme_159996_sw_l2_watch_report.html",
    },
    {
        "group": "周期红利",
        "title": "周期资源主题组",
        "etfs": "159930.SZ / 159697.SZ / 515220.SH",
        "core": "801951.SI 煤炭开采、801963.SI 炼化及贸易、801962.SI 油服工程",
        "status": "煤炭拥挤偏高，燃气观察中",
        "note": "不含化工，化工已单独对照。",
        "href": "pages/theme_cycle_resources_sw_l2_watch_report.html",
    },
    {
        "group": "周期红利",
        "title": "化工对照组",
        "etfs": "159870.SZ",
        "core": "801034.SI 化学制品、801038.SI 农化制品、801033.SI 化学原料",
        "status": "观察中为主，部分拥挤偏高",
        "note": "与能源/石油/煤炭 top5 重叠为 0，单独观察。",
        "href": "pages/theme_159870_chemical_compare_report.html",
    },
    {
        "group": "周期红利",
        "title": "易方达红利 ETF",
        "etfs": "515180.SH",
        "core": "801951.SI 煤炭开采、801963.SI 炼化及贸易、801179.SI 铁路公路",
        "status": "未启动为主",
        "note": "偏高股息资源/交运/基建组合。",
        "href": "pages/theme_515180_sw_l2_watch_report.html",
    },
    {
        "group": "周期红利",
        "title": "红利低波 ETF",
        "etfs": "512890.SH",
        "core": "801784.SI 城商行Ⅱ、801785.SI 农商行Ⅱ、801783.SI 股份制银行Ⅱ",
        "status": "银行链条观察中",
        "note": "和红利 ETF 风格相近但行业结构不同，不合并。",
        "href": "pages/theme_512890_sw_l2_watch_report.html",
    },
    {
        "group": "金融地产",
        "title": "证券主题",
        "etfs": "512880.SH",
        "core": "801193.SI 证券Ⅱ、801191.SI 多元金融、801194.SI 保险Ⅱ",
        "status": "未启动",
        "note": "软件/计算机已排除到独立对照组。",
        "href": "pages/theme_512880_sw_l2_watch_report.html",
    },
    {
        "group": "金融地产",
        "title": "房地产低相关校验",
        "etfs": "512200.SH",
        "core": "801181.SI 房地产开发、801183.SI 房地产服务",
        "status": "低相关异常",
        "note": "与房地产申万二级相关性偏低，需要核对跟踪指数/数据口径。",
        "href": "pages/theme_512200_real_estate_check_report.html",
    },
]


def _render_cards() -> str:
    grouped: dict[str, list[dict[str, str]]] = {}
    for theme in THEMES:
        grouped.setdefault(theme["group"], []).append(theme)

    sections: list[str] = []
    for group, themes in grouped.items():
        cards = []
        for theme in themes:
            cards.append(
                f"""
<article class="theme-card">
  <div class="card-top">
    <span class="group-tag">{escape(group)}</span>
    <a href="{escape(theme['href'])}">打开专题页</a>
  </div>
  <h2>{escape(theme['title'])}</h2>
  <p class="etfs">{escape(theme['etfs'])}</p>
  <dl>
    <dt>核心申万二级</dt><dd>{escape(theme['core'])}</dd>
    <dt>当前状态</dt><dd>{escape(theme['status'])}</dd>
    <dt>备注</dt><dd>{escape(theme['note'])}</dd>
  </dl>
</article>
"""
            )
        sections.append(
            f"""
<section>
  <h1>{escape(group)}</h1>
  <div class="grid">{''.join(cards)}</div>
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
  <title>ETF 主题观察总览</title>
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
    section {{ margin-top: 30px; }}
    section > h1 {{ margin: 0 0 14px; font-size: 22px; }}
    .grid {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }}
    .theme-card {{
      padding: 18px;
      border: 1px solid var(--line);
      border-radius: 22px;
      background: rgba(255, 250, 241, 0.9);
      box-shadow: 0 16px 38px rgba(70, 52, 27, 0.10);
      backdrop-filter: blur(8px);
    }}
    .card-top {{ display: flex; justify-content: space-between; align-items: center; gap: 10px; }}
    .group-tag {{
      display: inline-block;
      padding: 6px 10px;
      border-radius: 999px;
      background: rgba(31, 111, 120, 0.13);
      color: var(--accent-2);
      font-size: 12px;
    }}
    a {{ color: var(--accent); text-decoration: none; font-weight: 700; }}
    .theme-card h2 {{ margin: 14px 0 4px; font-size: 23px; }}
    .etfs {{ margin: 0 0 14px; color: var(--muted); font-weight: 700; }}
    dl {{ margin: 0; display: grid; grid-template-columns: 88px 1fr; gap: 9px 12px; }}
    dt {{ color: var(--muted); }}
    dd {{ margin: 0; line-height: 1.55; }}
    footer {{ margin-top: 30px; color: var(--muted); line-height: 1.7; }}
    @media (max-width: 860px) {{
      .grid {{ grid-template-columns: 1fr; }}
      dl {{ grid-template-columns: 1fr; }}
      dt {{ font-weight: 700; }}
    }}
  </style>
</head>
<body>
<main>
  <header>
    <h1>ETF 主题观察总览</h1>
    <p>生成时间：{escape(generated_at)}</p>
    <p>这个页面是入口页：先从这里选择主题，再进入对应专题图形页看年线、收敛路径、拥挤度和龙头状态。</p>
  </header>
  {_render_cards()}
  <footer>
    <p>规则：同一批申万二级高度重叠的 ETF 合并为主题组；行业归属不同但走势相关的对象放入对照组；相关性异常低的对象单独做校验页。</p>
  </footer>
</main>
</body>
</html>
"""
    OUTPUT_HTML.write_text(html, encoding="utf-8")
    print(f"wrote {OUTPUT_HTML}")


if __name__ == "__main__":
    build_dashboard()
