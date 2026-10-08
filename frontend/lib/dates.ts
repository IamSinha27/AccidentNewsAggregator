// Pure helpers for the API's YYYY-MM-DD days and YYYY-MM months. No
// environment access, so both server and client components can use them.

import type { Day, Totals } from "./api";

export type Month = {
  /** YYYY-MM */
  key: string;
  /** The days of this month that have data, oldest first. */
  days: Day[];
  totals: Totals;
};

const ZERO: Totals = { accidents: 0, fatal: 0, non_fatal: 0, deaths: 0, injured: 0 };

export function sumTotals(items: Totals[]): Totals {
  return items.reduce<Totals>(
    (sum, t) => ({
      accidents: sum.accidents + t.accidents,
      fatal: sum.fatal + t.fatal,
      non_fatal: sum.non_fatal + t.non_fatal,
      deaths: sum.deaths + t.deaths,
      injured: sum.injured + t.injured,
    }),
    ZERO,
  );
}

/** Groups the API's daily rows into months, oldest first. */
export function groupMonths(days: Day[]): Month[] {
  const byKey = new Map<string, Day[]>();
  for (const day of days) {
    const key = day.date.slice(0, 7);
    byKey.set(key, [...(byKey.get(key) ?? []), day]);
  }
  return [...byKey].map(([key, monthDays]) => ({ key, days: monthDays, totals: sumTotals(monthDays) }));
}

/** Returns `value` if it is a YYYY-MM-DD string, otherwise undefined. */
export function parseDay(value: string | string[] | undefined): string | undefined {
  return typeof value === "string" && /^\d{4}-\d{2}-\d{2}$/.test(value) ? value : undefined;
}

// Everything is parsed and formatted in UTC so a label never shifts by a day.
function utc(day: string) {
  return new Date(`${day.length === 7 ? `${day}-01` : day}T00:00:00Z`);
}

function format(day: string, options: Intl.DateTimeFormatOptions) {
  return new Intl.DateTimeFormat("en-IN", { ...options, timeZone: "UTC" }).format(utc(day));
}

/** "Wednesday, 7 October 2026" */
export const longDay = (day: string) => format(day, { weekday: "long", day: "numeric", month: "long", year: "numeric" });
/** "7 October 2026" */
export const fullDay = (day: string) => format(day, { day: "numeric", month: "long", year: "numeric" });
/** "7 Oct" */
export const shortDay = (day: string) => format(day, { day: "numeric", month: "short" });
/** "October 2026" */
export const monthName = (month: string) => format(month, { month: "long", year: "numeric" });
/** "Oct" */
export const monthShort = (month: string) => format(month, { month: "short" });
/** "Oct 2026" */
export const monthShortYear = (month: string) => format(month, { month: "short", year: "numeric" });

export const dayOfMonth = (day: string) => Number(day.slice(8, 10));

export function daysInMonth(month: string) {
  const [year, m] = month.split("-").map(Number);
  return new Date(Date.UTC(year, m, 0)).getUTCDate();
}

/** True if `later` is the calendar day right after `earlier`. */
export function isNextDay(earlier: string, later: string) {
  return utc(later).getTime() - utc(earlier).getTime() === 86_400_000;
}

/** en-IN digit grouping: 1,23,456 */
export const count = (n: number) => n.toLocaleString("en-IN");
