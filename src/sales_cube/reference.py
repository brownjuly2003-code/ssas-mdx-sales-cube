import pandas as pd


def reference(star: dict[str, pd.DataFrame]) -> dict[str, list[list]]:
    sales = star["FactSales"]
    for table, key in [
        ("DimDate", "DateKey"),
        ("DimProduct", "ProductKey"),
        ("DimCustomer", "CustomerKey"),
    ]:
        sales = sales.merge(star[table], on=key, validate="many_to_one")

    current = sales[sales["YearNumber"] == 2025]
    monthly = sales.groupby("MonthKey")["Revenue"].sum()
    march = int(monthly.loc[202503])
    prior = int(monthly.loc[202403])

    def grouped(frame, key, measure="Revenue"):
        totals = frame.groupby(key, sort=True)[measure].sum()
        return [[str(label), int(value)] for label, value in totals.items()]

    amounts = current.groupby(["ProductKey", "ProductName"], as_index=False)[
        "Revenue"
    ].sum()
    ranked = amounts.sort_values(
        ["Revenue", "ProductKey"], ascending=[False, True]
    ).head(3)
    east_office = current[
        (current["Region"] == "East") & (current["Category"] == "Office")
    ]
    return {
        "01_total": [[int(sales["Revenue"].sum())]],
        "02_units_by_year": grouped(sales, "YearNumber", "Units"),
        "03_category": grouped(current, "Category"),
        "04_region": grouped(current, "Region"),
        "05_months": grouped(current, "MonthLabel"),
        "06_ytd_march": [[int(monthly.loc[202501:202503].sum())]],
        "07_prior_march": [[prior]],
        "08_march_change": [[march - prior]],
        "09_top_products": [
            [row.ProductName, int(row.Revenue)] for row in ranked.itertuples()
        ],
        "10_east_office": grouped(east_office, "CustomerName"),
    }
