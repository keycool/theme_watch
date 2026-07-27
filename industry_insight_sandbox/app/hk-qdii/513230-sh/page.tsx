import type { Metadata } from "next";
import dashboardData from "../../../data/hk_qdii/513230-sh.json";
import HKQdiiDashboard from "../../components/HKQdiiDashboard";


export const metadata: Metadata = {
  title: "017832 / 513230 港股通消费 · 行业启动观察",
  description:
    "从017832下沉到底层ETF 513230及中证港股通消费主题指数，直接观察指数结构、成交活跃度和正式权重成分股。",
};

export default function HkQdii513230Page() {
  return <HKQdiiDashboard dashboardData={dashboardData} />;
}
