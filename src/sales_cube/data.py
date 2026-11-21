from datetime import date, timedelta
from pathlib import Path
from random import Random

import pandas as pd


def build_star(seed: int = 64) -> dict[str, pd.DataFrame]:
    rng = Random(seed)
    products = [
        (1, "Desk", "Office", 180),
        (2, "Chair", "Office", 90),
        (3, "Lamp", "Office", 35),
        (4, "Mouse", "Tech", 25),
        (5, "Screen", "Tech", 240),
        (6, "Keyboard", "Tech", 60),
    ]
    customers = [
        (1, "Aspen", "East"),
        (2, "Birch", "East"),
        (3, "Cedar", "West"),
        (4, "Elm", "West"),
    ]
    days, sales = [], []
    day = date(2024, 1, 1)
    while day < date(2026, 1, 1):
        month = day.year * 100 + day.month
        day_key = month * 100 + day.day
        days.append((day_key, day, month, day.strftime("%Y-%m"), day.year))
        for _ in range(rng.randrange(1, 5)):
            product, _, _, price = rng.choice(products)
            customer, _, _ = rng.choice(customers)
            units = rng.randint(1, 8)
            sales.append(
                (len(sales) + 1, day_key, product, customer, units, price * units)
            )
        day += timedelta(days=1)
    return {
        "DimDate": pd.DataFrame(
            days, columns=["DateKey", "DayDate", "MonthKey", "MonthLabel", "YearNumber"]
        ),
        "DimProduct": pd.DataFrame(
            [p[:3] for p in products], columns=["ProductKey", "ProductName", "Category"]
        ),
        "DimCustomer": pd.DataFrame(
            customers, columns=["CustomerKey", "CustomerName", "Region"]
        ),
        "FactSales": pd.DataFrame(
            sales,
            columns=[
                "LineKey",
                "DateKey",
                "ProductKey",
                "CustomerKey",
                "Units",
                "Revenue",
            ],
        ),
    }


def sql_literal(value: object) -> str:
    if isinstance(value, int):
        return str(value)
    if isinstance(value, date):
        return "'" + value.isoformat() + "'"
    return "'" + str(value).replace("'", "''") + "'"


def write_inserts(star: dict[str, pd.DataFrame], path: Path) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as output:
        for table, frame in star.items():
            rows = list(frame.itertuples(index=False, name=None))
            for start in range(0, len(rows), 500):
                output.write(
                    f"INSERT INTO dbo.{table} ({', '.join(frame.columns)}) VALUES\n"
                )
                values = [
                    "(" + ", ".join(map(sql_literal, row)) + ")"
                    for row in rows[start : start + 500]
                ]
                output.write(",\n".join(values) + ";\n")
