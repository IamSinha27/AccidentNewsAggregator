"""
demo_run.py
Validates extraction logic against real article text (pulled via web search,
standing in for what live RSS entries would contain: title + snippet).
"""

import csv
from extract import extract_fields

SAMPLE_ARTICLES = [
    {
        "title": "Trailer truck runs over five members of family in Jaipur",
        "snippet": "In Jaipur, a trailer truck ran over five members of the family. "
                   "Four family members died in the accident, while one person was "
                   "injured and has been admitted to the hospital.",
        "link": "https://www.indiatvnews.com/topic/road-accident-1",
    },
    {
        "title": "8 killed, 24 injured after Haridwar-Indore bus catches fire on Delhi-Mumbai Expressway",
        "snippet": "At least eight people were killed and 24 others injured after a "
                   "Haridwar-Indore bus caught fire following a collision with a truck "
                   "on the Delhi-Mumbai Expressway in Rajasthan's Dausa district.",
        "link": "https://www.indiatvnews.com/topic/road-accident-2",
    },
    {
        "title": "Sleeper bus collides with Ertiga car near Chityal",
        "snippet": "The bus, coming from Visakhapatnam to Hyderabad, hit the car from "
                   "the back near Chityal in the district around 5 am.",
        "link": "https://www.indiatvnews.com/topic/road-accident-3",
    },
    {
        "title": "E-rickshaw driver hurt avoiding tractor collision in Badaun",
        "snippet": "The e-rickshaw driver was attempting to avoid one tractor when the "
                   "collision with another tractor took place on the Bareilly-Mathura "
                   "road in Uttar Pradesh's Badaun district.",
        "link": "https://www.indiatvnews.com/topic/road-accident-4",
    },
    {
        "title": "Luxury bus rams into truck near Jarod on Banswara-Surat highway",
        "snippet": "A luxury bus travelling from Banswara in Rajasthan to Surat rammed "
                   "into a truck ahead of it near Kotambi village on the highway close "
                   "to Jarod. Most passengers were reportedly asleep at the time.",
        "link": "https://www.indiatvnews.com/topic/road-accident-5",
    },
    {
        "title": "20 killed as bus falls into gorge in Uttarakhand",
        "snippet": "At least 20 people were killed in the northern Indian state of "
                   "Uttarakhand when the bus they were traveling in fell into a "
                   "500-foot-deep gorge.",
        "link": "https://www.nbcnews.com/sample-1",
    },
    {
        "title": "16 killed in India road collision in West Bengal",
        "snippet": "All occupants of two jeeps returning from a wedding killed in West "
                   "Bengal state after colliding with truck.",
        "link": "https://www.aljazeera.com/sample-2",
    },
]

rows = []
for art in SAMPLE_ARTICLES:
    fields = extract_fields(art["title"], art["snippet"], use_llm_fallback=False)
    rows.append({
        "title": art["title"],
        "fatality": fields["fatality"],
        "vehicle_type": fields["vehicle_type"],
        "state": fields["state"],
        "link": art["link"],
        "rule_confident": fields["confident"],
    })

# Print as a readable table
col_widths = {"title": 45, "fatality": 16, "vehicle_type": 20, "state": 16, "rule_confident": 8}
header = f"{'Title':<45} {'Fatality':<16} {'Vehicle':<20} {'State':<16} {'Confident':<8}"
print(header)
print("-" * len(header))
for r in rows:
    t = (r["title"][:42] + "...") if len(r["title"]) > 45 else r["title"]
    print(f"{t:<45} {r['fatality']:<16} {r['vehicle_type']:<20} {r['state']:<16} {str(r['rule_confident']):<8}")

with open("demo_output.csv", "w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=["title", "fatality", "vehicle_type", "state", "link", "rule_confident"])
    writer.writeheader()
    writer.writerows(rows)

print("\nSaved to demo_output.csv")
