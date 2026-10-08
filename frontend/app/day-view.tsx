import Link from "next/link";

import { type DailyStats, type Severity, type Totals, fetchArticles } from "@/lib/api";
import { count, dayOfMonth, daysInMonth, groupMonths, longDay, monthShort, shortDay } from "@/lib/dates";
import { dayHref, overviewHref } from "@/lib/urls";
import { ArticleTable } from "./article-table";
import { Notice, Seg, Stack, StatTiles, barHeight, change, ghostButton, kicker, linkClass, panel } from "./ui";

const navLink = `${ghostButton} text-fg`;
const navOff = `${ghostButton} cursor-default opacity-35 hover:text-muted`;

/** One day's report: its totals, a strip to jump to another day, and its articles. */
export async function DayView({ daily, date, severity }: { daily: DailyStats; date: string; severity?: Severity }) {
  const index = daily.days.findIndex((d) => d.date === date);
  const latest = daily.days[daily.days.length - 1].date;
  if (index < 0) {
    return (
      <Notice title={`No articles for ${longDay(date)}`}>
        The most recent day with articles is{" "}
        <Link href={dayHref(latest)} className={linkClass}>
          {longDay(latest)}
        </Link>
        . Or go back to the{" "}
        <Link href="/" className={linkClass}>
          overview
        </Link>
        .
      </Notice>
    );
  }

  const day = daily.days[index];
  const before = daily.days[index - 1];
  const after = daily.days[index + 1];
  const months = groupMonths(daily.days);
  const month = months.find((m) => m.key === date.slice(0, 7))!;
  const scope = { month: month.key, day: date };
  const { totals, articles } = await fetchArticles({ date, severity });

  const byDay = new Map(month.days.map((d) => [dayOfMonth(d.date), d]));
  const maxDay = Math.max(...month.days.map((d) => d.accidents));
  const calendar = Array.from({ length: daysInMonth(month.key) }, (_, i) => i + 1);

  return (
    <>
      <div>
        <Link href={overviewHref({ ...scope, kind: "month" })} className={ghostButton}>
          ← Overview
        </Link>
      </div>

      <div className="flex flex-wrap items-end justify-between gap-x-6 gap-y-4">
        <div className="flex flex-[1_1_320px] flex-col gap-2">
          <span className={kicker}>Daily report</span>
          <h1 className="text-[clamp(24px,5vw,32px)] font-semibold tracking-[-0.02em]">{longDay(date)}</h1>
          <p className="text-muted tabular-nums">
            {count(day.accidents)} articles · {count(day.fatal)} fatal · {count(day.deaths)} deaths
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {before ? (
            <Link href={dayHref(before.date)} className={navLink}>
              ← {shortDay(before.date)}
            </Link>
          ) : (
            <span className={navOff}>← Earlier</span>
          )}
          {after ? (
            <Link href={dayHref(after.date)} className={navLink}>
              {shortDay(after.date)} →
            </Link>
          ) : (
            <span className={navOff}>Later →</span>
          )}
          <Link href={overviewHref({ ...scope, kind: "day" }, true)} className={ghostButton}>
            See by state →
          </Link>
        </div>
      </div>

      <section className={`${panel} overflow-hidden`}>
        <StatTiles totals={day} countLabel="Articles" note={(pick: (t: Totals) => number) => change(pick(day), before && pick(before), "previous day")} />
      </section>

      <section className={panel}>
        <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2.5 border-b border-hair px-[18px] py-3.5">
          <h2 className="text-[15px] font-semibold">Jump to another day</h2>
          <Seg
            label="Month"
            items={months.slice(-6).map((m) => ({ label: monthShort(m.key), href: dayHref(m.days[m.days.length - 1].date), on: m.key === month.key }))}
          />
        </div>
        <div className="overflow-x-auto p-[18px]">
          <div className="flex min-w-[700px] flex-col gap-2.5">
            <div className="flex h-[90px] items-end gap-0.5">
              {calendar.map((k) => {
                const d = byDay.get(k);
                if (!d) return <span key={k} className="h-0.5 min-w-0 flex-1 bg-line" />;
                const on = d.date === date;
                const label = `${shortDay(d.date)}: ${d.accidents} articles. Click to view`;
                return (
                  <Link
                    key={k}
                    href={dayHref(d.date)}
                    scroll={false}
                    aria-label={label}
                    title={label}
                    aria-current={on ? "true" : undefined}
                    className="daybar block min-w-0 flex-1"
                    style={{ opacity: on ? 1 : 0.4 }}
                  >
                    <Stack day={d} height={barHeight(d.accidents, maxDay, 90)} />
                  </Link>
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
      </section>

      <ArticleTable
        key={severity ?? "all"}
        articles={articles}
        totals={totals}
        severity={severity}
        hrefs={{ all: dayHref(date), fatal: dayHref(date, "fatal"), nonFatal: dayHref(date, "non-fatal") }}
        lastColumn="state"
      />
    </>
  );
}
