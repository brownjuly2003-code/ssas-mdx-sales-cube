from datetime import date

from sales_cube.data import build_star
from sales_cube.reference import reference


def test_calendar_and_foreign_keys():
    star = build_star(seed=64)
    dates = star["DimDate"]
    assert len(dates) == 731
    assert dates["DayDate"].min() == date(2024, 1, 1)
    assert dates["DayDate"].max() == date(2025, 12, 31)
    facts = star["FactSales"]
    assert facts["LineKey"].is_unique
    assert facts["Revenue"].gt(0).all()
    for table, key in [
        ("DimDate", "DateKey"),
        ("DimProduct", "ProductKey"),
        ("DimCustomer", "CustomerKey"),
    ]:
        assert star[table][key].is_unique
        assert facts[key].isin(star[table][key]).all()


def test_calendar_metrics_use_the_correct_periods():
    star = build_star(seed=64)
    facts = star["FactSales"]
    march = facts[facts["DateKey"].between(20250301, 20250331)]["Revenue"].sum()
    prior = facts[facts["DateKey"].between(20240301, 20240331)]["Revenue"].sum()
    ytd = facts[facts["DateKey"].between(20250101, 20250331)]["Revenue"].sum()
    answers = reference(star)
    assert answers["06_ytd_march"] == [[int(ytd)]]
    assert answers["07_prior_march"] == [[int(prior)]]
    assert answers["08_march_change"] == [[int(march - prior)]]
    assert answers["01_total"] == [[int(facts["Revenue"].sum())]]
