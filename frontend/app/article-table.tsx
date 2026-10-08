"use client";

import { useState } from "react";

import type { Article, Severity, Totals } from "@/lib/api";
import { count, shortDay } from "@/lib/dates";
import { Seg, ghostButton, panel } from "./ui";

/** Rows shown before "Show all". */
const FIRST = 15;

const COLUMNS = "grid-cols-[minmax(0,3fr)_180px_150px_150px_minmax(0,1.5fr)]";

/** Google News titles end with " - Outlet"; the outlet has its own column. */
function headline(article: Article) {
  const suffix = ` - ${article.source}`;
  return article.source && article.title.endsWith(suffix) ? article.title.slice(0, -suffix.length) : article.title;
}

function SeverityPill({ article }: { article: Article }) {
  const fatal = article.severity === "fatal";
  const text = fatal
    ? article.deaths > 0
      ? `Fatal · ${article.deaths} dead`
      : "Fatal · toll unknown"
    : article.injured > 0
      ? `Non-fatal · ${article.injured} injured`
      : "Non-fatal";
  const tone = fatal
    ? "border-[oklch(0.5_0.17_25)] bg-[oklch(0.25_0.07_25)] text-[oklch(0.78_0.14_25)]"
    : "border-[oklch(0.6_0.12_78)] bg-[oklch(0.25_0.05_78)] text-[oklch(0.85_0.13_85)]";
  return <span className={`inline-block rounded-full border px-2.5 py-0.5 text-xs whitespace-nowrap ${tone}`}>{text}</span>;
}

/**
 * The article list for a day or a state, with the severity filter above it.
 * The filter is a set of links: the server sends the matching rows.
 */
export function ArticleTable({
  articles,
  totals,
  severity,
  hrefs,
  lastColumn,
}: {
  articles: Article[];
  /** Totals for the whole period, whatever the filter. */
  totals: Totals;
  severity?: Severity;
  /** Where each filter option leads. */
  hrefs: { all: string; fatal: string; nonFatal: string };
  /** A day's list shows each article's state; a state's list shows its date. */
  lastColumn: "state" | "date";
}) {
  const [showAll, setShowAll] = useState(false);

  const matching = severity === "fatal" ? totals.fatal : severity === "non-fatal" ? totals.non_fatal : totals.accidents;
  const visible = showAll ? articles : articles.slice(0, FIRST);

  return (
    <section className={`${panel} overflow-hidden`}>
      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2.5 border-b border-hair px-[18px] py-3.5">
        <h2 className="text-[15px] font-semibold">Articles</h2>
        <Seg
          label="Severity"
          items={[
            { label: `All ${count(totals.accidents)}`, href: hrefs.all, on: !severity },
            { label: `Fatal ${count(totals.fatal)}`, href: hrefs.fatal, on: severity === "fatal" },
            { label: `Non-fatal ${count(totals.non_fatal)}`, href: hrefs.nonFatal, on: severity === "non-fatal" },
          ]}
        />
      </div>
      <div className="overflow-x-auto">
        <div className="tbl-in min-w-[900px]">
          <div className={`tbl-head grid ${COLUMNS} gap-4 border-b border-line bg-raised px-[18px] py-3 text-[11.5px] uppercase tracking-[0.06em] text-muted`}>
            <span>Title</span>
            <span>Fatality</span>
            <span>Vehicle type</span>
            <span>{lastColumn === "state" ? "State" : "Date"}</span>
            <span>Article link</span>
          </div>
          {visible.map((article) => (
            <div key={article.id} className={`tbl-row grid ${COLUMNS} items-center gap-4 border-t border-[#1a1a1a] px-[18px] py-[13px] text-sm leading-[1.45]`}>
              <span className="text-pretty text-fg">{headline(article)}</span>
              <span>
                <SeverityPill article={article} />
              </span>
              <span className="text-soft">{article.vehicles.join(" / ") || "Unknown"}</span>
              <span className="text-soft">{lastColumn === "state" ? article.state || "Unknown" : shortDay(article.date)}</span>
              <a href={article.link} target="_blank" rel="noopener noreferrer" className="text-accent hover:underline">
                {article.source || "Read article"}
                <span aria-hidden="true">{" ↗"}</span>
              </a>
            </div>
          ))}
          {articles.length === 0 && <p className="px-[18px] py-8 text-center text-sm text-dim">No articles match this filter.</p>}
        </div>
      </div>
      <div className="flex flex-wrap items-center justify-between gap-2.5 border-t border-hair px-[18px] py-3">
        <span className="text-[12.5px] text-dim tabular-nums">
          Showing {count(visible.length)} of {count(matching)} articles
          {articles.length < matching && ` · only the newest ${count(articles.length)} are loaded`}
        </span>
        {articles.length > FIRST && (
          <button type="button" onClick={() => setShowAll(!showAll)} className={ghostButton}>
            {showAll ? `Show first ${FIRST}` : `Show all ${count(articles.length)}`}
          </button>
        )}
      </div>
    </section>
  );
}
