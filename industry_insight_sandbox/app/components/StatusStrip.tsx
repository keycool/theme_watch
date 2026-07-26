type StatusStripProps = {
  generatedAt: string;
  latestDate: string;
};

function formatDate(value: string) {
  const compact = value.replace(/\D/g, "");
  if (compact.length < 8) return value;
  return `${compact.slice(0, 4)}-${compact.slice(4, 6)}-${compact.slice(6, 8)}`;
}

export default function StatusStrip({
  generatedAt,
  latestDate,
}: StatusStripProps) {
  const formattedLatestDate = formatDate(latestDate);

  return (
    <div
      className="status-strip"
      aria-label={`实时数据状态，数据截止 ${formattedLatestDate}，生成于 ${generatedAt}`}
    >
      <span className="status-pill status-pill-live">
        <i aria-hidden="true" />
        LIVE
      </span>
      <span className="status-pill">
        <span>数据截止</span>
        <time dateTime={latestDate}>{formattedLatestDate}</time>
      </span>
      <span className="status-pill">
        <span>生成于</span>
        <time dateTime={generatedAt.replace(" ", "T")}>{generatedAt}</time>
      </span>
    </div>
  );
}
