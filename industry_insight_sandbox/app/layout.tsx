import type { Metadata } from "next";
import "./globals.css";


export const metadata: Metadata = {
  title: "ETF与主题指数核心成分读数总览",
  description:
    "在隔离沙盒中，以ETF真实跟踪指数和指数权重核心成分股记录长期低于MA250 行业的均线与成交额读数。",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
