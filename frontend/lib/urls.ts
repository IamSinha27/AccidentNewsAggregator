// Every view lives in the URL, so it can be linked to and the back button works.
//
//   /                              overview, latest month
//   /?month=2026-09                overview for another month
//   /?scope=day&day=2026-10-07     overview with the state map narrowed to a day
//   /?scope=all                    overview with the state map over all time
//   /?date=2026-10-07              one day's articles
//   /?state=Goa&...                one state's articles, for the same month/day/all-time choice
//   /?vehicle=Truck&...            one vehicle type's articles; add &state=Goa to narrow it to a state

import type { Period, Severity } from "./api";
import { type Month, fullDay, monthName } from "./dates";

/** The vehicle types the API knows (backend extract.VEHICLE_TYPES). */
export const VEHICLES = ["Auto-rickshaw", "Bus", "Car", "Tractor", "Truck", "Two-wheeler", "Van"];

export type ScopeKind = "day" | "month" | "all";

/** A period: one day, one month or all time. */
export type Window = {
  kind: ScopeKind;
  /** The month shown in the charts; also the period when kind is "month". */
  month: string;
  /** The period when kind is "day"; otherwise the day that scope would open on. */
  day: string;
};

/** What the state map (and a state's article list) covers. */
export type Scope = Window & {
  /** The vehicle chart's own period (?vscope=&vmonth=&vday=). Absent: its default, the latest month. */
  vehicles?: Window;
};

type Params = Record<string, string | string[] | undefined>;

const one = (value: string | string[] | undefined) => (typeof value === "string" ? value : undefined);

/** A period from its three URL values, falling back to the latest month that has data. */
function resolveWindow(months: Month[], kind?: string, monthKey?: string, wantedDay?: string): Window {
  const month =
    months.find((m) => m.key === monthKey) ?? months.find((m) => m.key === wantedDay?.slice(0, 7)) ?? months[months.length - 1];
  const day = month.days.find((d) => d.date === wantedDay) ?? month.days[month.days.length - 1];
  return { kind: kind === "day" || kind === "all" ? kind : "month", month: month.key, day: day.date };
}

/** Reads the scope from the URL, falling back to the latest month that has data. */
export function resolveScope(months: Month[], params: Params): Scope {
  const window = resolveWindow(months, one(params.scope), one(params.month), one(params.day));
  if (params.vscope === undefined && params.vmonth === undefined && params.vday === undefined) return window;
  return { ...window, vehicles: resolveWindow(months, one(params.vscope), one(params.vmonth), one(params.vday)) };
}

/** The period the vehicle chart covers: its own, or the latest month when none is set. */
export function vehicleWindow(scope: Scope, months: Month[]): Window {
  return scope.vehicles ?? resolveWindow(months);
}

/** The scope as the API's date/month parameters. */
export function scopePeriod(scope: Window): Period {
  return scope.kind === "day" ? { date: scope.day } : scope.kind === "month" ? { month: scope.month } : {};
}

/** "7 October 2026", "October 2026" or "All time (September 2026 – October 2026)". */
export function scopeLabel(scope: Window, months: Month[]) {
  if (scope.kind === "day") return fullDay(scope.day);
  if (scope.kind === "month") return monthName(scope.month);
  const first = monthName(months[0].key);
  const last = monthName(months[months.length - 1].key);
  return `All time (${first === last ? first : `${first} – ${last}`})`;
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
  const v = scope.vehicles;
  return {
    month: scope.kind === "day" ? undefined : scope.month,
    scope: scope.kind === "month" ? undefined : scope.kind,
    day: scope.kind === "day" ? scope.day : undefined,
    vmonth: v?.kind === "month" ? v.month : undefined,
    vscope: v && v.kind !== "month" ? v.kind : undefined,
    vday: v?.kind === "day" ? v.day : undefined,
  };
}

export const STATES_ANCHOR = "by-state";

export function overviewHref(scope: Scope, toStates = false) {
  return href(scopeParams(scope), toStates ? `#${STATES_ANCHOR}` : "");
}

export function stateHref(state: string, scope: Scope, severity?: Severity) {
  return href({ state, ...scopeParams(scope), severity });
}

export function vehicleHref(vehicle: string, scope: Scope, state?: string, severity?: Severity) {
  return href({ vehicle, state, ...scopeParams(scope), severity });
}

export function dayHref(date: string, severity?: Severity) {
  return href({ date, severity });
}

export function parseSeverity(value: string | string[] | undefined): Severity | undefined {
  return value === "fatal" || value === "non-fatal" ? value : undefined;
}

export function parseVehicle(value: string | string[] | undefined): string | undefined {
  return VEHICLES.find((v) => v === value);
}

export { one as oneParam };
