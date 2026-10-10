import Link from "next/link";
import { Suspense } from "react";

import { fetchDaily } from "@/lib/api";
import { groupMonths, parseDay } from "@/lib/dates";
import { MAP_CENTROIDS } from "@/lib/india-map";
import { oneParam, parseSeverity, parseVehicle, resolveScope } from "@/lib/urls";
import { DayView } from "./day-view";
import { Overview } from "./overview";
import { StateView } from "./state-view";
import { VehicleView } from "./vehicle-view";
import { Notice, linkClass, panel } from "./ui";

type Params = Record<string, string | string[] | undefined>;

/** Picks the view from the URL (see lib/urls.ts). A failed load ends up in error.tsx. */
async function View({ params }: { params: Params }) {
  const date = parseDay(params.date);
  const state = oneParam(params.state);
  const vehicle = parseVehicle(params.vehicle);
  const severity = parseSeverity(params.severity);
  const daily = await fetchDaily();
  if (daily.days.length === 0) {
    return <Notice title="No articles yet">The daily collection hasn’t stored anything so far.</Notice>;
  }
  if (date) return <DayView daily={daily} date={date} severity={severity} />;
  const scope = resolveScope(groupMonths(daily.days), params);
  if (state && !(state in MAP_CENTROIDS) && state !== "Unknown") {
    return (
      <Notice title={`“${state}” isn’t a state or union territory we track`}>
        Go back to the{" "}
        <Link href="/" className={linkClass}>
          overview
        </Link>{" "}
        and pick one from the map.
      </Notice>
    );
  }
  if (oneParam(params.vehicle) && !vehicle) {
    return (
      <Notice title={`“${oneParam(params.vehicle)}” isn’t a vehicle type we track`}>
        Go back to the{" "}
        <Link href="/" className={linkClass}>
          overview
        </Link>{" "}
        and pick one from the vehicle chart.
      </Notice>
    );
  }
  if (vehicle) return <VehicleView daily={daily} vehicle={vehicle} state={state} scope={scope} severity={severity} />;
  if (state) return <StateView daily={daily} state={state} scope={scope} severity={severity} />;
  return <Overview daily={daily} scope={scope} />;
}

/** Shown while the API is answering -- which can take a while on a cold start. */
function Loading() {
  return (
    <div role="status" className="flex flex-col gap-6">
      <span className="sr-only">Loading</span>
      {[94, 260, 420].map((height) => (
        <div key={height} className={`${panel} animate-pulse`} style={{ height }} />
      ))}
      <p className="text-sm text-muted">The server sleeps when idle, so the first load of the day can take up to a minute.</p>
    </div>
  );
}

export default async function Home(props: PageProps<"/">) {
  const params = await props.searchParams;
  // Keyed by view only: moving between days or periods keeps the current
  // page on screen until the next one is ready, instead of flashing a skeleton.
  const view = parseDay(params.date) ? "day" : oneParam(params.vehicle) ? "vehicle" : oneParam(params.state) ? "state" : "overview";

  return (
    <main className="mx-auto flex w-full max-w-[1200px] flex-1 flex-col gap-6 px-[clamp(16px,5vw,56px)] pt-[clamp(20px,5vw,56px)] pb-14">
      <Suspense key={view} fallback={<Loading />}>
        <View params={params} />
      </Suspense>
    </main>
  );
}
