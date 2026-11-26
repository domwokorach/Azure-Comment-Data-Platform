"""Generate fake but realistic source-system extracts for the demo.

Three separate systems that do not talk to each other today:
  * CRM          -> customers.csv       (has duplicates and messy emails)
  * Permits      -> sites.csv, permits.csv
  * Inspections  -> inspections.json    (nested, semi-structured, some bad records)

All data is synthetic. Seeded so every run gives the same files.
"""
import csv
import json
import random
from datetime import date, timedelta
from pathlib import Path

random.seed(4706)
ROOT = Path(__file__).resolve().parents[1]
LANDING = ROOT / "data" / "landing"

FIRST = ["Amara", "Ben", "Chloe", "David", "Esi", "Femi", "Grace", "Hassan", "Isla", "James", "Kofi", "Lena"]
LAST = ["Okafor", "Smith", "Patel", "Jones", "Mensah", "Brown", "Khan", "Taylor", "Evans", "Owusu"]
TOWNS = ["Leeds", "Bristol", "York", "Exeter", "Norwich", "Carlisle", "Reading", "Lincoln"]
SITE_TYPES = ["Waste transfer", "Water discharge", "Landfill", "Industrial", "Farm"]
PERMIT_STATUS = ["Active", "Active", "Active", "Suspended", "Expired"]
FINDINGS = ["Odour", "Leak", "Paperwork", "Storage", "Noise", "Runoff"]
SEVERITY = ["low", "medium", "high"]


def rand_date(start: date, end: date) -> date:
    return start + timedelta(days=random.randint(0, (end - start).days))


def customers(n=200):
    rows = []
    for i in range(1, n + 1):
        f, l = random.choice(FIRST), random.choice(LAST)
        email = f"{f}.{l}{i}@example.org"
        if random.random() < 0.05:
            email = email.upper() + "  "          # messy formatting
        if random.random() < 0.03:
            email = "not-an-email"                 # invalid
        rows.append({"customer_id": f"C{i:05d}", "full_name": f"{f} {l}",
                     "email": email, "town": random.choice(TOWNS),
                     "created_date": rand_date(date(2015, 1, 1), date(2025, 12, 31)).isoformat(),
                     "updated_at": f"2026-0{random.randint(1, 9)}-1{random.randint(0, 9)}T10:00:00"})
    # duplicate records with a newer updated_at (CRM keeps history rows)
    for r in random.sample(rows, 10):
        d = dict(r)
        d["town"] = random.choice(TOWNS)
        d["updated_at"] = "2026-10-01T09:00:00"
        rows.append(d)
    return rows


def sites(n=300, n_customers=200):
    return [{"site_id": f"S{i:05d}", "operator_customer_id": f"C{random.randint(1, n_customers):05d}",
             "site_name": f"{random.choice(TOWNS)} {random.choice(SITE_TYPES)} {i}",
             "site_type": random.choice(SITE_TYPES),
             "latitude": round(random.uniform(50.2, 55.0), 5),
             "longitude": round(random.uniform(-4.5, 1.5), 5)} for i in range(1, n + 1)]


def permits(n=400, n_sites=300):
    rows = []
    for i in range(1, n + 1):
        start = rand_date(date(2018, 1, 1), date(2025, 6, 30))
        rows.append({"permit_id": f"P{i:06d}", "site_id": f"S{random.randint(1, n_sites):05d}",
                     "permit_type": random.choice(["Standard", "Bespoke", "Exemption"]),
                     "status": random.choice(PERMIT_STATUS),
                     "issued_date": start.isoformat(),
                     "expiry_date": (start + timedelta(days=365 * random.choice([3, 5, 10]))).isoformat(),
                     "annual_fee_gbp": random.choice([450, 1200, 2750, 5600])})
    return rows


def inspections(n=1500, n_sites=300):
    rows = []
    for i in range(1, n + 1):
        site = f"S{random.randint(1, n_sites):05d}"
        when = rand_date(date(2023, 1, 1), date(2026, 10, 31))
        rec = {"inspection_id": f"I{i:07d}", "site_ref": site, "inspected_on": when.isoformat(),
               "inspector": {"id": f"EMP{random.randint(100, 160)}", "team": random.choice(["North", "South", "East", "West"])},
               "outcome": random.choice(["Compliant", "Compliant", "Minor breach", "Major breach"]),
               "findings": [{"category": random.choice(FINDINGS), "severity": random.choice(SEVERITY)}
                            for _ in range(random.randint(0, 3))],
               "notes": random.choice(["", "Follow-up visit booked.", "Operator cooperative.", "Photos attached in case file."])}
        if random.random() < 0.02:
            rec["site_ref"] = None                                  # broken reference
        if random.random() < 0.01:
            rec["inspected_on"] = "2031-01-01"                      # future date: data entry error
        if random.random() < 0.01:
            rec["outcome"] = "??"                                   # invalid code
        rows.append(rec)
    return rows


def write_csv(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def main():
    write_csv(LANDING / "crm" / "customers.csv", customers())
    write_csv(LANDING / "permits" / "sites.csv", sites())
    write_csv(LANDING / "permits" / "permits.csv", permits())
    p = LANDING / "inspections" / "inspections.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(inspections(), indent=1), encoding="utf-8")
    print(f"Sample data written to {LANDING}")


if __name__ == "__main__":
    main()
