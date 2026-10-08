"use client"; // Error boundaries must be Client Components

import Link from "next/link";

import { Notice, linkClass } from "./ui";

/** Shown when the API can't be reached -- most often a cold start that timed out. */
export default function LoadError({ retry }: { error: Error & { digest?: string }; retry: () => void }) {
  return (
    <main className="mx-auto w-full max-w-[1200px] flex-1 px-[clamp(16px,5vw,56px)] pt-[clamp(20px,5vw,56px)] pb-14">
      <Notice title="Couldn’t load the data">
        The data server didn’t respond. It may still be waking up —{" "}
        <button type="button" onClick={() => retry()} className={`${linkClass} cursor-pointer`}>
          try again
        </button>
        , or go back to the{" "}
        <Link href="/" className={linkClass} prefetch={false}>
          overview
        </Link>
        .
      </Notice>
    </main>
  );
}
