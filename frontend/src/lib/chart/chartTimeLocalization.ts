import {
  TickMarkType,
  type IChartApi,
  type Time,
} from "lightweight-charts";
import {
  createChartDateFormatter,
  createChartTimeFormatter,
  type TimeFormatOptions,
} from "../formatTime";

function effectiveTimeZone(options: TimeFormatOptions): string {
  return options.showUtc ? "UTC" : options.timeZone;
}

function timeToDate(time: Time): Date | null {
  if (typeof time === "number") {
    const date = new Date(time * 1000);
    return Number.isNaN(date.getTime()) ? null : date;
  }

  if (typeof time === "string") {
    const date = new Date(time);
    return Number.isNaN(date.getTime()) ? null : date;
  }

  if (time && typeof time === "object" && "year" in time) {
    const businessDay = time as { year: number; month: number; day: number };
    return new Date(Date.UTC(businessDay.year, businessDay.month - 1, businessDay.day));
  }

  return null;
}

export function createChartTickMarkFormatter(options: TimeFormatOptions) {
  const timeZone = effectiveTimeZone(options);

  return (time: Time, tickMarkType: TickMarkType): string | null => {
    const date = timeToDate(time);
    if (!date) return null;

    switch (tickMarkType) {
      case TickMarkType.Year:
        return new Intl.DateTimeFormat(undefined, {
          timeZone,
          year: "numeric",
        }).format(date);
      case TickMarkType.Month:
        return new Intl.DateTimeFormat(undefined, {
          timeZone,
          month: "short",
        }).format(date);
      case TickMarkType.DayOfMonth:
        return new Intl.DateTimeFormat(undefined, {
          timeZone,
          day: "numeric",
        }).format(date);
      case TickMarkType.Time: {
        const hour12 = options.timeFormat === "12h";
        const formatted = new Intl.DateTimeFormat(undefined, {
          timeZone,
          hour: "2-digit",
          minute: "2-digit",
          hour12,
        }).format(date);
        return options.showUtc ? `${formatted}` : formatted;
      }
      case TickMarkType.TimeWithSeconds:
        return new Intl.DateTimeFormat(undefined, {
          timeZone,
          hour: "2-digit",
          minute: "2-digit",
          second: "2-digit",
          hour12: options.timeFormat === "12h",
        }).format(date);
      default:
        return null;
    }
  };
}

export function applyChartTimeLocalization(
  charts: IChartApi[],
  timeOptions: TimeFormatOptions,
): void {
  if (charts.length === 0) return;

  const localization = {
    timeFormatter: createChartTimeFormatter(timeOptions),
    dateFormatter: createChartDateFormatter(timeOptions),
  };
  const tickMarkFormatter = createChartTickMarkFormatter(timeOptions);

  for (const chart of charts) {
    chart.applyOptions({
      localization,
      timeScale: { tickMarkFormatter },
    });
  }
}
