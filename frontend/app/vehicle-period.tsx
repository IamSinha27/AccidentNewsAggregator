"use client";

import { useRouter } from "next/navigation";

import { monthName, shortDay } from "@/lib/dates";
import { type Scope, type ScopeKind, type Window, overviewHref } from "@/lib/urls";
import type { MonthOption } from "./state-map";
import { Seg } from "./ui";

const selectClass = "rounded-[7px] border border-[#333] bg-raised px-2.5 py-1.5 text-sm text-fg";

const KINDS: [ScopeKind, string][] = [
  ["day", "Day"],
  ["month", "Month"],
  ["all", "All time"],
];

/**
 * The vehicle chart's own period control. It changes only the chart's period
 * (?vscope=&vmonth=&vday=); the state map keeps whatever it was set to.
 */
export function VehiclePeriod({
  scope,
  window,
  months,
  days,
}: {
  /** The page's scope, so changing the vehicle period leaves the map's untouched. */
  scope: Scope;
  /** The vehicle chart's current period. */
  window: Window;
  months: MonthOption[];
  /** The days of the chart's month that have data. */
  days: string[];
}) {
  const router = useRouter();
  const go = (next: Window) => router.push(overviewHref({ ...scope, vehicles: next }), { scroll: false });
  const lastDayOf = (month: string) => months.find((m) => m.key === month)?.lastDay ?? window.day;

  return (
    <>
      <Seg
        label="Vehicle period"
        items={KINDS.map(([kind, label]) => ({
          label,
          href: overviewHref({ ...scope, vehicles: { ...window, kind } }),
          on: window.kind === kind,
        }))}
      />
      {window.kind !== "all" && (
        <label>
          <span className="sr-only">Vehicle chart month</span>
          <select
            className={selectClass}
            value={window.month}
            onChange={(event) => go({ kind: window.kind, month: event.target.value, day: lastDayOf(event.target.value) })}
          >
            {months.map((m) => (
              <option key={m.key} value={m.key}>
                {monthName(m.key)}
              </option>
            ))}
          </select>
        </label>
      )}
      {window.kind === "day" && (
        <label>
          <span className="sr-only">Vehicle chart day</span>
          <select className={selectClass} value={window.day} onChange={(event) => go({ ...window, day: event.target.value })}>
            {days.map((day) => (
              <option key={day} value={day}>
                {shortDay(day)}
              </option>
            ))}
          </select>
        </label>
      )}
    </>
  );
}
