"""
backfill_vehicles.py
One-off: fill `vehicles` for rows stored when the vehicles were one free-text
`vehicle_type` column, then drop that column.

    python backfill_vehicles.py [--dry-run]

Nothing is scraped. Each stored description ("SUV / Dumper", "Bus, Bolero")
is split into its individual vehicles, and the LLM is asked which one of the
fixed categories in extract.VEHICLE_TYPES each of those belongs to -- one
question per distinct vehicle name, not per row. Does nothing on a database
where the old column is already gone.
"""

import argparse
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor

import db
from extract import VEHICLE_TYPES, normalise_vehicles
from run_pipeline import DEFAULT_WORKERS

CATEGORY_PROMPT = """A news report of a road accident in India describes one of the vehicles involved as: "{part}"

Which ONE of these categories is it? {vehicle_types}

Guide: motorcycle/scooter/bike/moped -> "Two-wheeler"; any passenger car, SUV, MUV or jeep -> "Car"; lorry/dumper/tipper/tanker/trailer/container/goods carrier -> "Truck"; any van, pickup, tempo or ambulance -> "Van"; e-rickshaw -> "Auto-rickshaw"; tractor-trolley -> "Tractor"; any bus -> "Bus".

Answer with only the category name, exactly as written above. Answer None if it is not a road vehicle that fits one of them (a train, a pedestrian) or the description is too vague to tell (unknown, "vehicle", "four-wheeler").
"""


def split_description(description: str) -> list:
    """'Truck / Car, Two-wheeler' -> ['Truck', 'Car', 'Two-wheeler']."""
    return [part.strip() for part in re.split(r"/|,|\band\b", description) if part.strip()]


def categorise(client, part: str) -> list:
    """[] or a one-item list: the category this single vehicle belongs to."""
    resp = client.chat.completions.create(
        model="gpt-4o-mini", max_tokens=20,
        messages=[{"role": "user", "content": CATEGORY_PROMPT.format(
            part=part, vehicle_types=", ".join(f'"{name}"' for name in VEHICLE_TYPES),
        )}],
    )
    return normalise_vehicles([resp.choices[0].message.content.strip().strip('"')])


def main() -> int:
    parser = argparse.ArgumentParser(description="Convert the old vehicle_type text into the vehicles list.")
    parser.add_argument("--dry-run", action="store_true", help="print the mapping but write nothing")
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS)
    args = parser.parse_args()

    conn = db.connect()
    db.init_schema(conn)
    has_old_column = conn.execute(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_schema = current_schema() AND table_name = 'articles' AND column_name = 'vehicle_type'"
    ).fetchone()
    if not has_old_column:
        print("vehicle_type column is already gone; nothing to do")
        return 0

    descriptions = [row[0] for row in conn.execute(
        "SELECT vehicle_type FROM articles WHERE vehicle_type IS NOT NULL GROUP BY 1 ORDER BY count(*) DESC, 1"
    )]
    parts = sorted({part for d in descriptions for part in split_description(d)})
    category = {}
    if parts:
        from openai import OpenAI
        client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            category = dict(zip(parts, pool.map(lambda part: categorise(client, part), parts)))
        for part in parts:
            print(f"  {part!r:<42} -> {' / '.join(category[part]) or 'none'}")
        print()

    for description in descriptions:
        vehicles = sorted({name for part in split_description(description) for name in category[part]})
        print(f"{description!r:<45} -> {' / '.join(vehicles) or 'Unknown'}")
        conn.execute("UPDATE articles SET vehicles = %s WHERE vehicle_type = %s", (vehicles, description))
    conn.execute("ALTER TABLE articles DROP COLUMN vehicle_type")

    if args.dry_run:
        conn.rollback()
    else:
        conn.commit()
    conn.close()
    print(f"\n{len(descriptions)} descriptions converted" + (" (dry run, nothing written)" if args.dry_run else "; vehicle_type dropped"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
