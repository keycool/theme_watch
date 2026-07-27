import type { Metadata } from "next";
import dashboardData from "../../../data/hk_qdii/513970-sh.json";
import HKQdiiDashboard from "../../components/HKQdiiDashboard";


export const metadata: Metadata = {
  title: "513970 恒生消费ETF · 行业启动观察",
  description:
    "使用ETF价格代理、ETF成交活跃度和恒生消费官方前十大成分股观察513970行业启动状态。",
};

export default function HkQdii513970Page() {
  return <HKQdiiDashboard dashboardData={dashboardData} />;
}
