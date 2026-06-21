from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parent
REPORT_DIR = ROOT / "reports" / "theme_watch"
PAGE_DIR = REPORT_DIR / "pages"
CORRELATION_DIR = REPORT_DIR / "correlations"

THEME_DAILIES = [
    {"ts_code": "931994.CSI", "source": "index", "output": "theme_931994_to_sw_l2_correlation.csv"},
    {"ts_code": "512480.SH", "source": "fund", "output": "theme_512480_to_sw_l2_correlation.csv"},
    {"ts_code": "515790.SH", "source": "fund", "output": "theme_515790_to_sw_l2_correlation.csv"},
    {"ts_code": "515180.SH", "source": "fund", "output": "theme_515180_to_sw_l2_correlation.csv"},
    {"ts_code": "512890.SH", "source": "fund", "output": "theme_512890_to_sw_l2_correlation.csv"},
    {"ts_code": "159928.SZ", "source": "fund", "output": "theme_159928_to_sw_l2_correlation.csv"},
    {"ts_code": "512690.SH", "source": "fund", "output": "theme_512690_to_sw_l2_correlation.csv"},
    {"ts_code": "512010.SH", "source": "fund", "output": "theme_512010_to_sw_l2_correlation.csv"},
    {"ts_code": "512170.SH", "source": "fund", "output": "theme_512170_to_sw_l2_correlation.csv"},
    {"ts_code": "159992.SZ", "source": "fund", "output": "theme_159992_to_sw_l2_correlation.csv"},
    {"ts_code": "512980.SH", "source": "fund", "output": "theme_512980_to_sw_l2_correlation.csv"},
    {"ts_code": "159996.SZ", "source": "fund", "output": "theme_159996_to_sw_l2_correlation.csv"},
    {"ts_code": "159930.SZ", "source": "fund", "output": "theme_159930_to_sw_l2_correlation.csv"},
    {"ts_code": "159697.SZ", "source": "fund", "output": "theme_159697_to_sw_l2_correlation.csv"},
    {"ts_code": "515220.SH", "source": "fund", "output": "theme_515220_to_sw_l2_correlation.csv"},
    {"ts_code": "159870.SZ", "source": "fund", "output": "theme_159870_to_sw_l2_correlation.csv"},
    {"ts_code": "512200.SH", "source": "fund", "output": "theme_512200_to_sw_l2_correlation.csv"},
    {"ts_code": "512880.SH", "source": "fund", "output": "theme_512880_to_sw_l2_correlation.csv"},
    {"ts_code": "515230.SH", "source": "fund", "output": "theme_515230_to_sw_l2_correlation.csv"},
    {"ts_code": "159998.SZ", "source": "fund", "output": "theme_159998_to_sw_l2_correlation.csv"},
]

TOPIC_PAGES = [
    {
        "title": "电网设备主题 - 申万二级关联观察",
        "codes": ["801738.SI", "801733.SI", "801074.SI", "801072.SI", "801736.SI"],
        "output": "theme_931994_sw_l2_watch_report.html",
    },
    {
        "title": "光伏主题 - 申万二级关联观察",
        "codes": ["801735.SI", "801736.SI", "801737.SI", "801733.SI", "801738.SI"],
        "output": "theme_515790_sw_l2_watch_report.html",
    },
    {
        "title": "半导体主题 - 申万二级关联观察",
        "codes": ["801081.SI", "801086.SI", "801101.SI", "801082.SI", "801078.SI"],
        "output": "theme_512480_sw_l2_watch_report.html",
    },
    {
        "title": "软件 ETF 观察组 - 申万二级关联观察",
        "codes": ["801104.SI", "801103.SI"],
        "output": "theme_515230_software_watch_report.html",
    },
    {
        "title": "计算机 ETF 观察组 - 申万二级关联观察",
        "codes": ["801101.SI"],
        "output": "theme_159998_computer_watch_report.html",
    },
    {
        "title": "通信链条对照组 - 申万二级关联观察",
        "codes": ["801102.SI", "801223.SI"],
        "output": "theme_communication_compare_report.html",
    },
    {
        "title": "传媒主题 - 申万二级关联观察",
        "codes": ["801767.SI", "801765.SI", "801764.SI", "801769.SI", "801995.SI"],
        "output": "theme_512980_sw_l2_watch_report.html",
    },
    {
        "title": "消费酒主题组 - 申万二级关联观察",
        "codes": ["801125.SI", "801126.SI", "801129.SI", "801127.SI", "801124.SI"],
        "output": "theme_consumption_liquor_sw_l2_watch_report.html",
    },
    {
        "title": "医药医疗主题组 - 申万二级关联观察",
        "codes": ["801156.SI", "801153.SI", "801152.SI", "801151.SI", "801155.SI"],
        "output": "theme_healthcare_sw_l2_watch_report.html",
    },
    {
        "title": "医药 ETF 观察组 - 申万二级关联观察",
        "codes": ["801156.SI", "801152.SI", "801151.SI", "801153.SI", "801155.SI"],
        "output": "theme_512010_medicine_watch_report.html",
    },
    {
        "title": "医疗 ETF 观察组 - 申万二级关联观察",
        "codes": ["801156.SI", "801153.SI", "801152.SI", "801151.SI", "801155.SI"],
        "output": "theme_512170_healthcare_watch_report.html",
    },
    {
        "title": "创新药 ETF 观察组 - 申万二级关联观察",
        "codes": ["801151.SI", "801152.SI", "801156.SI"],
        "output": "theme_159992_innovative_drug_watch_report.html",
    },
    {
        "title": "家电主题 - 申万二级关联观察",
        "codes": ["801113.SI", "801116.SI", "801112.SI", "801114.SI", "801111.SI"],
        "output": "theme_159996_sw_l2_watch_report.html",
    },
    {
        "title": "周期资源主题组 - 申万二级关联观察",
        "codes": ["801951.SI", "801963.SI", "801962.SI", "801163.SI", "801992.SI", "801952.SI"],
        "output": "theme_cycle_resources_sw_l2_watch_report.html",
    },
    {
        "title": "基础化工对照组 - 申万二级关联观察",
        "codes": ["801034.SI", "801038.SI", "801033.SI", "801043.SI", "801032.SI"],
        "output": "theme_159870_chemical_compare_report.html",
    },
    {
        "title": "易方达红利 ETF - 申万二级关联观察",
        "codes": ["801951.SI", "801963.SI", "801179.SI", "801992.SI", "801723.SI"],
        "output": "theme_515180_sw_l2_watch_report.html",
    },
    {
        "title": "红利低波 ETF - 申万二级关联观察",
        "codes": ["801784.SI", "801785.SI", "801783.SI", "801782.SI", "801951.SI"],
        "output": "theme_512890_sw_l2_watch_report.html",
    },
    {
        "title": "证券主题 - 申万二级关联观察",
        "codes": ["801193.SI", "801191.SI", "801194.SI"],
        "output": "theme_512880_sw_l2_watch_report.html",
    },
    {
        "title": "房地产 ETF 观察组 - 申万二级关联观察",
        "codes": ["801181.SI", "801183.SI", "801713.SI", "801721.SI", "801722.SI"],
        "output": "theme_512200_real_estate_watch_report.html",
    },
]
