import type { Metadata } from "next";
import dashboardData from "../../../data/hk_qdii/513970-sh.json";
import HKQdiiDashboard from "../../components/HKQdiiDashboard";


export const metadata: Metadata = {
  title: "513970 恒生消费ETF · 行业读数",
  description:
    "使用ETF价格代理、ETF成交活跃度和恒生消费官方前十大成分股记录513970的行业读数。",
};

export default function HkQdii513970Page() {
  return <HKQdiiDashboard dashboardData={dashboardData} />;
}
