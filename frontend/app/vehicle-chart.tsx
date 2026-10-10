import Link from "next/link";
import type { ReactNode } from "react";

import type { Totals, VehicleStats } from "@/lib/api";
import { count } from "@/lib/dates";
import { Legend, panel } from "./ui";

/** Widest a bar may be, as a share of the row, so its value label always fits beside it. */
const BAR_SHARE = 82;

function describe(name: string, totals: Totals) {
  return `${name}: ${count(totals.accidents)} accidents, ${count(totals.fatal)} fatal, ${count(totals.non_fatal)} non-fatal, ${count(totals.deaths)} ${totals.deaths === 1 ? "death" : "deaths"}`;
}

/**
 * Accidents per vehicle type, each bar split into fatal and non-fatal.
 * An accident with several vehicles is counted under each, so the bars add up
 * to more than the accident total; accidents that name no vehicle are listed apart.
 */
export function VehicleChart({
  stats,
  scopeNote,
  hrefFor,
  control,
}: {
  stats: VehicleStats;
  scopeNote: string;
  hrefFor: (vehicle: string) => string;
  /** A period control to show beside the note, when the page has one to share. */
  control?: ReactNode;
}) {
  const { vehicles, unknown } = stats;
  const max = Math.max(1, ...vehicles.map((v) => v.accidents));

  return (
    <section aria-labelledby="vehicles-h" className={panel}>
      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2.5 border-b border-hair px-[18px] py-4">
        <div className="flex flex-wrap items-baseline gap-x-3.5 gap-y-2">
          <h2 id="vehicles-h" className="text-[15px] font-semibold">
            By vehicle type
          </h2>
          <Legend />
        </div>
        <div className="flex flex-wrap items-center gap-2.5">
          {control}
          {scopeNote && <span className="text-[13px] text-muted">{scopeNote}</span>}
        </div>
      </div>

      <div className="flex flex-col gap-3 p-[18px]">
        {vehicles.length === 0 ? (
          <p className="text-sm text-muted">No accident here names a vehicle.</p>
        ) : (
          <ul className="flex flex-col gap-2.5">
            {vehicles.map((v) => (
              <li key={v.vehicle}>
                <Link
                  href={hrefFor(v.vehicle)}
                  className="grid grid-cols-[96px_1fr] items-center gap-3 rounded-md py-0.5 hover:bg-raised max-sm:grid-cols-[84px_1fr]"
                  title={`${describe(v.vehicle, v)}. Click to list the articles`}
                >
                  <span className="text-[13px] text-soft">{v.vehicle}</span>
                  <div className="flex items-center gap-2">
                    <span
                      className="flex h-5 min-w-1 gap-0.5 overflow-hidden rounded-r-sm"
                      style={{ width: `${(v.accidents / max) * BAR_SHARE}%` }}
                      aria-hidden="true"
                    >
                      {v.fatal > 0 && <span className="bg-fatal" style={{ flexGrow: v.fatal }} />}
                      {v.non_fatal > 0 && <span className="bg-nonfatal" style={{ flexGrow: v.non_fatal }} />}
                    </span>
                    <span className="text-xs text-muted tabular-nums">{count(v.accidents)}</span>
                  </div>
                </Link>
              </li>
            ))}
          </ul>
        )}

        {unknown.accidents > 0 && (
          <p className="border-t border-hair pt-3 text-xs text-dim tabular-nums">
            {count(unknown.accidents)} {unknown.accidents === 1 ? "accident doesn’t" : "accidents don’t"} name a vehicle ({count(unknown.fatal)} fatal,{" "}
            {count(unknown.non_fatal)} non-fatal).
          </p>
        )}
        <p className="text-xs text-dim">An accident involving several vehicles is counted under each of them. Click a bar to list its articles.</p>
      </div>

      <table className="sr-only">
        <caption>Accidents by vehicle type</caption>
        <thead>
          <tr>
            <th scope="col">Vehicle</th>
            <th scope="col">Accidents</th>
            <th scope="col">Fatal</th>
            <th scope="col">Non-fatal</th>
            <th scope="col">Deaths</th>
            <th scope="col">Injured</th>
          </tr>
        </thead>
        <tbody>
          {vehicles.map((v) => (
            <tr key={v.vehicle}>
              <th scope="row">{v.vehicle}</th>
              <td>{v.accidents}</td>
              <td>{v.fatal}</td>
              <td>{v.non_fatal}</td>
              <td>{v.deaths}</td>
              <td>{v.injured}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
