# ETF 与主题指数核心成分启动观察

这是一个与现有生产策略隔离的观察沙盒。目标清单严格取自现有项目正式配置，共 20 个对象：

- 19 只 ETF
- 1 个主题指数
- 4 个项目分组

总览页展示全部对象的当前标签、三层条件状态、跟踪指数和核心成分摘要。点击任一对象标题，可进入独立专题页。

## 观察逻辑

原来的关系：

> ETF → 申万二级行业 → 申万行业龙头

本沙盒改为：

> ETF → 真实跟踪指数 → 指数权重核心成分股

对于项目中直接跟踪的主题指数，则使用：

> 主题指数 → 自身指数行情 → 指数权重核心成分股

三层启动条件保持为：

1. 低位形成收敛结构
2. 跟踪指数带量突破年线
3. 权重前 3 龙头出现涨停并延续

核心成分优先累计覆盖指数权重 60%，最多取 20 只。申万二级只作为成分股行业文字参照，不参与专题启动标签。

## 刷新数据

```powershell
py -B .\generate_dashboard_data.py
```

指定截止交易日：

```powershell
py -B .\generate_dashboard_data.py --end-date 20260717
```

生成内容：

- `data/overview.json`：总览数据
- `data/all_topics.json`：全部专题合集
- `data/topics/<slug>.json`：20 个独立专题数据

## 本地查看

```powershell
npm run dev
```

打开：

```text
http://localhost:3000/
```

专题路由格式：

```text
http://localhost:3000/topic/<slug>
```

## 验证

```powershell
npm test
```

测试会核对正式目标清单、总览数据和专题数据完全一致，并逐个服务端渲染全部 20 个专题。

## 独立 workflow

仓库根目录提供独立编排器，不调用原有申万二级 workflow：

```powershell
py -B .\run_etf_constituent_workflow.py --end-date 20260717
```

仅校验已有结果：

```powershell
py -B .\run_etf_constituent_workflow.py --end-date 20260717 --validate-only
```

GitHub Actions 配置为 `.github/workflows/etf-constituent-daily.yml`，工作日北京时间
20:30 自动运行，也支持手动指定交易日。运行产物包括 workflow 日志、20 个专题数据、
总览数据和站点构建结果。计算完成后还会复用仓库现有的
`Theme_Watch_FEISHU_WEBHOOK_URL` 与 `Theme_Watch_FEISHU_WEBHOOK_SECRET`
发送独立的 ETF 核心成分观察摘要。

独立观察网页：

```text
https://etf-core-constituent-watch.keyhf78.chatgpt.site
```

workflow 每次成功计算后，会把最新总览和 20 个专题 JSON 发布到专用
`etf-watch-data` 分支。网页启动后从该分支读取最新数据，失败时才回退到内置快照，
因此日常更新不需要覆盖原有主题报告的 GitHub Pages。

## 隔离边界

- 不导入现有生产策略引擎。
- 不读取或写入 `.cache_scan_v2`。
- 不运行 `run_theme_watch_workflow.py` 或 `run_sw_l2_strategy_scan.py`。
- 不修改 `reports/theme_watch/`。
- 所有代码、数据、构建产物和页面均位于本沙盒目录。
