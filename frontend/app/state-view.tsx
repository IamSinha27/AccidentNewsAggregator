import Link from "next/link";

import { type DailyStats, type Severity, fetchArticles, fetchVehicles } from "@/lib/api";
import { count, groupMonths } from "@/lib/dates";
import { type Scope, overviewHref, scopeLabel, scopePeriod, stateHref, vehicleHref } from "@/lib/urls";
import { ArticleTable } from "./article-table";
import { StatTiles, ghostButton, kicker, panel } from "./ui";
import { VehicleChart } from "./vehicle-chart";

/** One state's articles and totals, for the day, month or all-time period chosen on the map. */
export async function StateView({ daily, state, scope, severity }: { daily: DailyStats; state: string; scope: Scope; severity?: Severity }) {
  const span = scopeLabel(scope, groupMonths(daily.days));
  const [{ totals, articles }, vehicles] = await Promise.all([
    fetchArticles({ state, ...scopePeriod(scope), severity }),
    fetchVehicles({ state, ...scopePeriod(scope) }),
  ]);

  return (
    <>
      <div>
        <Link href={overviewHref(scope, true)} className={ghostButton}>
          ← Overview
        </Link>
      </div>

      <div className="flex flex-col gap-2">
        <span className={kicker}>State report</span>
        <h1 className="text-[clamp(24px,5vw,32px)] font-semibold tracking-[-0.02em]">{state}</h1>
        <p className="text-muted tabular-nums">
          {count(totals.accidents)} articles · {count(totals.fatal)} fatal · {count(totals.deaths)} deaths · {span}
        </p>
      </div>

      <section className={`${panel} overflow-hidden`}>
        <StatTiles totals={totals} countLabel="Articles" note={() => span} />
      </section>

      <VehicleChart stats={vehicles} scopeNote={span} hrefFor={(vehicle) => vehicleHref(vehicle, scope, state)} />

      <ArticleTable
        key={severity ?? "all"}
        articles={articles}
        totals={totals}
        severity={severity}
        hrefs={{ all: stateHref(state, scope), fatal: stateHref(state, scope, "fatal"), nonFatal: stateHref(state, scope, "non-fatal") }}
        lastColumn="date"
      />
    </>
  );
}
