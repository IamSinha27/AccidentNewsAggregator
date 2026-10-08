import Link from "next/link";

import type { Totals } from "@/lib/api";
import { count } from "@/lib/dates";

export const panel = "rounded-[10px] border border-line bg-panel";
export const kicker = "text-[11px] uppercase tracking-[0.06em] text-dim";
export const ghostButton =
  "inline-flex min-h-9 cursor-pointer items-center whitespace-nowrap rounded-[7px] border border-line px-3 py-2 text-[13px] text-muted hover:text-fg";
export const segGroup = "flex flex-wrap gap-0.5 rounded-lg border border-line p-[3px]";

export function segItem(on: boolean) {
  return `inline-flex min-h-[30px] cursor-pointer items-center rounded-[5px] px-3 py-[5px] text-[13px] tabular-nums max-md:min-h-10 ${
    on ? "bg-line text-fg" : "text-muted hover:text-fg"
  }`;
}

/** Segmented control whose options are links. */
export function Seg({ label, items }: { label: string; items: { label: string; href: string; on: boolean }[] }) {
  return (
    <div className={segGroup} role="group" aria-label={label}>
      {items.map((item) => (
        <Link key={item.label} href={item.href} scroll={false} aria-current={item.on ? "true" : undefined} className={segItem(item.on)}>
          {item.label}
        </Link>
      ))}
    </div>
  );
}

export function Legend() {
  return (
    <div className="flex flex-wrap gap-3 text-xs text-muted">
      <span className="flex items-center gap-1.5">
        <span className="size-[9px] rounded-sm bg-fatal" />
        Fatal
      </span>
      <span className="flex items-center gap-1.5">
        <span className="size-[9px] rounded-sm bg-nonfatal" />
        Non-fatal
      </span>
    </div>
  );
}

/** A stacked bar: non-fatal on top of fatal. `height` is in pixels. */
export function Stack({ day, height }: { day: { fatal: number; non_fatal: number }; height: number }) {
  return (
    <span className="flex w-full flex-col overflow-hidden rounded-t-sm" style={{ height }}>
      <span className="bg-nonfatal" style={{ flexGrow: day.non_fatal }} />
      <span className="bg-fatal" style={{ flexGrow: day.fatal }} />
    </span>
  );
}

export function barHeight(value: number, max: number, tallest: number) {
  return Math.max(2, Math.round((value / Math.max(1, max)) * tallest));
}

/** "+12 vs yesterday (44)" */
export function change(now: number, before: number | undefined, versus: string) {
  if (before === undefined) return "No earlier day in the data";
  if (now === before) return `Same as ${versus}`;
  return `${now > before ? "+" : "−"}${count(Math.abs(now - before))} vs ${versus} (${count(before)})`;
}

/** "33 fatal · 23 non-fatal" */
export function breakdown(totals: Totals) {
  return `${count(totals.fatal)} fatal · ${count(totals.non_fatal)} non-fatal`;
}

/**
 * The three headline numbers. `note` writes the small line under each one:
 * a comparison with another day, or just the period covered.
 */
export function StatTiles({
  totals,
  countLabel,
  note,
}: {
  totals: Totals;
  countLabel: string;
  note: (pick: (t: Totals) => number) => string;
}) {
  const tiles = [
    { label: countLabel, value: totals.accidents, tone: "text-fg", pick: (t: Totals) => t.accidents, sub: breakdown(totals) },
    {
      label: "Fatalities",
      value: totals.deaths,
      tone: "text-fatal-text",
      pick: (t: Totals) => t.deaths,
      sub: `Deaths across ${count(totals.fatal)} fatal accidents`,
    },
    { label: "Injuries", value: totals.injured, tone: "text-nonfatal-text", pick: (t: Totals) => t.injured, sub: "People reported injured" },
  ];
  return (
    <div className="grid grid-cols-[repeat(auto-fit,minmax(200px,1fr))] gap-px bg-hair">
      {tiles.map((tile) => (
        <div key={tile.label} className="flex flex-col gap-1.5 bg-panel p-[18px]">
          <span className={kicker}>{tile.label}</span>
          <span className={`text-[40px] leading-none font-semibold tracking-[-0.02em] tabular-nums ${tile.tone}`}>{count(tile.value)}</span>
          <span className="text-[12.5px] text-muted tabular-nums">{note(tile.pick)}</span>
          <span className="text-xs text-dim">{tile.sub}</span>
        </div>
      ))}
    </div>
  );
}

export function Notice({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-[10px] border border-dashed border-line px-6 py-12 text-center">
      <p className="font-medium">{title}</p>
      <div className="mt-1 text-sm text-muted">{children}</div>
    </div>
  );
}

export const linkClass = "font-medium text-accent underline-offset-2 hover:underline";
