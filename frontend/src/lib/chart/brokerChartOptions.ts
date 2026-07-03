import {
  ColorType,
  CrosshairMode,
  LineStyle,
  type CandlestickSeriesPartialOptions,
  type ChartOptions,
  type DeepPartial,
  type IChartApi,
} from "lightweight-charts";

export const CANDLESTICK_SERIES_OPTIONS: CandlestickSeriesPartialOptions = {
  upColor: "#22c55e",
  downColor: "#ef4444",
  borderUpColor: "#0f1419",
  borderDownColor: "#0f1419",
  wickUpColor: "rgba(34, 197, 94, 0.8)",
  wickDownColor: "rgba(239, 68, 68, 0.8)",
};

type BrokerChartOptionsInput = {
  locked?: boolean;
  fontSize?: number;
  signalScaleMargin?: number;
  fixTimeScaleEdges?: boolean;
  secondsVisible?: boolean;
};

export function createBrokerChartOptions({
  locked = false,
  fontSize = 11,
  signalScaleMargin = 0.08,
  fixTimeScaleEdges = false,
  secondsVisible = false,
}: BrokerChartOptionsInput = {}): DeepPartial<ChartOptions> {
  return {
    layout: {
      background: { type: ColorType.Solid, color: "transparent" },
      textColor: "#8b9cb3",
      fontSize,
    },
    grid: {
      vertLines: { visible: false },
      horzLines: { color: "rgba(45, 58, 79, 0.4)" },
    },
    crosshair: {
      mode: locked ? CrosshairMode.Hidden : CrosshairMode.Normal,
      vertLine: {
        color: "#8b9cb3",
        style: LineStyle.Dashed,
        width: 1,
        labelVisible: true,
      },
      horzLine: {
        color: "#8b9cb3",
        style: LineStyle.Dashed,
        width: 1,
        labelVisible: true,
      },
    },
    rightPriceScale: {
      borderColor: "#2d3a4f",
      scaleMargins: {
        top: signalScaleMargin,
        bottom: signalScaleMargin,
      },
    },
    timeScale: {
      borderColor: "#2d3a4f",
      timeVisible: true,
      secondsVisible,
      rightOffset: 0,
      fixLeftEdge: fixTimeScaleEdges,
      fixRightEdge: fixTimeScaleEdges,
    },
    handleScroll: !locked,
    handleScale: !locked,
  };
}

export function fitTimeScaleToBounds(
  chart: IChartApi,
  barCount: number,
  options: { fixEdges?: boolean } = {},
) {
  if (barCount < 1) return;
  const timeScale = chart.timeScale();
  if (options.fixEdges) {
    timeScale.applyOptions({
      rightOffset: 0,
      fixLeftEdge: true,
      fixRightEdge: true,
    });
  }
  timeScale.setVisibleLogicalRange({
    from: 0,
    to: Math.max(barCount - 1, 0),
  });
}
