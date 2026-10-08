// Server-side client for the FastAPI backend (backend/api.py).

/** The five numbers the API reports for any day, month, state or list. */
export type Totals = {
  accidents: number;
  fatal: number;
  non_fatal: number;
  /** A lower bound: fatal articles that state no toll add 0. */
  deaths: number;
  /** A lower bound: articles that state no number add 0. */
  injured: number;
};

export type Day = Totals & { date: string };

export type DailyStats = {
  /** Null only when the database is empty. */
  first_date: string | null;
  latest_date: string | null;
  /** One entry per day that has data, oldest first. */
  days: Day[];
};

export type StateTotals = Totals & { state: string };

export type StateStats = {
  /** States with at least one accident, most accidents first. */
  states: StateTotals[];
  /** Accidents whose state could not be determined. */
  unknown: Totals;
};

export type Severity = "fatal" | "non-fatal";

export type Article = {
  id: number;
  date: string;
  title: string;
  severity: Severity;
  /** 0 on a fatal article means the toll wasn't stated. */
  deaths: number;
  /** 0 means nobody was hurt or no number was stated. */
  injured: number;
  /** Vehicle types involved, alphabetical; empty when none is known. */
  vehicles: string[];
  state: string | null;
  link: string;
  source: string | null;
};

export type ArticlesResponse = {
  /** Totals for the whole day/month/state asked for, whatever the severity filter. */
  totals: Totals;
  articles: Article[];
};

/** A day, a month, or (with neither) all time. */
export type Period = { date?: string; month?: string };

const API_URL = (process.env.API_URL ?? "http://localhost:8000").replace(/\/$/, "");

// Render's free web tier sleeps when idle and can take about a minute to
// wake, so the first request of the day needs a generous timeout.
const TIMEOUT_MS = 90_000;

/** The most the API returns in one list. */
export const ARTICLE_LIMIT = 500;

async function get<T>(path: string, params: Record<string, string | undefined> = {}): Promise<T> {
  const url = new URL(`${API_URL}${path}`);
  for (const [key, value] of Object.entries(params)) {
    if (value) url.searchParams.set(key, value);
  }
  const response = await fetch(url, { cache: "no-store", signal: AbortSignal.timeout(TIMEOUT_MS) });
  if (!response.ok) throw new Error(`API responded ${response.status}`);
  return response.json();
}

/** Totals for every day that has data. */
export function fetchDaily(): Promise<DailyStats> {
  return get("/stats/daily");
}

/** Totals per state for a day, a month or all time. */
export function fetchStates(period: Period): Promise<StateStats> {
  return get("/stats/states", period);
}

/** Articles for a day, a month and/or a state, newest first. */
export function fetchArticles(filter: Period & { state?: string; severity?: Severity }): Promise<ArticlesResponse> {
  return get("/articles", { ...filter, limit: String(ARTICLE_LIMIT) });
}
