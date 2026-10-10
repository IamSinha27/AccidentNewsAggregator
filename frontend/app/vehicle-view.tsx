import Link from "next/link";

import { type DailyStats, type Severity, fetchArticles } from "@/lib/api";
import { count, groupMonths } from "@/lib/dates";
import { type Scope, overviewHref, scopeLabel, scopePeriod, stateHref, vehicleHref, vehicleWindow } from "@/lib/urls";
import { ArticleTable } from "./article-table";
import { StatTiles, ghostButton, kicker, panel } from "./ui";

/**
 * One vehicle type's articles and totals for the chosen period, for every state
 * or (when `state` is given) for just that one. An accident with several
 * vehicles is listed under each of them.
 */
export async function VehicleView({
  daily,
  vehicle,
  state,
  scope,
  severity,
}: {
  daily: DailyStats;
  vehicle: string;
  state?: string;
  scope: Scope;
  severity?: Severity;
}) {
  const months = groupMonths(daily.days);
  // From the overview the list covers the vehicle chart's period; from a state page, that state's.
  const window = state ? scope : vehicleWindow(scope, months);
  const span = scopeLabel(window, months);
  const { totals, articles } = await fetchArticles({ vehicle, state, ...scopePeriod(window), severity });

  return (
    <>
      <div>
        <Link href={state ? stateHref(state, scope) : overviewHref(scope)} className={ghostButton}>
          ← {state ?? "Overview"}
        </Link>
      </div>

      <div className="flex flex-col gap-2">
        <span className={kicker}>Vehicle report</span>
        <h1 className="text-[clamp(24px,5vw,32px)] font-semibold tracking-[-0.02em]">{state ? `${vehicle} · ${state}` : vehicle}</h1>
        <p className="text-muted tabular-nums">
          {count(totals.accidents)} articles · {count(totals.fatal)} fatal · {count(totals.deaths)} {totals.deaths === 1 ? "death" : "deaths"} · {span}
        </p>
      </div>

      <section className={`${panel} overflow-hidden`}>
        <StatTiles totals={totals} countLabel="Articles" note={() => span} />
      </section>

      <ArticleTable
        key={severity ?? "all"}
        articles={articles}
        totals={totals}
        severity={severity}
        hrefs={{
          all: vehicleHref(vehicle, scope, state),
          fatal: vehicleHref(vehicle, scope, state, "fatal"),
          nonFatal: vehicleHref(vehicle, scope, state, "non-fatal"),
        }}
        lastColumn={state ? "date" : "state"}
      />
      <p className="text-xs text-dim">An accident involving several vehicles is listed under each of them.</p>
    </>
  );
}
