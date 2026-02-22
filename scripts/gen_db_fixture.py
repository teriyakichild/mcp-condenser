#!/usr/bin/env python3
"""Generate a synthetic SQL query result set fixture for testing TOON compression.

Produces 50 order rows with 17 columns, designed to exercise various compression
heuristics (constant columns, mostly-zero columns, clustered timestamps, etc.).

Output: tests/fixtures/db_query_results.json
"""

import json
import random
from datetime import datetime, timedelta
from pathlib import Path

SEED = 42
NUM_ROWS = 150

# Column distributions
STATUSES = ["shipped", "delivered", "pending", "cancelled", "processing"]
STATUS_WEIGHTS = [30, 25, 20, 10, 15]  # percentage-ish weights

REGIONS = ["northeast", "southeast", "midwest", "west", "southwest"]
REGION_WEIGHTS = [25, 20, 20, 20, 15]

PAYMENT_METHODS = ["credit_card", "debit_card", "paypal", "bank_transfer"]
PAYMENT_WEIGHTS = [45, 25, 20, 10]

CITIES_BY_REGION = {
    "northeast": [
        ("New York", "NY"),
        ("Boston", "MA"),
        ("Philadelphia", "PA"),
        ("Hartford", "CT"),
        ("Providence", "RI"),
    ],
    "southeast": [
        ("Atlanta", "GA"),
        ("Miami", "FL"),
        ("Charlotte", "NC"),
        ("Nashville", "TN"),
        ("Richmond", "VA"),
    ],
    "midwest": [
        ("Chicago", "IL"),
        ("Detroit", "MI"),
        ("Minneapolis", "MN"),
        ("Columbus", "OH"),
        ("Kansas City", "MO"),
    ],
    "west": [
        ("Los Angeles", "CA"),
        ("Seattle", "WA"),
        ("Portland", "OR"),
        ("San Francisco", "CA"),
        ("Denver", "CO"),
    ],
    "southwest": [
        ("Houston", "TX"),
        ("Phoenix", "AZ"),
        ("Dallas", "TX"),
        ("San Antonio", "TX"),
        ("Albuquerque", "NM"),
    ],
}

FIRST_NAMES = [
    "James", "Mary", "Robert", "Patricia", "John", "Jennifer", "Michael",
    "Linda", "David", "Elizabeth", "William", "Barbara", "Richard", "Susan",
    "Joseph", "Jessica", "Thomas", "Sarah", "Christopher", "Karen",
    "Daniel", "Lisa", "Matthew", "Nancy", "Anthony", "Betty", "Mark",
    "Margaret", "Steven", "Sandra", "Paul", "Ashley", "Andrew", "Dorothy",
    "Joshua", "Kimberly", "Kenneth", "Emily", "Kevin", "Donna",
]

LAST_NAMES = [
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller",
    "Davis", "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez",
    "Wilson", "Anderson", "Thomas", "Taylor", "Moore", "Jackson", "Martin",
    "Lee", "Perez", "Thompson", "White", "Harris", "Sanchez", "Clark",
    "Ramirez", "Lewis", "Robinson",
]

NOTES_OPTIONS = [
    None, None, None, None, None, None, None, None,  # mostly null
    "Gift wrap requested",
    "Express delivery",
    "Leave at front door",
    "Signature required",
    "Fragile - handle with care",
    "Customer loyalty discount applied",
    "Replacement order - original lost in transit",
    "Corporate purchase order #PO-8842",
]

# Base date: orders clustered in a 2-day window
BASE_DATE = datetime(2026, 2, 18, 9, 0, 0)


def generate_email(first: str, last: str, rng: random.Random) -> str:
    domains = ["gmail.com", "yahoo.com", "outlook.com", "hotmail.com", "icloud.com"]
    sep = rng.choice([".", "_", ""])
    num = rng.choice(["", str(rng.randint(1, 99))])
    domain = rng.choice(domains)
    return f"{first.lower()}{sep}{last.lower()}{num}@{domain}"


