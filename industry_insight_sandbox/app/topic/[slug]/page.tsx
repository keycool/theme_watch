import type { Metadata } from "next";
import { notFound } from "next/navigation";
import allTopics from "../../../data/all_topics.json";
import TopicDashboard from "../../components/TopicDashboard";


export function generateStaticParams() {
  return allTopics.map((topic) => ({ slug: topic.target.slug }));
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string }>;
}): Promise<Metadata> {
  const { slug } = await params;
  const topic = allTopics.find((item) => item.target.slug === slug);
  if (!topic) return {};
  return {
    title: `${topic.target.name} · 核心成分启动观察`,
    description: `${topic.target.name}直接观察${topic.target.indexName}及指数权重核心成分股。`,
  };
}

export default async function TopicPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const topic = allTopics.find((item) => item.target.slug === slug);
  if (!topic) notFound();
  return <TopicDashboard dashboardData={topic} />;
}
