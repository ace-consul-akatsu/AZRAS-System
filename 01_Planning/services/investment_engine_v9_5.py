
from __future__ import annotations
from typing import Any

from core.project_coordinator import require_current_module_output
import math

def _f(v: Any, default: float=0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default

def npv(rate: float, cashflows: list[float]) -> float:
    """NPV calculation that remains stable for long analysis periods.

    A rate extremely close to -100% can make (1 + rate) ** year underflow
    to zero during a 100-year evaluation. Return a signed infinity instead
    of raising ZeroDivisionError so the IRR bracketing routine can continue.
    """
    base = 1.0 + rate
    if base <= 0.0:
        return math.inf

    total = 0.0
    discount_factor = 1.0
    for year, cashflow in enumerate(cashflows):
        if year > 0:
            discount_factor *= base
        if discount_factor == 0.0:
            if cashflow > 0:
                return math.inf
            if cashflow < 0:
                return -math.inf
            continue
        term = cashflow / discount_factor
        total += term
        if math.isinf(total):
            return total
    return total

def irr(cashflows: list[float], low: float=-0.99, high: float=10.0) -> float | None:
    # Robust bisection; returns None where no sign change exists.
    def f(r: float) -> float:
        return npv(r, cashflows)
    fl=f(low); fh=f(high)
    if (
        math.isnan(fl)
        or math.isnan(fh)
        or (math.isfinite(fl) and math.isfinite(fh) and fl * fh > 0)
        or (math.isinf(fl) and math.isinf(fh) and fl == fh)
    ):
        # Try a broader logarithmic scan to locate a sign change.
        points=[-0.99,-0.9,-0.75,-0.5,-0.25,0,0.02,0.05,0.1,0.2,0.5,1,2,5,10]
        previous=points[0]; fp=f(previous)
        bracket=None
        for p in points[1:]:
            fc=f(p)
            if fp==0:
                return previous
            if fp*fc<0:
                bracket=(previous,p);break
            previous=p;fp=fc
        if bracket is None:
            return None
        low,high=bracket
    fl = f(low)
    for _ in range(200):
        mid=(low+high)/2
        fm=f(mid)
        if math.isfinite(fm) and abs(fm)<1e-6:
            return mid
        if (
            (fl <= 0 <= fm)
            or (fm <= 0 <= fl)
            or (math.isinf(fl) and math.isfinite(fm) and fl * fm <= 0)
        ):
            high=mid
        else:
            low=mid
            fl=fm
    return (low+high)/2

def annual_loan_payment(principal: float, annual_rate: float, years: int) -> float:
    if principal<=0 or years<=0:
        return 0.0
    if abs(annual_rate)<1e-12:
        return principal/years
    return principal * annual_rate * (1+annual_rate)**years / ((1+annual_rate)**years-1)

def calculate_investment(project: dict[str, Any], settings: dict[str, Any]) -> dict[str, Any]:
    module5=require_current_module_output(project, "module5", "Module 5")

    construction_cost=_f(module5.get("summary",{}).get("total_construction_cost"))
    currency=str(module5.get("currency","JPY"))
    _m5_unpriced=list(module5.get("unpriced_cost_lines") or [])
    _m5_partial=(bool(module5.get("construction_cost_is_partial")) or (bool(module5.get("priced_total_excludes_unpriced_items")) and bool(_m5_unpriced)))
    _m5_quantity_cost_gap_count=int((module5.get("quantity_cost_coverage_audit") or {}).get("monetary_gap_count") or 0)
    construction_cost_input_status={
        "source":"module5",
        "is_partial":_m5_partial,
        "priced_total_excludes_unpriced_items":_m5_partial,
        "unpriced_item_count":len(_m5_unpriced),
        "quantity_cost_gap_count":_m5_quantity_cost_gap_count,
    }
    gfa=max(_f(project.get("common",{}).get("scale_gfa_m2")),1.0)

    years=max(int(_f(settings.get("analysis_years"),50)),1)
    rent_per_m2=_f(settings.get("annual_rent_per_m2"))
    vacancy=max(min(_f(settings.get("vacancy_rate_percent"))/100.0,1.0),0.0)
    rent_growth=_f(settings.get("rent_growth_percent"))/100.0
    operating_rate=max(_f(settings.get("operating_expense_percent"))/100.0,0.0)
    maintenance_rate=max(_f(settings.get("annual_maintenance_percent_of_cost"))/100.0,0.0)
    property_tax_rate=max(_f(settings.get("property_tax_percent_of_cost"))/100.0,0.0)
    insurance_rate=max(_f(settings.get("insurance_percent_of_cost"))/100.0,0.0)
    discount_rate=_f(settings.get("discount_rate_percent"))/100.0
    terminal_cap=max(_f(settings.get("terminal_cap_rate_percent"))/100.0,0.0001)
    sale_cost_rate=max(_f(settings.get("terminal_sale_cost_percent"))/100.0,0.0)
    land_cost=_f(settings.get("land_cost"))
    other_initial=_f(settings.get("other_initial_cost"))

    initial_total=construction_cost+land_cost+other_initial

    use_loan=bool(settings.get("use_loan"))
    ltc=max(min(_f(settings.get("loan_to_cost_percent"))/100.0,1.0),0.0) if use_loan else 0.0
    loan_rate=max(_f(settings.get("annual_interest_rate_percent"))/100.0,0.0)
    loan_term=max(int(_f(settings.get("loan_term_years"),30)),1)
    loan_amount=initial_total*ltc
    equity=initial_total-loan_amount
    payment=annual_loan_payment(loan_amount,loan_rate,loan_term)

    rows=[]
    balance=loan_amount
    cumulative_unlevered=-initial_total
    cumulative_equity=-equity
    unlevered_cf=[-initial_total]
    equity_cf=[-equity]
    payback_year=None

    base_gross_rent=gfa*rent_per_m2
    terminal_value=0.0

    for year in range(1,years+1):
        gross_rent=base_gross_rent*((1+rent_growth)**(year-1))
        effective_rent=gross_rent*(1-vacancy)
        operating_expense=effective_rent*operating_rate
        maintenance=construction_cost*maintenance_rate
        property_tax=construction_cost*property_tax_rate
        insurance=construction_cost*insurance_rate
        noi=effective_rent-operating_expense-maintenance-property_tax-insurance

        interest=principal=debt_service=0.0
        if use_loan and year<=loan_term and balance>1e-8:
            interest=balance*loan_rate
            debt_service=min(payment,balance+interest)
            principal=max(debt_service-interest,0.0)
            balance=max(balance-principal,0.0)

        terminal_net=0.0
        if year==years:
            next_year_gross=base_gross_rent*((1+rent_growth)**year)
            next_year_effective=next_year_gross*(1-vacancy)
            next_year_noi=(
                next_year_effective-next_year_effective*operating_rate-
                construction_cost*maintenance_rate-
                construction_cost*property_tax_rate-
                construction_cost*insurance_rate
            )
            terminal_value=max(next_year_noi/terminal_cap,0.0)
            terminal_net=terminal_value*(1-sale_cost_rate)-balance
            balance=0.0

        unlevered_cash=noi+(terminal_value*(1-sale_cost_rate) if year==years else 0.0)
        equity_cash=noi-debt_service+terminal_net
        discounted_unlevered=unlevered_cash/((1+discount_rate)**year)
        discounted_equity=equity_cash/((1+discount_rate)**year)

        cumulative_unlevered+=unlevered_cash
        cumulative_equity+=equity_cash
        if payback_year is None and cumulative_equity>=0:
            payback_year=year

        unlevered_cf.append(unlevered_cash)
        equity_cf.append(equity_cash)
        rows.append({
            "year":year,
            "gross_rent":gross_rent,
            "effective_rent":effective_rent,
            "operating_expense":operating_expense,
            "maintenance_cost":maintenance,
            "property_tax":property_tax,
            "insurance_cost":insurance,
            "noi":noi,
            "interest_payment":interest,
            "principal_payment":principal,
            "debt_service":debt_service,
            "terminal_sale_proceeds":terminal_value*(1-sale_cost_rate) if year==years else 0.0,
            "before_tax_cash_flow":equity_cash,
            "unlevered_cash_flow":unlevered_cash,
            "discounted_cash_flow":discounted_equity,
            "cumulative_equity_cash_flow":cumulative_equity,
            "loan_balance":balance
        })

    year1=rows[0]
    unlevered_irr=irr(unlevered_cf)
    equity_irr=irr(equity_cf)
    total_debt=sum(r["debt_service"] for r in rows)
    dscr=(year1["noi"]/year1["debt_service"]) if year1["debt_service"]>0 else None

    summary={
        "construction_cost":construction_cost,
        "land_cost":land_cost,
        "other_initial_cost":other_initial,
        "initial_total_investment":initial_total,
        "loan_amount":loan_amount,
        "equity_investment":equity,
        "year1_gross_rent":year1["gross_rent"],
        "year1_effective_rent":year1["effective_rent"],
        "year1_noi":year1["noi"],
        "year1_gross_yield_percent":year1["gross_rent"]/initial_total*100 if initial_total else 0.0,
        "year1_noi_yield_percent":year1["noi"]/initial_total*100 if initial_total else 0.0,
        "unlevered_npv":npv(discount_rate,unlevered_cf),
        "unlevered_irr_percent":unlevered_irr*100 if unlevered_irr is not None else None,
        "equity_npv":npv(discount_rate,equity_cf),
        "equity_irr_percent":equity_irr*100 if equity_irr is not None else None,
        "terminal_value":terminal_value,
        "cumulative_unlevered_cash_flow":cumulative_unlevered,
        "cumulative_equity_cash_flow":cumulative_equity,
        "total_debt_service":total_debt,
        "year1_dscr":dscr,
        "simple_payback_year":payback_year
    }

    return {
        "version":"9.5",
        "module":"module6",
        "currency":currency,
        "analysis_years":years,
        "settings":settings,
        "cashflow":rows,
        "summary":summary,
        "construction_cost_input_status":construction_cost_input_status,
        "status":"provisional_planning_comparison_incomplete_construction_cost" if _m5_partial else "provisional_planning_comparison",
        "disclaimer":"Planning comparison only; use verified market, financing, tax and valuation assumptions for formal decisions."
    }
