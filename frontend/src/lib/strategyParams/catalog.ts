export const SIGNAL_CATALOG_SECTIONS = [
  {
    id: "limits",
    label: "Limits",
    signals: [
      {
        type: "monthly_high" as const,
        label: "Monthly High",
        description: "Enter when price breaks the current monthly high.",
      },
      {
        type: "monthly_low" as const,
        label: "Monthly Low",
        description: "Enter when price breaks the current monthly low.",
      },
    ],
  },
  {
    id: "events",
    label: "Events",
    signals: [
      {
        type: "ema_crossover" as const,
        label: "EMA Crossover",
        description: "Fast/slow EMA crossover entry signal.",
      },
    ],
  },
] as const;

export const SIGNAL_CATALOG = SIGNAL_CATALOG_SECTIONS.flatMap((section) => [...section.signals]);

export const FILTER_CATALOG = [
  {
    type: "adx" as const,
    id: "adx",
    label: "ADX filter",
    description: "Trend strength filter.",
  },
  {
    type: "atr" as const,
    id: "atr",
    label: "ATR filter",
    description: "Volatility range filter.",
  },
];

export type SignalCatalogType = (typeof SIGNAL_CATALOG)[number]["type"];
export type FilterCatalogType = (typeof FILTER_CATALOG)[number]["type"];

export function findSignalCatalogEntry(type: SignalCatalogType) {
  return SIGNAL_CATALOG.find((item) => item.type === type);
}
