import massiveLogo from "../assets/providers/massive.png";
import newsapiLogo from "../assets/providers/newsapi.png";

export type DataSourceId = "newsapi" | "massive";

export type DataSource = {
  id: DataSourceId;
  name: string;
  description: string;
  category: string;
  available: boolean;
  logo?: string;
};

export const DATA_SOURCES: DataSource[] = [
  {
    id: "newsapi",
    name: "NewsAPI",
    description: "Fetch news articles for research reports.",
    category: "News",
    available: true,
    logo: newsapiLogo,
  },
  {
    id: "massive",
    name: "Massive",
    description: "Stocks, forex, crypto, and futures market data via Massive.com.",
    category: "Market data",
    available: true,
    logo: massiveLogo,
  },
];

export type ApiKeyConnectionSummary = {
  api_key_set: boolean;
  enabled: boolean;
};

export function connectedDataSourceIds(
  connections: Partial<Record<DataSourceId, ApiKeyConnectionSummary>>,
): DataSourceId[] {
  return DATA_SOURCES.filter((source) => connections[source.id]?.api_key_set).map(
    (source) => source.id,
  );
}

export function getDataSource(dataSourceId: DataSourceId): DataSource | undefined {
  return DATA_SOURCES.find((source) => source.id === dataSourceId);
}

export function dataSourceName(dataSourceId: string | null | undefined): string | null {
  if (!dataSourceId) return null;
  return DATA_SOURCES.find((source) => source.id === dataSourceId)?.name ?? dataSourceId;
}
