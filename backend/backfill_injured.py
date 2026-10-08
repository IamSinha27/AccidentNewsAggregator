"""
backfill_injured.py
One-off: fill `injured` for rows stored before that column existed.

    python backfill_injured.py [--dry-run] [--workers N]

The article body was never stored, and this doesn't scrape it again: the LLM
is given the stored headline only, so it finds a count only when the headline
states one ("3 killed, 5 hurt as bus overturns"). Only `injured` is written --
severity and deaths were extracted from the full article at the time and are
left alone. Rows that already have a count are skipped, so it is safe to rerun.
"""

import argparse
import sys
from concurrent.futures import ThreadPoolExecutor

import db
from extract import extract_fields
from run_pipeline import DEFAULT_WORKERS


def injured_from_title(title: str) -> int:
    fields = extract_fields(title)
    return fields["injured"] if fields else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Fill injured counts for existing articles from their headlines.")
    parser.add_argument("--dry-run", action="store_true", help="print what would change but write nothing")
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS)
    args = parser.parse_args()

    conn = db.connect()
    db.init_schema(conn)
    rows = conn.execute("SELECT id, title FROM articles WHERE injured = 0 ORDER BY id").fetchall()

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        counts = list(pool.map(injured_from_title, [title for _id, title in rows]))

    updated = 0
    for (row_id, title), injured in zip(rows, counts):
        if injured > 0:
            print(f"[{injured} injured] {title}", flush=True)
            conn.execute("UPDATE articles SET injured = %s WHERE id = %s", (injured, row_id))
            updated += 1

    if args.dry_run:
        conn.rollback()
    else:
        conn.commit()
    conn.close()
    print(f"\n{updated} of {len(rows)} rows given an injured count" + (" (dry run, nothing written)" if args.dry_run else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
