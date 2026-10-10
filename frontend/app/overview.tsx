import Link from "next/link";

import { type DailyStats, type Totals, fetchStates, fetchVehicles } from "@/lib/api";
import { count, groupMonths, isNextDay, longDay, monthName } from "@/lib/dates";
import { type Scope, overviewHref, scopeLabel, scopePeriod, vehicleHref, vehicleWindow } from "@/lib/urls";
import { StateMap } from "./state-map";
import { TimeChart } from "./time-chart";
import { Legend, StatTiles, change, ghostButton, panel } from "./ui";
import { VehicleChart } from "./vehicle-chart";
import { VehiclePeriod } from "./vehicle-period";

/** The landing view: the latest day, accidents over time, the vehicle chart and the state map (each with its own period). */
export async function Overview({ daily, scope }: { daily: DailyStats; scope: Scope }) {
  const months = groupMonths(daily.days);
  const month = months.find((m) => m.key === scope.month)!;
  // The vehicle chart has a period of its own, set apart from the state map's.
  const vehicleScope = vehicleWindow(scope, months);
  const vehicleMonth = months.find((m) => m.key === vehicleScope.month)!;
  const [{ states, unknown }, vehicles] = await Promise.all([fetchStates(scopePeriod(scope)), fetchVehicles(scopePeriod(vehicleScope))]);

  const today = daily.days[daily.days.length - 1];
  const before = daily.days[daily.days.length - 2];
  const versus = before && isNextDay(before.date, today.date) ? "yesterday" : "previous day";

  return (
    <>
      <div className="flex flex-col gap-2.5">
        <h1 className="text-[clamp(24px,5vw,32px)] font-semibold tracking-[-0.02em]">Indian traffic accident news</h1>
        <p className="max-w-[640px] leading-[1.55] text-pretty text-muted">
          Road accidents reported by Indian news outlets, collected once a day. Details are extracted automatically from each article and may
          contain mistakes.
        </p>
      </div>

      <section aria-labelledby="today-h" className={`${panel} overflow-hidden`}>
        <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2.5 border-b border-hair px-[18px] py-3.5">
          <div className="flex flex-wrap items-center gap-2.5">
            <span className="flex items-center gap-1.5 rounded-md bg-hair px-[9px] py-1 text-[11px] uppercase tracking-[0.06em]">
              <span className="size-1.5 rounded-full bg-fatal" />
              Latest
            </span>
            <h2 id="today-h" className="text-[15px] font-semibold">
              {longDay(today.date)}
            </h2>
          </div>
          <div className="flex flex-wrap gap-2">
            <Link href={`/?date=${today.date}`} className={ghostButton}>
              See articles →
            </Link>
            <Link href={overviewHref({ ...scope, kind: "day", month: today.date.slice(0, 7), day: today.date }, true)} className={ghostButton}>
              See by state →
            </Link>
          </div>
        </div>
        <StatTiles totals={today} countLabel="Accidents" note={(pick: (t: Totals) => number) => change(pick(today), before && pick(before), versus)} />
      </section>

      <section className={panel}>
        <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2.5 border-b border-hair px-[18px] py-4">
          <div className="flex flex-wrap items-baseline gap-x-3.5 gap-y-2">
            <h2 className="text-[15px] font-semibold">Accidents over time</h2>
            <Legend />
          </div>
          <div className="text-[13px] text-muted tabular-nums">
            <span className="font-medium text-fg">{monthName(month.key)}</span> — {count(month.totals.accidents)} accidents ·{" "}
            {count(month.totals.fatal)} fatal · {count(month.totals.deaths)} deaths
          </div>
        </div>
        <TimeChart months={months} scope={scope} />
      </section>

      <VehicleChart
        stats={vehicles}
        scopeNote={scopeLabel(vehicleScope, months)}
        // Opened from here, the list keeps this chart's period, and "← Overview" brings both sections back as they were.
        hrefFor={(vehicle) => vehicleHref(vehicle, { ...scope, vehicles: vehicleScope })}
        control={
          <VehiclePeriod
            scope={scope}
            window={vehicleScope}
            months={months.map((m) => ({ key: m.key, lastDay: m.days[m.days.length - 1].date }))}
            days={vehicleMonth.days.map((d) => d.date)}
          />
        }
      />

      <StateMap
        states={states}
        unknown={unknown}
        scope={scope}
        scopeNote={scope.kind === "month" ? "" : scopeLabel(scope, months)}
        months={months.map((m) => ({ key: m.key, lastDay: m.days[m.days.length - 1].date }))}
        days={month.days.map((d) => d.date)}
      />
    </>
  );
}
