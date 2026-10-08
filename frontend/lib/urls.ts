// Every view lives in the URL, so it can be linked to and the back button works.
//
//   /                              overview, latest month
//   /?month=2026-09                overview for another month
//   /?scope=day&day=2026-10-07     overview with the state map narrowed to a day
//   /?scope=all                    overview with the state map over all time
//   /?date=2026-10-07              one day's articles
//   /?state=Goa&...                one state's articles, for the same month/day/all-time choice

import type { Period, Severity } from "./api";
import { type Month, fullDay, monthName } from "./dates";

export type ScopeKind = "day" | "month" | "all";

/** What the state map (and a state's article list) covers. */
export type Scope = {
  kind: ScopeKind;
  /** The month shown in the charts; also the period when kind is "month". */
  month: string;
  /** The period when kind is "day"; otherwise the day that scope would open on. */
  day: string;
};

type Params = Record<string, string | string[] | undefined>;

const one = (value: string | string[] | undefined) => (typeof value === "string" ? value : undefined);

/** Reads the scope from the URL, falling back to the latest month that has data. */
export function resolveScope(months: Month[], params: Params): Scope {
  const wantedDay = one(params.day);
  const month =
    months.find((m) => m.key === one(params.month)) ??
    months.find((m) => m.key === wantedDay?.slice(0, 7)) ??
    months[months.length - 1];
  const day = month.days.find((d) => d.date === wantedDay) ?? month.days[month.days.length - 1];
  const kind = one(params.scope);
  return { kind: kind === "day" || kind === "all" ? kind : "month", month: month.key, day: day.date };
}

/** The scope as the API's date/month parameters. */
export function scopePeriod(scope: Scope): Period {
  return scope.kind === "day" ? { date: scope.day } : scope.kind === "month" ? { month: scope.month } : {};
}

/** "7 October 2026", "October 2026" or "September 2026 – October 2026". */
export function scopeLabel(scope: Scope, months: Month[]) {
  if (scope.kind === "day") return fullDay(scope.day);
  if (scope.kind === "month") return monthName(scope.month);
  const first = monthName(months[0].key);
  const last = monthName(months[months.length - 1].key);
  return first === last ? first : `${first} – ${last}`;
}

function href(params: Record<string, string | undefined>, hash = "") {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value) query.set(key, value);
  }
  const text = query.toString();
  return `/${text ? `?${text}` : ""}${hash}`;
}

function scopeParams(scope: Scope) {
  return {
    month: scope.kind === "day" ? undefined : scope.month,
    scope: scope.kind === "month" ? undefined : scope.kind,
    day: scope.kind === "day" ? scope.day : undefined,
  };
}

export const STATES_ANCHOR = "by-state";

export function overviewHref(scope: Scope, toStates = false) {
  return href(scopeParams(scope), toStates ? `#${STATES_ANCHOR}` : "");
}

export function stateHref(state: string, scope: Scope, severity?: Severity) {
  return href({ state, ...scopeParams(scope), severity });
}

export function dayHref(date: string, severity?: Severity) {
  return href({ date, severity });
}

export function parseSeverity(value: string | string[] | undefined): Severity | undefined {
  return value === "fatal" || value === "non-fatal" ? value : undefined;
}

export { one as oneParam };
