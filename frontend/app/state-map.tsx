"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import type { StateTotals, Totals } from "@/lib/api";
import { count, monthName, shortDay } from "@/lib/dates";
import { MAP_CENTROIDS, MAP_PATHS, MAP_VIEW_BOX } from "@/lib/india-map";
import { type Scope, type ScopeKind, STATES_ANCHOR, overviewHref, stateHref } from "@/lib/urls";
import { Seg, breakdown, ghostButton, kicker, panel, segGroup, segItem } from "./ui";

type Metric = "accidents" | "deaths";

/** A month the map can be switched to, and the day a "Day" scope opens on there. */
export type MonthOption = { key: string; lastDay: string };

const selectClass = "rounded-[7px] border border-[#333] bg-raised px-2.5 py-1.5 text-sm text-fg";

/** Accidents or deaths per state: bubbles on a map of India, and a ranking. */
export function StateMap({
  states,
  unknown,
  scope,
  scopeNote,
  months,
  days,
}: {
  states: StateTotals[];
  unknown: Totals;
  scope: Scope;
  /** The period in words, shown next to the controls. */
  scopeNote: string;
  months: MonthOption[];
  /** The days of the chosen month that have data. */
  days: string[];
}) {
  const router = useRouter();
  const [metric, setMetric] = useState<Metric>("accidents");
  const [selected, setSelected] = useState<string | null>(null);
  const [showAll, setShowAll] = useState(false);

  const byAccidents = metric === "accidents";
  const value = (row: StateTotals) => row[metric];
  const rows = states.filter((row) => value(row) > 0).sort((a, b) => value(b) - value(a) || a.state.localeCompare(b.state));
  const max = rows.length ? value(rows[0]) : 1;
  const current = rows.find((row) => row.state === selected) ?? rows[0];
  const shown = showAll ? rows : rows.slice(0, 10);

  const size = (v: number) => Math.round(8 + 46 * Math.sqrt(v / max));
  const fill = byAccidents ? "rgba(59, 158, 255, 0.32)" : "oklch(0.64 0.2 25 / 0.38)";
  const stroke = byAccidents ? "#3b9eff" : "oklch(0.64 0.2 25)";
  const legend = [...new Set([max, Math.max(1, Math.round(max / 4)), Math.max(1, Math.round(max / 16))])];

  const go = (next: Scope) => router.push(overviewHref(next), { scroll: false });
  const lastDayOf = (month: string) => months.find((m) => m.key === month)?.lastDay ?? scope.day;
  const scopeItems: [ScopeKind, string][] = [
    ["day", "Day"],
    ["month", "Month"],
    ["all", "All time"],
  ];
  const period = scope.kind === "all" ? "all time" : scope.kind === "day" ? shortDay(scope.day) : monthName(scope.month);

  return (
    <section id={STATES_ANCHOR} className={`${panel} scroll-mt-4`}>
      <div className="flex flex-col gap-3 border-b border-hair px-[18px] py-4">
        <div className="flex flex-wrap items-center justify-between gap-2.5">
          <h2 className="text-[15px] font-semibold">{byAccidents ? "Accidents" : "Deaths"} by state / UT</h2>
          <div className={segGroup} role="group" aria-label="Metric">
            {(["accidents", "deaths"] as const).map((m) => (
              <button key={m} type="button" aria-pressed={metric === m} onClick={() => setMetric(m)} className={segItem(metric === m)}>
                {m === "accidents" ? "Accidents" : "Deaths"}
              </button>
            ))}
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2.5">
          <Seg label="Period" items={scopeItems.map(([kind, label]) => ({ label, href: overviewHref({ ...scope, kind }), on: scope.kind === kind }))} />
          {scope.kind !== "all" && (
            <label>
              <span className="sr-only">Month</span>
              <select
                className={selectClass}
                value={scope.month}
                onChange={(event) => go({ ...scope, month: event.target.value, day: lastDayOf(event.target.value) })}
              >
                {months.map((m) => (
                  <option key={m.key} value={m.key}>
                    {monthName(m.key)}
                  </option>
                ))}
              </select>
            </label>
          )}
          {scope.kind === "day" && (
            <label>
              <span className="sr-only">Day</span>
              <select className={selectClass} value={scope.day} onChange={(event) => go({ ...scope, day: event.target.value })}>
                {days.map((day) => (
                  <option key={day} value={day}>
                    {shortDay(day)}
                  </option>
                ))}
              </select>
            </label>
          )}
          <span className="text-[13px] text-dim">{scopeNote}</span>
        </div>
      </div>

      <div className="flex flex-wrap items-start gap-6 p-[18px]">
        <div className="flex min-w-0 flex-[3_1_360px] flex-col gap-3">
          <div className="relative mx-auto aspect-[1000/1116] w-full max-w-[600px]">
            <svg viewBox={MAP_VIEW_BOX} role="img" aria-label="Map of India by state" className="absolute inset-0 block size-full">
              <g fill="#161616" stroke="#363636" strokeWidth="1.2" strokeLinejoin="round">
                {MAP_PATHS.map((path) => (
                  <path key={path.name} d={path.d}>
                    <title>{path.name}</title>
                  </path>
                ))}
              </g>
            </svg>
            {rows
              .filter((row) => MAP_CENTROIDS[row.state])
              .map((row) => {
                const on = row.state === current?.state;
                const label = `${row.state}: ${row.accidents} accidents, ${row.deaths} deaths`;
                return (
                  <button
                    key={row.state}
                    type="button"
                    onClick={() => setSelected(row.state)}
                    aria-label={label}
                    title={label}
                    aria-pressed={on}
                    className="absolute -translate-x-1/2 -translate-y-1/2 cursor-pointer rounded-full"
                    style={{
                      left: `${MAP_CENTROIDS[row.state][0]}%`,
                      top: `${MAP_CENTROIDS[row.state][1]}%`,
                      width: size(value(row)),
                      height: size(value(row)),
                      background: fill,
                      border: on ? "2px solid #ededed" : `1.5px solid ${stroke}`,
                    }}
                  />
                );
              })}
          </div>
          <div className="flex flex-wrap items-end justify-center gap-[18px] text-xs text-dim">
            <span className="self-center">Circle size = {metric}</span>
            {rows.length > 0 &&
              legend.map((v) => (
                <span key={v} className="flex flex-col items-center gap-1 tabular-nums">
                  <span className="rounded-full" style={{ width: size(v), height: size(v), background: fill, border: `1.5px solid ${stroke}` }} />
                  {count(v)}
                </span>
              ))}
          </div>
        </div>

        <div className="flex min-w-0 flex-[2_1_260px] flex-col gap-3.5">
          {current && (
            <Link
              href={stateHref(current.state, scope)}
              aria-label={`Open all articles for ${current.state}`}
              className="flex w-full flex-col gap-2 rounded-lg border border-line bg-[#121212] p-3.5 hover:border-accent"
            >
              <span className="flex w-full items-baseline justify-between gap-2">
                <span className="text-[15px] font-semibold">{current.state}</span>
                <span className="text-xs text-dim tabular-nums">
                  #{rows.indexOf(current) + 1} of {rows.length}
                </span>
              </span>
              <span className="flex flex-wrap gap-5 tabular-nums">
                <Figure value={count(current.accidents)} label="accidents" />
                <Figure value={count(current.deaths)} label="deaths" tone="text-fatal-text" />
                <Figure value={`${Math.round((current.fatal / Math.max(1, current.accidents)) * 100)}%`} label="fatal" />
              </span>
              <span className="flex h-2 w-full overflow-hidden rounded-sm bg-[#1a1a1a]">
                <span className="bg-fatal" style={{ flexGrow: current.fatal }} />
                <span className="bg-nonfatal" style={{ flexGrow: current.non_fatal }} />
              </span>
              <span className="text-xs text-dim tabular-nums">{breakdown(current)}</span>
              <span className="mt-1 w-full border-t border-hair pt-2.5 text-[13px] text-[#7cb8ff]">
                View all {count(current.accidents)} articles · {period} →
              </span>
            </Link>
          )}
          <div className="flex flex-col gap-0.5">
            <span className={`${kicker} pb-1.5`}>Ranking</span>
            {shown.map((row, i) => {
              const on = row.state === current?.state;
              return (
                <button
                  key={row.state}
                  type="button"
                  onClick={() => setSelected(row.state)}
                  aria-pressed={on}
                  className={`grid min-h-8 cursor-pointer grid-cols-[22px_minmax(0,1fr)_44px] items-center gap-2 rounded-md px-2 py-1 text-left text-[13px] text-soft max-md:min-h-11 ${on ? "bg-hair" : ""}`}
                >
                  <span className="text-[11.5px] text-dim tabular-nums">{i + 1}</span>
                  <span className="flex min-w-0 flex-col gap-[3px]">
                    <span className="truncate">{row.state}</span>
                    <span className="h-[3px] rounded-sm" style={{ width: `${(value(row) / max) * 100}%`, background: stroke }} />
                  </span>
                  <span className="text-right font-medium text-fg tabular-nums">{count(value(row))}</span>
                </button>
              );
            })}
            {rows.length === 0 && <p className="my-2 text-[13px] text-dim">No {metric} with a known state for this period.</p>}
            {rows.length > 10 && (
              <button type="button" onClick={() => setShowAll(!showAll)} className={`${ghostButton} mt-2 self-start`}>
                {showAll ? "Show top 10" : `Show all ${rows.length} states & UTs`}
              </button>
            )}
          </div>
          {unknown.accidents > 0 && (
            <p className="text-xs text-dim">
              {count(unknown.accidents)} {unknown.accidents === 1 ? "accident" : "accidents"} with no known state{" "}
              {unknown.accidents === 1 ? "is" : "are"} not shown here.
            </p>
          )}
        </div>
      </div>
    </section>
  );
}

function Figure({ value, label, tone = "" }: { value: string; label: string; tone?: string }) {
  return (
    <span className="flex flex-col gap-0.5">
      <span className={`text-[26px] leading-none font-semibold ${tone}`}>{value}</span>
      <span className="text-xs text-dim">{label}</span>
    </span>
  );
}
