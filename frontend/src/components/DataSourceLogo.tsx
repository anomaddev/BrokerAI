import { getDataSource, type DataSource, type DataSourceId } from "../lib/dataSources";

type DataSourceLogoProps = {
  source: DataSource | DataSourceId;
  size?: number;
  className?: string;
};

export default function DataSourceLogo({
  source,
  size = 40,
  className = "exchange-logo",
}: DataSourceLogoProps) {
  const meta = typeof source === "string" ? getDataSource(source) : source;
  if (!meta?.logo) return null;

  return (
    <img
      src={meta.logo}
      alt=""
      className={className}
      width={size}
      height={size}
    />
  );
}