def generate_total_amount(rng: random.Random) -> float:
    """Generate order totals with a realistic distribution.

    Most orders are moderate ($20-$200), some are small, a few are large.
    """
    r = rng.random()
    if r < 0.10:
        # Small orders
        return round(rng.uniform(12.99, 29.99), 2)
    elif r < 0.75:
        # Moderate orders
        return round(rng.uniform(30.00, 249.99), 2)
    elif r < 0.92:
        # Larger orders
        return round(rng.uniform(250.00, 799.99), 2)
    else:
        # Big-ticket orders
        return round(rng.uniform(800.00, 2499.99), 2)


def generate_rows(rng: random.Random) -> list[dict]:
    rows = []

    for i in range(NUM_ROWS):
        order_id = f"ORD-{10001 + i}"

        first = rng.choice(FIRST_NAMES)
        last = rng.choice(LAST_NAMES)
        customer_name = f"{first} {last}"
        customer_email = generate_email(first, last, rng)

        # Order date: clustered within a 2-day window (48 hours)
        offset_hours = rng.gauss(24, 8)  # centered at 24h, std 8h
        offset_hours = max(0, min(48, offset_hours))  # clamp to [0, 48]
        order_dt = BASE_DATE + timedelta(hours=offset_hours)
        order_date = order_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

        status = rng.choices(STATUSES, weights=STATUS_WEIGHTS, k=1)[0]

        # Ship date: 1-5 days after order for shipped/delivered, null for pending/processing/cancelled
        if status in ("shipped", "delivered"):
            ship_offset_days = rng.randint(1, 5)
            ship_dt = order_dt + timedelta(days=ship_offset_days)
            ship_date = ship_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        else:
            ship_date = None

        region = rng.choices(REGIONS, weights=REGION_WEIGHTS, k=1)[0]
        city, state = rng.choice(CITIES_BY_REGION[region])

        # Country: mostly US (94%), with a few exceptions
        if rng.random() < 0.94:
            country = "US"
        else:
            country = rng.choice(["CA", "MX", "GB"])

        total_amount = generate_total_amount(rng)

        # Discount: mostly zero (85%), occasionally non-zero
        if rng.random() < 0.85:
            discount_amount = 0.00
        else:
            discount_amount = round(rng.uniform(2.00, min(total_amount * 0.25, 50.00)), 2)

        # Tax: percentage of (total - discount)
        tax_rate = rng.uniform(0.05, 0.10)
        tax_amount = round((total_amount - discount_amount) * tax_rate, 2)

        # Shipping cost
        if total_amount > 100:
            shipping_cost = 0.00  # free shipping over $100
        else:
            shipping_cost = round(rng.uniform(4.99, 14.99), 2)

        # Currency: mostly USD (92%)
        if rng.random() < 0.92:
            currency = "USD"
        else:
            currency = rng.choice(["CAD", "EUR", "GBP"])

        payment_method = rng.choices(PAYMENT_METHODS, weights=PAYMENT_WEIGHTS, k=1)[0]

        notes = rng.choice(NOTES_OPTIONS)

        row = {
            "order_id": order_id,
            "customer_name": customer_name,
            "customer_email": customer_email,
            "order_date": order_date,
            "ship_date": ship_date,
            "status": status,
            "region": region,
            "city": city,
            "state": state,
            "country": country,
            "total_amount": total_amount,
            "discount_amount": discount_amount,
            "tax_amount": tax_amount,
            "shipping_cost": shipping_cost,
            "currency": currency,
            "payment_method": payment_method,
            "notes": notes,
        }
        rows.append(row)

    return rows


def main() -> None:
    rng = random.Random(SEED)
    rows = generate_rows(rng)

    output_path = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "db_query_results.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    json_text = json.dumps(rows, indent=2)
    output_path.write_text(json_text + "\n")

    size_kb = len(json_text.encode()) / 1024
    print(f"Generated {len(rows)} rows with 17 columns each")
    print(f"Written to: {output_path}")
    print(f"JSON size: {size_kb:.1f} KB ({len(json_text)} bytes)")


if __name__ == "__main__":
    main()
