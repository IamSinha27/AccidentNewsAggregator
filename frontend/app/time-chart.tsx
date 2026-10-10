"use client";

import Link from "next/link";
import { useState } from "react";

import type { Day } from "@/lib/api";
import { type Month, count, dayOfMonth, daysInMonth, monthName, monthShort, monthShortYear, shortDay } from "@/lib/dates";
import { type Scope, dayHref, overviewHref } from "@/lib/urls";
import { Stack, barHeight, kicker } from "./ui";

/** Months shown at once in the small chart. */
const WINDOW = 6;

/** Daily bars for the chosen month, and a month-by-month chart to pick it from. */
export function TimeChart({ months, scope }: { months: Month[]; scope: Scope }) {
  const index = Math.max(0, months.findIndex((m) => m.key === scope.month));
  const month = months[index];

  const [hover, setHover] = useState<Day | null>(null);
  const maxStart = Math.max(0, months.length - WINDOW);
  const [start, setStart] = useState(index >= maxStart ? maxStart : Math.max(0, index - WINDOW + 1));
  const visible = months.slice(start, start + WINDOW);

  const byDay = new Map(month.days.map((d) => [dayOfMonth(d.date), d]));
  const maxDay = Math.max(...month.days.map((d) => d.accidents));
  const maxMonth = Math.max(...visible.map((m) => m.totals.accidents));
  const calendar = Array.from({ length: daysInMonth(month.key) }, (_, i) => i + 1);

  const first = visible[0].key;
  const last = visible[visible.length - 1].key;
  const range =
    first === last
      ? monthShortYear(first)
      : first.slice(0, 4) === last.slice(0, 4)
        ? `${monthShort(first)} – ${monthShortYear(last)}`
        : `${monthShortYear(first)} – ${monthShortYear(last)}`;

  const navButton = "size-8 cursor-pointer rounded-[7px] border border-line text-lg leading-none text-fg disabled:cursor-default disabled:opacity-35 max-md:size-10";

  return (
    <div className="flex flex-wrap gap-y-2">
      <div className="flex max-w-full flex-[3_1_320px] flex-col gap-2.5 p-[18px]">
        <span className={kicker}>{monthName(month.key)} · daily</span>
        <div className="overflow-x-auto pb-1">
          <div className="flex min-w-[700px] flex-col gap-2.5">
            <div className="flex h-[188px] items-end gap-0.5">
              {calendar.map((k) => {
                const day = byDay.get(k);
                if (!day) return <span key={k} className="h-0.5 min-w-0 flex-1 bg-line" />;
                const label = `${shortDay(day.date)}: ${day.accidents} articles, ${day.fatal} fatal, ${day.deaths} deaths. Click to view articles`;
                const dimmed = scope.kind === "day" && scope.day !== day.date;
                return (
                  <div key={k} className="flex min-w-0 flex-1 flex-col items-stretch gap-[3px]">
                    <span className="text-center text-[10.5px] leading-[15px] text-soft tabular-nums">{day.accidents}</span>
                    <Link
                      href={dayHref(day.date)}
                      className="daybar block"
                      aria-label={label}
                      title={label}
                      style={{ opacity: dimmed ? 0.45 : 1 }}
                      onMouseEnter={() => setHover(day)}
                      onMouseLeave={() => setHover(null)}
                      onFocus={() => setHover(day)}
                      onBlur={() => setHover(null)}
                    >
                      <Stack day={day} height={barHeight(day.accidents, maxDay, 150)} />
                    </Link>
                  </div>
                );
              })}
            </div>
            <div className="flex gap-0.5 border-t border-line pt-2">
              {calendar.map((k) => (
                <span key={k} className="min-w-0 flex-1 text-center text-[10.5px] text-dim tabular-nums">
                  {k}
                </span>
              ))}
            </div>
          </div>
        </div>
        <div className="flex min-h-8 items-center gap-2 rounded-[7px] border border-dashed border-[#2a4a6b] bg-[#0d1620] px-2.5 py-1.5 text-[12.5px] text-[#7cb8ff] tabular-nums">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" className="shrink-0">
            <path d="M5 3l14 8-6 2-2 6z" />
          </svg>
          <span className="max-md:hidden">
            {hover
              ? `${shortDay(hover.date)} · ${hover.accidents} articles · ${hover.fatal} fatal · ${hover.deaths} deaths — click to open the list`
              : "Click any bar to open that day’s article list"}
          </span>
          <span className="md:hidden">Swipe to see all days · tap a bar to open its articles</span>
        </div>
      </div>

      <div className="flex max-w-full flex-[1_1_220px] flex-col gap-2.5 p-[18px]">
        <div className="flex items-center justify-between gap-2">
          <span className={kicker}>Months</span>
          <div className="flex items-center gap-1.5">
            <span className="text-xs text-dim tabular-nums">{range}</span>
            <button type="button" className={navButton} aria-label="Earlier months" disabled={start === 0} onClick={() => setStart(Math.max(0, start - WINDOW))}>
              ‹
            </button>
            <button type="button" className={navButton} aria-label="Later months" disabled={start >= maxStart} onClick={() => setStart(Math.min(maxStart, start + WINDOW))}>
              ›
            </button>
          </div>
        </div>
        <div className="flex h-[170px] items-end gap-2.5">
          {visible.map((m) => {
            const on = m.key === month.key;
            return (
              <Link
                key={m.key}
                href={overviewHref({ ...scope, month: m.key, day: m.days[m.days.length - 1].date })}
                scroll={false}
                aria-label={`${monthName(m.key)}: ${m.totals.accidents} accidents`}
                aria-current={on ? "true" : undefined}
                className="flex max-w-16 flex-1 flex-col items-stretch gap-1.5"
                style={{ opacity: on ? 1 : 0.4 }}
              >
                <span className="text-center text-[11px] text-muted tabular-nums">{count(m.totals.accidents)}</span>
                <Stack day={m.totals} height={barHeight(m.totals.accidents, maxMonth, 140)} />
              </Link>
            );
          })}
        </div>
        <div className="flex gap-2.5 border-t border-line pt-2">
          {visible.map((m) => (
            <span key={m.key} className={`max-w-16 flex-1 text-center text-xs ${m.key === month.key ? "text-fg" : "text-dim"}`}>
              {monthShort(m.key)}
            </span>
          ))}
        </div>
        <span className="text-xs text-dim">Tap a month to see its days</span>
        <span className="text-xs text-dim">Recording started {monthShortYear(months[0].key)}. Earlier months are not shown.</span>
      </div>
    </div>
  );
}
