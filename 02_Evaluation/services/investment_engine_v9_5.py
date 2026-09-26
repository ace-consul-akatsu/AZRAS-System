
from __future__ import annotations
from typing import Any
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

def cashflow_sign_changes(cashflows: list[float], eps: float=1e-9) -> int:
    """Count sign changes ignoring zero/near-zero cash flows."""
    signs=[]
    for value in cashflows:
        if abs(value) <= eps:
            continue
        signs.append(1 if value > 0 else -1)
    return sum(1 for a,b in zip(signs, signs[1:]) if a != b)

def irr(cashflows: list[float], low: float=-0.99, high: float=10.0) -> float | None:
    # Conventional IRR is only meaningful for a conventional cash-flow pattern.
    # Multiple sign changes can produce multiple IRRs; do not return a search
    # boundary such as 1000% as if it were a valid result.
    if cashflow_sign_changes(cashflows) > 1:
        return None
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
    # Evaluation master cash-flow data is always generated for 200 years.
    # Compare may later display any subset from 1 to 200 years.
    settings=dict(settings or {})
    settings["analysis_years"]=200
    outputs=project.get("module_outputs",{})
    module5=outputs.get("module5")
    module7=outputs.get("module7")
    if not module5:
        raise ValueError("Module 5 output is required.")
    if not module7:
        raise ValueError("Module 7 output is required so renewal/rebuild costs can be included in cash flow.")

    m5_summary=module5.get("summary",{}) or {}
    construction_cost=_f(
        m5_summary.get("subtotal_before_tax"),
        _f(m5_summary.get("total_construction_cost"))
    )
    construction_tax=_f(m5_summary.get("tax_amount"))
    construction_cost_with_tax=construction_cost+construction_tax
    currency=str(module5.get("currency","JPY"))
    gfa=max(_f(project.get("common",{}).get("scale_gfa_m2")),1.0)

    years=200
    rent_per_m2=_f(settings.get("annual_rent_per_m2"))
    rent_setting_method=str(settings.get("rent_setting_method") or "gross_yield")
    target_gross_yield_percent=_f(settings.get("target_gross_yield_percent"),8.0)
    vacancy=max(min(_f(settings.get("vacancy_rate_percent"))/100.0,1.0),0.0)
    rent_growth=_f(settings.get("rent_growth_percent"))/100.0
    construction_cost_escalation_rate=max(
        _f(settings.get("construction_cost_escalation_percent"),0.0)/100.0,0.0
    )
    general_inflation_rate=max(
        _f(settings.get("general_inflation_percent"),0.0)/100.0,0.0
    )
    operating_rate=max(_f(settings.get("operating_expense_percent"))/100.0,0.0)
    # PATCH 079:
    # Planned repair / renewal / replacement / rebuild costs are owned by Module 7.
    # This rate is ONLY for routine day-to-day upkeep not represented in Module 7.
    routine_maintenance_rate=max(
        _f(settings.get("annual_maintenance_percent_of_cost"),0.0)/100.0,0.0
    )
    # Land/building-related taxes are intentionally excluded from Evaluation.
    # Tax regimes differ by country, state/prefecture, municipality and ownership.
    # Keep the legacy input key for backward JSON compatibility, but do not use it.
    property_tax_rate=0.0
    insurance_rate=max(_f(settings.get("insurance_percent_of_cost"))/100.0,0.0)
    earthquake_insurance_share_percent=max(
        min(_f(settings.get("earthquake_insurance_share_percent"),0.0),100.0),0.0
    )
    earthquake_insurance_discount_percent=max(
        min(_f(settings.get("earthquake_insurance_discount_percent"),0.0),50.0),0.0
    )
    earthquake_share=earthquake_insurance_share_percent/100.0
    earthquake_discount_rate=earthquake_insurance_discount_percent/100.0
    discount_rate=_f(settings.get("discount_rate_percent"))/100.0
    terminal_cap=max(_f(settings.get("terminal_cap_rate_percent"))/100.0,0.0001)
    sale_cost_rate=max(_f(settings.get("terminal_sale_cost_percent"))/100.0,0.0)
    land_cost=_f(settings.get("land_cost"))
    other_initial=_f(settings.get("other_initial_cost"))

    # Business interruption assumptions.
    # These are explicit planning inputs, not hidden method-specific penalties.
    total_dwelling_units=max(int(_f(settings.get("total_dwelling_units"),3)),1)
    affected_dwelling_units=max(int(_f(settings.get("partial_renewal_affected_dwelling_units"),1)),1)
    affected_dwelling_units=min(affected_dwelling_units,total_dwelling_units)
    configured_affected_floor_area=max(_f(settings.get("partial_renewal_affected_floor_area_m2"),0.0),0.0)

    # Partial-renewal affected fraction is derived, never a hidden fixed percentage.
    # Priority:
    # 1) explicit affected floor area / GFA
    # 2) affected dwelling units / total dwelling units
    if configured_affected_floor_area>0:
        partial_affected_fraction=max(min(configured_affected_floor_area/gfa,1.0),0.0)
        partial_affected_scope_source="module6.affected_floor_area_m2 / project_gfa"
    else:
        partial_affected_fraction=max(min(affected_dwelling_units/total_dwelling_units,1.0),0.0)
        partial_affected_scope_source="module6.affected_dwelling_units / total_dwelling_units"

    partial_downtime_months=max(_f(settings.get("partial_renewal_downtime_months"),1.0),0.0)
    all_infill_downtime_months=max(_f(settings.get("all_infill_downtime_months"),3.0),0.0)
    full_rebuild_reletting_months=max(_f(settings.get("full_rebuild_reletting_months"),3.0),0.0)
    relocation_comp_months=max(_f(settings.get("full_rebuild_relocation_compensation_months"),2.0),0.0)
    full_rebuild_moving_expense_base_currency=max(
        _f(
            settings.get("full_rebuild_moving_expense_base_currency"),
            _f(settings.get("full_rebuild_moving_expense_base_yen"),300000.0) if currency=="JPY" else 0.0
        ),0.0
    )

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
    cumulative_unlevered_ex_terminal=-initial_total
    cumulative_equity_ex_terminal=-equity
    # PATCH_209: persist present-value holding-period cumulative CF so Compare
    # can display it without independently recalculating Evaluation results.
    cumulative_discounted_unlevered_ex_terminal=-initial_total
    unlevered_cf=[-initial_total]
    equity_cf=[-equity]
    payback_year=None

    if rent_setting_method=="market_rent":
        base_gross_rent=gfa*rent_per_m2
        resolved_annual_rent_per_m2=rent_per_m2
        rent_setting_basis="market_rent_per_m2"
    else:
        rent_setting_method="gross_yield"
        if target_gross_yield_percent<=0:
            raise ValueError("Target gross yield must be greater than zero.")
        base_gross_rent=initial_total*(target_gross_yield_percent/100.0)
        resolved_annual_rent_per_m2=base_gross_rent/gfa if gfa else 0.0
        rent_setting_basis="initial_total_investment_x_target_gross_yield"
    year1_monthly_rent_per_unit=base_gross_rent/12.0/total_dwelling_units if total_dwelling_units else 0.0

    # Store resolved rent values with the saved settings for audit/reproducibility.
    settings["rent_setting_method"]=rent_setting_method
    # PATCH_009: keep the user's target for backward compatibility and for
    # restoring the UI when switching modes, but explicitly mark whether it
    # actually drove this calculation.
    settings["target_gross_yield_percent"]=target_gross_yield_percent
    settings["target_gross_yield_active"]=(rent_setting_method=="gross_yield")
    settings["resolved_annual_rent_per_m2"]=resolved_annual_rent_per_m2
    settings["resolved_year1_gross_rent"]=base_gross_rent
    settings["resolved_monthly_rent_per_unit"]=year1_monthly_rent_per_unit
    settings["rent_setting_basis"]=rent_setting_basis
    # PATCH_006: the gross yield this Project actually earns on its own
    # investment.  Under market rent it is DERIVED (rent x GFA / initial
    # investment) and differs per Project; under gross-yield mode it equals the
    # target by construction.  It is a standalone business indicator: it is kept
    # apart from target_gross_yield_percent (the user's input, which is never
    # overwritten) so no downstream comparison reads it as a premise.
    implied_gross_yield_percent=(base_gross_rent/initial_total*100.0) if initial_total else None
    settings["implied_gross_yield_percent"]=implied_gross_yield_percent

    terminal_value=0.0

    lifecycle_cost_by_year={}
    lifecycle_tax_by_year={}
    lifecycle_timeline=module7.get("annual_cost_timeline",[]) or []
    if len(lifecycle_timeline) != years:
        raise ValueError(f"Module 7 annual_cost_timeline must contain {years} years; got {len(lifecycle_timeline)}.")
    for row in lifecycle_timeline:
        y=int(_f(row.get("year")))
        if 1 <= y <= years:
            lifecycle_cost_by_year[y]=_f(
                row.get("annual_cost_before_tax"),
                _f(row.get("annual_cost"))
            )
            lifecycle_tax_by_year[y]=_f(row.get("annual_tax"))

    module7_total=_f((module7.get("summary") or {}).get("total_lifecycle_work_cost"))
    timeline_total=sum(lifecycle_cost_by_year.values())
    reconcile_tolerance=max(1.0,abs(module7_total)*1e-9)
    if module7_total>0 and abs(timeline_total-module7_total)>reconcile_tolerance:
        raise ValueError(
            "Module 7 lifecycle cost mismatch: annual_cost_timeline total "
            f"{timeline_total:.6f} != summary.total_lifecycle_work_cost {module7_total:.6f}."
        )

    module3=outputs.get("module3") or {}
    m5_summary=module5.get("summary",{}) or {}
    module5_duration_months=max(
        _f(
            m5_summary.get("estimated_construction_duration_months"),
            _f(m5_summary.get("duration_months"),0.0)
        ),
        0.0
    )
    events_by_year={}
    for e in module3.get("events",[]) or []:
        y=int(_f(e.get("year")))
        if 1 <= y <= years:
            events_by_year.setdefault(y,[]).append(e)

    # Precompute construction-related business interruption.
    # Full rebuild dominates other same-year interruption events.
    interruption_month_equiv_by_year={}
    relocation_cost_by_year={}
    moving_expense_by_year={}
    interruption_audit=[]

    def add_month_equiv(start_year, month_equiv, label, affected_fraction):
        remaining=max(month_equiv,0.0)
        y=start_year
        while remaining>1e-9 and y<=years:
            available=max(12.0-interruption_month_equiv_by_year.get(y,0.0),0.0)
            add=min(remaining,available)
            interruption_month_equiv_by_year[y]=interruption_month_equiv_by_year.get(y,0.0)+add
            if add>0:
                interruption_audit.append({
                    "source_year":start_year,"applied_year":y,"event":label,
                    "affected_fraction":affected_fraction,"whole_building_equivalent_months":add
                })
            remaining-=add
            y+=1

    for y,events in sorted(events_by_year.items()):
        full=[e for e in events if e.get("action")=="full_rebuild"]
        if full:
            # Entire building unavailable during demolition/rebuild. Construction
            # duration comes from Module 5; reletting is additional post-completion vacancy.
            total_months=module5_duration_months+full_rebuild_reletting_months
            add_month_equiv(y,total_months,"full_rebuild",1.0)
            # Relocation/tenant compensation as rent-equivalent months.
            event_gross=base_gross_rent*((1+rent_growth)**(y-1))
            relocation_cost_by_year[y]=event_gross/12.0*relocation_comp_months
            # Actual moving expense is a current-price input and is escalated
            # to the rebuild year using general inflation.
            moving_expense_by_year[y]=full_rebuild_moving_expense_base_currency*((1+general_inflation_rate)**y)
            continue

        # Partial renewals: only the work area loses rent. Other dwellings stay occupied.
        partial_month_equiv=0.0
        labels=[]
        for e in events:
            if e.get("action")!="replace_infill":
                continue
            comp=str(e.get("component_key") or "")

            # Future detailed events can carry their own affected area/unit data.
            event_affected_area=_f(e.get("affected_floor_area_m2"))
            event_affected_units=int(_f(e.get("affected_dwelling_units"),0))
            if event_affected_area>0:
                event_affected_fraction=max(min(event_affected_area/gfa,1.0),0.0)
                event_scope_source="module3.event.affected_floor_area_m2 / project_gfa"
            elif event_affected_units>0:
                event_affected_fraction=max(min(event_affected_units/total_dwelling_units,1.0),0.0)
                event_scope_source="module3.event.affected_dwelling_units / total_dwelling_units"
            else:
                event_affected_fraction=partial_affected_fraction
                event_scope_source=partial_affected_scope_source
            if comp in {"roof","infill_exterior"}:
                # Default: envelope work can be performed without making the dwelling unusable.
                months=0.0
            elif comp=="windows":
                months=min(partial_downtime_months,0.25)
            elif comp=="all_infill":
                months=all_infill_downtime_months
            elif comp in {"infill_layout","insulation"}:
                months=partial_downtime_months
            else:
                months=0.0
            if months>0:
                partial_month_equiv += months*event_affected_fraction
                labels.append(f"{comp}[{event_affected_fraction*100:.2f}%:{event_scope_source}]")
        if partial_month_equiv>0:
            add_month_equiv(
                y,partial_month_equiv,
                "partial_renewal:"+",".join(labels),
                partial_affected_fraction
            )

    for year in range(1,years+1):
        gross_rent=base_gross_rent*((1+rent_growth)**(year-1))
        baseline_effective_rent=gross_rent*(1-vacancy)
        interruption_month_equiv=min(interruption_month_equiv_by_year.get(year,0.0),12.0)
        construction_rent_loss=baseline_effective_rent*(interruption_month_equiv/12.0)
        effective_rent=max(baseline_effective_rent-construction_rent_loss,0.0)
        operating_expense=effective_rent*operating_rate
        # Routine fixed-cost OPEX is expressed in future nominal currency using
        # general inflation. Operating expense already moves with nominal rent.
        general_price_factor=(1+general_inflation_rate)**year
        maintenance=construction_cost*routine_maintenance_rate*general_price_factor
        property_tax=0.0
        gross_insurance=construction_cost*insurance_rate*general_price_factor
        insurance_discount_amount=gross_insurance*earthquake_share*earthquake_discount_rate
        insurance=max(gross_insurance-insurance_discount_amount,0.0)
        noi=effective_rent-operating_expense-maintenance-insurance

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
            next_year_general_price_factor=(1+general_inflation_rate)**(year+1)
            next_year_noi=(
                next_year_effective-next_year_effective*operating_rate-
                construction_cost*routine_maintenance_rate*next_year_general_price_factor-
                (construction_cost*insurance_rate*next_year_general_price_factor*(1-earthquake_share*earthquake_discount_rate))
            )
            terminal_value=max(next_year_noi/terminal_cap,0.0)
            terminal_net=terminal_value*(1-sale_cost_rate)-balance
            balance=0.0

        lifecycle_event_cost_base_year=lifecycle_cost_by_year.get(year,0.0)
        lifecycle_event_tax_base_year=lifecycle_tax_by_year.get(year,0.0)
        construction_price_factor=(1+construction_cost_escalation_rate)**year
        lifecycle_event_cost=lifecycle_event_cost_base_year*construction_price_factor
        lifecycle_event_tax=lifecycle_event_tax_base_year*construction_price_factor
        relocation_tenant_cost=relocation_cost_by_year.get(year,0.0)
        moving_expense_actual=moving_expense_by_year.get(year,0.0)
        business_interruption_cost=construction_rent_loss+relocation_tenant_cost+moving_expense_actual
        unlevered_cash=noi-lifecycle_event_cost-relocation_tenant_cost-moving_expense_actual+(terminal_value*(1-sale_cost_rate) if year==years else 0.0)
        equity_cash=noi-debt_service-lifecycle_event_cost-relocation_tenant_cost-moving_expense_actual+terminal_net
        discounted_unlevered=unlevered_cash/((1+discount_rate)**year)
        discounted_equity=equity_cash/((1+discount_rate)**year)

        cumulative_unlevered+=unlevered_cash
        cumulative_equity+=equity_cash

        terminal_sale_proceeds=terminal_value*(1-sale_cost_rate) if year==years else 0.0
        # Holding-period cumulative CF excludes terminal sale proceeds.
        cumulative_unlevered_ex_terminal += unlevered_cash - terminal_sale_proceeds
        cumulative_equity_ex_terminal += equity_cash - (terminal_net if year==years else 0.0)
        discounted_terminal=terminal_sale_proceeds/((1+discount_rate)**year) if terminal_sale_proceeds else 0.0
        cumulative_discounted_unlevered_ex_terminal += discounted_unlevered-discounted_terminal

        if payback_year is None and cumulative_equity_ex_terminal>=0:
            payback_year=year

        unlevered_cf.append(unlevered_cash)
        equity_cf.append(equity_cash)
        rows.append({
            "year":year,
            "gross_rent":gross_rent,
            "baseline_effective_rent":baseline_effective_rent,
            "construction_interruption_month_equiv":interruption_month_equiv,
            "construction_rent_loss":construction_rent_loss,
            "relocation_tenant_cost":relocation_tenant_cost,
            "moving_expense_actual":moving_expense_actual,
            "moving_expense_base_year":full_rebuild_moving_expense_base_currency if moving_expense_actual>0 else 0.0,
            "business_interruption_cost":business_interruption_cost,
            "effective_rent":effective_rent,
            "operating_expense":operating_expense,
            "maintenance_cost":maintenance,
            "property_tax":property_tax,
            "insurance_cost":insurance,
            "insurance_cost_before_earthquake_discount":gross_insurance,
            "earthquake_insurance_discount_amount":insurance_discount_amount,
            "earthquake_insurance_share_percent":earthquake_insurance_share_percent,
            "earthquake_insurance_discount_percent":earthquake_insurance_discount_percent,
            "noi":noi,
            "lifecycle_event_cost":lifecycle_event_cost,
            "lifecycle_event_cost_future_nominal":lifecycle_event_cost,
            "lifecycle_event_cost_base_year":lifecycle_event_cost_base_year,
            "construction_cost_escalation_factor":construction_price_factor,
            "lifecycle_event_tax":lifecycle_event_tax,
            "lifecycle_event_tax_base_year":lifecycle_event_tax_base_year,
            "general_inflation_factor":general_price_factor,
            "interest_payment":interest,
            "principal_payment":principal,
            "debt_service":debt_service,
            "terminal_sale_proceeds":terminal_sale_proceeds,
            "before_tax_cash_flow":equity_cash,
            "unlevered_cash_flow":unlevered_cash,
            "discounted_cash_flow":discounted_equity,
            "cumulative_equity_cash_flow":cumulative_equity,
            "cumulative_unlevered_cash_flow_ex_terminal":cumulative_unlevered_ex_terminal,
            "cumulative_equity_cash_flow_ex_terminal":cumulative_equity_ex_terminal,
            "cumulative_discounted_unlevered_cash_flow_ex_terminal":cumulative_discounted_unlevered_ex_terminal,
            "loan_balance":balance
        })

    year1=rows[0]
    unlevered_irr=irr(unlevered_cf)
    equity_irr=irr(equity_cf)
    total_debt=sum(r["debt_service"] for r in rows)
    dscr=(year1["noi"]/year1["debt_service"]) if year1["debt_service"]>0 else None


    def _horizon_summary(horizon: int, discount_rate_override: float|None=None) -> dict[str,Any]:
        """PATCH 073: comparable 50-year / 200-year business summary."""
        h=max(1,min(int(horizon),years))
        scenario_discount_rate=discount_rate if discount_rate_override is None else max(float(discount_rate_override),0.0)
        selected=rows[:h]

        unlevered=[-initial_total]
        equity_series=[-equity]

        for r in selected:
            unlevered.append(
                _f(r.get("noi"))
                - _f(r.get("lifecycle_event_cost"))
                - _f(r.get("relocation_tenant_cost"))
                - _f(r.get("moving_expense_actual"))
            )
            equity_series.append(
                _f(r.get("noi"))
                - _f(r.get("debt_service"))
                - _f(r.get("lifecycle_event_cost"))
                - _f(r.get("relocation_tenant_cost"))
                - _f(r.get("moving_expense_actual"))
            )

        next_year=h+1
        next_year_gross=base_gross_rent*((1+rent_growth)**(next_year-1))
        next_year_effective=next_year_gross*(1-vacancy)
        next_year_general_price_factor=(1+general_inflation_rate)**next_year
        next_year_noi=(
            next_year_effective
            - next_year_effective*operating_rate
            - construction_cost*routine_maintenance_rate*next_year_general_price_factor
            - (construction_cost*insurance_rate*next_year_general_price_factor*(1-earthquake_share*earthquake_discount_rate))
        )
        terminal_value=max(next_year_noi/terminal_cap,0.0)
        sale_net=terminal_value*(1-sale_cost_rate)

        loan_balance_at_h=_f(selected[-1].get("loan_balance")) if selected else loan_amount
        unlevered[-1]+=sale_net
        equity_series[-1]+=sale_net-loan_balance_at_h

        uirr=irr(unlevered)
        eirr=irr(equity_series)

        running=-equity
        payback=None
        for r in selected:
            running += (
                _f(r.get("noi"))
                - _f(r.get("debt_service"))
                - _f(r.get("lifecycle_event_cost"))
                - _f(r.get("relocation_tenant_cost"))
                - _f(r.get("moving_expense_actual"))
            )
            if payback is None and running>=0:
                payback=int(_f(r.get("year")))

        return {
            "horizon_years":h,
            "construction_cost":construction_cost,
            "construction_cost_before_tax":construction_cost,
            "construction_tax":construction_tax,
            "construction_cost_with_tax":construction_cost_with_tax,
            "initial_total_investment":initial_total,
            "terminal_value":terminal_value,
            "terminal_sale_proceeds_net_of_sale_cost":sale_net,
            "loan_balance_at_horizon":loan_balance_at_h,
            "unlevered_npv":npv(scenario_discount_rate,unlevered),
            "unlevered_irr_percent":uirr*100 if uirr is not None else None,
            "equity_npv":npv(scenario_discount_rate,equity_series),
            "equity_irr_percent":eirr*100 if eirr is not None else None,
            "total_lifecycle_event_cost":sum(_f(r.get("lifecycle_event_cost")) for r in selected),
            "total_lifecycle_event_cost_before_tax":sum(_f(r.get("lifecycle_event_cost")) for r in selected),
            "total_lifecycle_event_cost_future_nominal":sum(_f(r.get("lifecycle_event_cost")) for r in selected),
            "total_lifecycle_event_cost_base_year":sum(_f(r.get("lifecycle_event_cost_base_year")) for r in selected),
            "total_lifecycle_tax":sum(_f(r.get("lifecycle_event_tax")) for r in selected),
            "total_lifecycle_tax_base_year":sum(_f(r.get("lifecycle_event_tax_base_year")) for r in selected),
            "construction_cost_escalation_percent":construction_cost_escalation_rate*100.0,
            "general_inflation_percent":general_inflation_rate*100.0,
            "discount_rate_percent":scenario_discount_rate*100.0,
            "rent_growth_percent":rent_growth*100.0,
            "total_business_interruption_cost":sum(_f(r.get("business_interruption_cost")) for r in selected),
            "total_construction_rent_loss":sum(_f(r.get("construction_rent_loss")) for r in selected),
            "total_relocation_tenant_cost":sum(_f(r.get("relocation_tenant_cost")) for r in selected),
            "simple_payback_year":payback,
            "valuation_basis":"next-year NOI / terminal cap rate; sale cost deducted; remaining loan repaid from equity proceeds",
        }

    # PATCH 084 — always rebuild primary 60/120/180-year summaries
    # from the CURRENT inputs and CURRENT cash-flow rows.
    horizon_summaries={}
    for _h in (60,120,180):
        horizon_summaries[str(_h)] = _horizon_summary(_h)

    # PATCH 138 — constant-price lifecycle comparison.
    # This is NOT a second investment NPV. It removes future price escalation
    # from Module 7 lifecycle work so construction methods can be compared on
    # a common current-price basis over very long horizons.
    def _constant_price_summary(horizon:int)->dict[str,Any]:
        h=max(1,min(int(horizon),years))
        selected=rows[:h]
        lifecycle_base=sum(_f(r.get("lifecycle_event_cost_base_year")) for r in selected)
        lifecycle_nominal=sum(_f(r.get("lifecycle_event_cost")) for r in selected)
        return {
            "horizon_years":h,
            "price_basis":"current_base_year_price",
            "initial_construction_cost_before_tax":construction_cost,
            "lifecycle_event_cost_base_year":lifecycle_base,
            "combined_construction_and_lifecycle_base_year":construction_cost+lifecycle_base,
            "lifecycle_event_cost_future_nominal_reference":lifecycle_nominal,
            "construction_cost_escalation_applied":False,
            "general_inflation_applied":False,
            "discount_rate_applied":False,
            "note_ja":"工法そのものの長期費用差を見るため、Module 7の更新・修繕・解体・建替え費を現在価格のまま集計する。投資NPVではない。",
            "note_en":"Constant-price engineering comparison of Module 7 lifecycle work. This is not an investment NPV."
        }

    constant_price_comparison={str(_h):_constant_price_summary(_h) for _h in (60,120,180,200)}


    # PATCH 081 — transparent sensitivity analysis.
    # Primary user inputs remain unchanged. Only construction/renewal escalation
    # and general inflation are varied together at 1.0%, 1.5%, and 2.0%.
    def _scenario_horizon_summary(horizon:int, construction_escalation_percent:float, inflation_percent:float)->dict[str,Any]:
        h=max(1,min(int(horizon),years))
        construction_esc=max(float(construction_escalation_percent),0.0)/100.0
        inflation_esc=max(float(inflation_percent),0.0)/100.0
        selected=rows[:h]
        unlevered=[-initial_total]
        equity_series=[-equity]
        scenario_rows=[]

        for r in selected:
            y=int(_f(r.get("year")))
            baseline_effective_rent=_f(r.get("baseline_effective_rent"))
            construction_rent_loss=_f(r.get("construction_rent_loss"))
            relocation_tenant_cost=_f(r.get("relocation_tenant_cost"))
            effective_rent=max(baseline_effective_rent-construction_rent_loss,0.0)

            operating_expense=effective_rent*operating_rate
            general_price_factor=(1+inflation_esc)**y
            moving_expense_actual=full_rebuild_moving_expense_base_currency*general_price_factor if _f(r.get("moving_expense_actual"))>0 else 0.0
            construction_price_factor=(1+construction_esc)**y
            maintenance=construction_cost*routine_maintenance_rate*general_price_factor
            gross_insurance=construction_cost*insurance_rate*general_price_factor
            insurance_discount=gross_insurance*earthquake_share*earthquake_discount_rate
            insurance=max(gross_insurance-insurance_discount,0.0)
            noi=effective_rent-operating_expense-maintenance-insurance

            lifecycle_base=_f(r.get("lifecycle_event_cost_base_year"))
            lifecycle_future=lifecycle_base*construction_price_factor
            debt_service=_f(r.get("debt_service"))

            unlevered.append(noi-lifecycle_future-relocation_tenant_cost-moving_expense_actual)
            equity_series.append(noi-debt_service-lifecycle_future-relocation_tenant_cost-moving_expense_actual)

            scenario_rows.append({
                "year":y,
                "noi":noi,
                "lifecycle_event_cost":lifecycle_future,
                "business_interruption_cost":construction_rent_loss+relocation_tenant_cost+moving_expense_actual,
            })

        next_year=h+1
        next_year_gross=base_gross_rent*((1+rent_growth)**(next_year-1))
        next_year_effective=next_year_gross*(1-vacancy)
        next_price_factor=(1+inflation_esc)**next_year
        next_noi=(
            next_year_effective
            - next_year_effective*operating_rate
            - construction_cost*routine_maintenance_rate*next_price_factor
            - construction_cost*insurance_rate*next_price_factor
              *(1-earthquake_share*earthquake_discount_rate)
        )
        terminal_value=max(next_noi/terminal_cap,0.0)
        sale_net=terminal_value*(1-sale_cost_rate)
        loan_balance_at_h=_f(selected[-1].get("loan_balance")) if selected else loan_amount

        unlevered[-1]+=sale_net
        equity_series[-1]+=sale_net-loan_balance_at_h

        return {
            "horizon_years":h,
            "construction_cost_escalation_percent":construction_escalation_percent,
            "general_inflation_percent":inflation_percent,
            "unlevered_npv":npv(discount_rate,unlevered),
            "equity_npv":npv(discount_rate,equity_series),
            "terminal_value":terminal_value,
            "total_lifecycle_event_cost":sum(_f(x.get("lifecycle_event_cost")) for x in scenario_rows),
            "total_business_interruption_cost":sum(_f(x.get("business_interruption_cost")) for x in scenario_rows),
        }

    discount_rate_candidates=[2.0,3.0,4.0,5.0,6.0]
    current_discount_percent=discount_rate*100.0
    if all(abs(current_discount_percent-r)>1e-9 for r in discount_rate_candidates):
        discount_rate_candidates.append(current_discount_percent)
    discount_rate_candidates=sorted(set(round(r,6) for r in discount_rate_candidates))
    discount_rate_sensitivity={}
    for rate_percent in discount_rate_candidates:
        rate=rate_percent/100.0
        discount_rate_sensitivity[f"{rate_percent:g}"]={
            "discount_rate_percent":rate_percent,
            "is_current_input":abs(rate_percent-current_discount_percent)<1e-9,
            "horizons":{str(h):_horizon_summary(h,rate) for h in (50,100,150,200)}
        }

    sensitivity_scenarios={}
    for scenario_key,label_ja,construction_rate,inflation_rate in (
        ("low","低位",2.3,2.1),
        ("standard","標準（日本60年参考）",2.8,2.6),
        ("high","高位",3.3,3.1),
    ):
        sensitivity_scenarios[scenario_key]={
            "label_ja":label_ja,
            "construction_rate_percent":construction_rate,
            "inflation_rate_percent":inflation_rate,
            "rate_percent":construction_rate,
            "horizons":{
                "60":_scenario_horizon_summary(60,construction_rate,inflation_rate),
                "120":_scenario_horizon_summary(120,construction_rate,inflation_rate),
                "180":_scenario_horizon_summary(180,construction_rate,inflation_rate),
                "200":_scenario_horizon_summary(200,construction_rate,inflation_rate),
            }
        }

    summary={
        "construction_cost":construction_cost,
        "land_cost":land_cost,
        "other_initial_cost":other_initial,
        "initial_total_investment":initial_total,
        "loan_amount":loan_amount,
        "equity_investment":equity,
        "year1_gross_rent":year1["gross_rent"],
        "year1_monthly_rent_per_unit":year1_monthly_rent_per_unit,
        "resolved_annual_rent_per_m2":resolved_annual_rent_per_m2,
        "rent_setting_method":rent_setting_method,
        "rent_setting_basis":rent_setting_basis,
        # PATCH_009: in market-rent mode there is no active target yield.
        # Preserve the user's inactive preference in a separate key so the
        # saved JSON cannot be misread as if 8% (or another target) drove rent.
        "target_gross_yield_percent":(target_gross_yield_percent if rent_setting_method=="gross_yield" else None),
        "stored_target_gross_yield_percent":target_gross_yield_percent,
        "target_gross_yield_active":bool(rent_setting_method=="gross_yield"),
        # PATCH_005: state the revenue premise explicitly so a downstream
        # multi-Project comparison does not have to infer it.
        #
        # Under "gross_yield", rent is derived from this Project's own initial
        # investment at a fixed target yield. That is a sound way to study one
        # Project, but it makes the result non-comparable across buildings: a
        # more expensive building is automatically granted proportionally more
        # rent, and simple payback becomes independent of construction cost, so
        # every Project sharing the yield pays back in the same year whatever
        # it cost. Nothing here changes a cash flow; it only records the
        # premise the cash flow was built on.
        "revenue_basis_disclosure":{
            "patch":"PATCH_005",
            "audit_only":True,
            "rent_setting_method":rent_setting_method,
            "rent_setting_basis":rent_setting_basis,
            "rent_derived_from_construction_cost":bool(rent_setting_method=="gross_yield"),
            "target_gross_yield_percent":target_gross_yield_percent if rent_setting_method=="gross_yield" else None,
            "resolved_annual_rent_per_m2":resolved_annual_rent_per_m2,
            "comparable_across_projects":bool(rent_setting_method=="market_rent"),
            "comparison_note_ja":(
                "家賃を建設費から目標表面利回りで逆算しているため、単純投資回収年は建設費に依存しない。"
                "建物間の事業性比較には使えない。比較する場合は「市場家賃を直接入力」に切り替え、"
                "全Projectで同じ家賃を設定すること。"
                if rent_setting_method=="gross_yield" else
                "市場家賃を直接指定しているため、建設費の違いがそのまま事業性の違いとして表れる。"
                "同じ家賃を設定した他Projectとの比較に使用できる。"
            ),
            "comparison_note_en":(
                "Rent is derived from construction cost at a target gross yield, so simple payback does not "
                "depend on construction cost and this result cannot be used to compare buildings. Switch to "
                "market rent and apply the same rent to every Project before comparing."
                if rent_setting_method=="gross_yield" else
                "Rent is an explicit market figure, so a construction-cost difference shows up as a business "
                "difference. Comparable with other Projects set to the same rent."
            ),
        },
        "year1_effective_rent":year1["effective_rent"],
        "year1_noi":year1["noi"],
        "year1_gross_yield_percent":year1["gross_rent"]/initial_total*100 if initial_total else 0.0,
        # PATCH_006: standalone gross yield of this Project (see above).
        "implied_gross_yield_percent":implied_gross_yield_percent,
        "implied_gross_yield_basis":("market_rent_x_gfa_div_initial_investment"
                                     if rent_setting_method=="market_rent" else "equals_target_gross_yield"),
        "gross_yield_value_source":("market_rent_derived"
                                    if rent_setting_method=="market_rent" else "target_input"),
        "year1_noi_yield_percent":year1["noi"]/initial_total*100 if initial_total else 0.0,
        "unlevered_npv":npv(discount_rate,unlevered_cf),
        "unlevered_irr_percent":unlevered_irr*100 if unlevered_irr is not None else None,
        "unlevered_irr_status":"multiple_sign_changes_not_applicable" if cashflow_sign_changes(unlevered_cf)>1 else ("calculated" if unlevered_irr is not None else "no_root"),
        "equity_npv":npv(discount_rate,equity_cf),
        "equity_irr_percent":equity_irr*100 if equity_irr is not None else None,
        "equity_irr_status":"multiple_sign_changes_not_applicable" if cashflow_sign_changes(equity_cf)>1 else ("calculated" if equity_irr is not None else "no_root"),
        "terminal_value":terminal_value,
        "total_lifecycle_event_cost":sum(_f(r.get("lifecycle_event_cost")) for r in rows),
        "total_lifecycle_event_cost_before_tax":sum(_f(r.get("lifecycle_event_cost")) for r in rows),
        "total_lifecycle_event_cost_future_nominal":sum(_f(r.get("lifecycle_event_cost")) for r in rows),
        "total_lifecycle_event_cost_base_year":sum(lifecycle_cost_by_year.values()),
        "total_lifecycle_tax":sum(_f(r.get("lifecycle_event_tax")) for r in rows),
        "total_lifecycle_tax_base_year":sum(lifecycle_tax_by_year.values()),
        "construction_cost_before_tax":construction_cost,
        "construction_tax":construction_tax,
        "construction_cost_with_tax":construction_cost_with_tax,
        "tax_treatment":"consumption_tax_reported_separately_and_excluded_from_npv_cashflow",
        "total_construction_rent_loss":sum(r.get("construction_rent_loss",0.0) for r in rows),
        "total_relocation_tenant_cost":sum(r.get("relocation_tenant_cost",0.0) for r in rows),
        "total_business_interruption_cost":sum(r.get("business_interruption_cost",0.0) for r in rows),
        "module7_cost_source":"module7.annual_cost_timeline",
        "cumulative_unlevered_cash_flow":cumulative_unlevered,
        "cumulative_equity_cash_flow":cumulative_equity,
        "cumulative_unlevered_cash_flow_ex_terminal":cumulative_unlevered_ex_terminal,
        "cumulative_equity_cash_flow_ex_terminal":cumulative_equity_ex_terminal,
        "terminal_value_separated_from_cumulative_cf":True,
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
        "lifecycle_cost_integration":{
            "source":"module7.annual_cost_timeline",
            "integration_required":True,
            "integration_validated":True,
            "years_loaded":len(lifecycle_cost_by_year),
            "total_cost_base_year":sum(lifecycle_cost_by_year.values()),
            "module7_summary_total_lifecycle_work_cost":module7_total,
            "module7_timeline_reconciled":True,
            "total_cost_future_nominal":sum(_f(r.get("lifecycle_event_cost")) for r in rows),
            "construction_cost_escalation_percent":construction_cost_escalation_rate*100.0,
            "treatment":"Module 7 current-price lifecycle cost is escalated to future nominal cost in the event year, then discounted by the NPV discount rate.",
            "routine_maintenance_treatment":"Module 6 routine maintenance is limited to day-to-day upkeep not represented by Module 7. Planned repair/renewal/replacement/rebuild is counted only in Module 7. Routine maintenance and insurance are escalated by general inflation; operating expense follows rent because it is modeled as a percentage of rent."
        },
        "moving_expense_migration_policy":{
            "patch":"087",
            "legacy_zero_migrated_to_yen":300000.0,
            "migration_flag_key":"moving_expense_standard_migrated",
            "migration_once_only":True,
            "user_override_after_migration":True,
            "note_ja":"旧プロジェクトで移転実費が0円かつ移行フラグがない場合のみ、初回に30万円へ移行する。移行後はユーザーが0円を含め任意に変更できる。"
        },
        "relocation_cost_policy":{
            "tenant_compensation_basis":"rent_linked_months",
            "actual_moving_expense_basis":"current_price_input_escalated_by_general_inflation",
            "actual_moving_expense_base_currency":full_rebuild_moving_expense_base_currency,
        "actual_moving_expense_base_yen":full_rebuild_moving_expense_base_currency if currency=="JPY" else None,
            "standard_basis_yen_per_unit":100000.0,
            "standard_unit_count":3,
            "standard_total_yen":300000.0,
            "standard_value_status":"comparison_reference_user_editable",
            "legacy_zero_migration_patch":"087",
            "reference_country":"Japan",
            "reference_framework":"Public land acquisition / Land Expropriation Act loss-compensation practice",
            "note_ja":"退去補償は家賃連動。移転実費は現在価格入力を一般物価で将来額へ連動。※移転実費の算出における物価連動は日本の公共事業の土地収用法・損失補償の考え方を参考にしている。標準初期値は10万円/戸×3戸=30万円（現在価格）で、比較用の参考値。実事業では個別見積りで変更する。"
        },
        "insurance_cost_policy":{
            "base_insurance_percent_of_initial_construction_cost":insurance_rate*100.0,
            "earthquake_insurance_share_percent":earthquake_insurance_share_percent,
            "earthquake_insurance_discount_percent":earthquake_insurance_discount_percent,
            "automatic_method_discount":False,
            "verified_discount_only":True,
            "eligible_verified_discount_examples_percent":[10,30,50],
            "note_ja":"工法名だけで保険料を自動優遇しない。地震保険相当部分について、所定の確認資料で耐震性能等による割引が確認できる場合のみ10～50%の割引率を入力する。一般火災・財産保険部分には適用しない。"
        },
        "maintenance_cost_policy":{
            "module6_scope":"routine_day_to_day_upkeep_only",
            "module7_scope":"planned_inspection_repair_renewal_replacement_demolition_and_rebuild",
            "routine_maintenance_percent_of_initial_construction_cost":routine_maintenance_rate*100.0,
            "double_count_prevention":True,
            "note_ja":"Module 7で計上する計画修繕・更新・交換・解体・建替え費はModule 6の年間維持管理費に含めない。Module 6はModule 7に含まれない日常維持管理費のみを扱う。"
        },
        "value_rate_policy":{
            "rent_growth_percent":rent_growth*100.0,
            "construction_cost_escalation_percent":construction_cost_escalation_rate*100.0,
            "general_inflation_percent":general_inflation_rate*100.0,
            "discount_rate_percent":discount_rate*100.0,
            "formula_ja":{
                "rent":"年次家賃 = 1年目家賃 × (1 + 家賃上昇率)^(年-1)",
                "construction":"将来の建替え・更新費 = 現在単価ベース費用 × (1 + 建設・更新工事費上昇率)^発生年",
                "general_inflation":"維持管理・保険等の固定基準費 = 現在額 × (1 + 一般物価上昇率)^年",
                "present_value":"現在価値 = 将来名目キャッシュフロー ÷ (1 + NPV割引率)^年"
            },
            "note_ja":"4つの率は別々の経済条件として扱う。将来工事費を先に名目額へ上昇させ、その後NPV割引率で現在価値へ換算する。"
        },
        "tax_treatment":{
            "land_and_building_related_taxes":"excluded",
            "included_in_cashflow":False,
            "property_tax_percent_of_cost_applied":0.0,
            "legacy_property_tax_input_ignored":True,
            "policy_ja":"土地・建物に関する税金は国・地域によって税制が異なるため、本シミュレーションのCF計算対象外とし、別途考慮する。",
            "policy_en":"Taxes related to land and buildings vary by country and jurisdiction and are excluded from this simulation cash flow; they must be considered separately.",
            "scope_examples":[
                "property tax",
                "city planning / municipal real-estate tax",
                "real-estate acquisition tax",
                "other land/building-specific taxes"
            ]
        },
        "business_interruption_model":{
            "source":"Module 3 renewal events + Module 5 construction duration + Module 6 explicit assumptions",
            "policy":"full rebuild affects 100%; partial renewal affects only configured work area; other dwellings retain normal occupancy",
            "module5_rebuild_duration_months":module5_duration_months,
            "total_dwelling_units":total_dwelling_units,
            "partial_renewal_affected_dwelling_units":affected_dwelling_units,
            "partial_renewal_affected_floor_area_m2":configured_affected_floor_area,
            "derived_partial_renewal_affected_area_percent":partial_affected_fraction*100.0,
            "affected_scope_source":partial_affected_scope_source,
            "partial_renewal_downtime_months":partial_downtime_months,
            "all_infill_downtime_months":all_infill_downtime_months,
            "full_rebuild_reletting_months":full_rebuild_reletting_months,
            "full_rebuild_relocation_compensation_months":relocation_comp_months,
            "interruption_audit":interruption_audit
        },
        "cashflow":rows,
        "summary":summary,
        "horizon_summaries":horizon_summaries,
        "constant_price_comparison":constant_price_comparison,
        "comparison_framework":{
            "nominal_dcf":{
                "role":"investment_feasibility",
                "price_basis":"future_nominal",
                "construction_cost_escalation_percent":construction_cost_escalation_rate*100.0,
                "general_inflation_percent":general_inflation_rate*100.0,
                "discount_rate_percent":discount_rate*100.0,
                "note_ja":"事業家向け投資採算。将来名目CFを割引率で現在価値化する。"
            },
            "constant_price":{
                "role":"long_term_method_cost_comparison",
                "price_basis":"current_base_year_price",
                "discount_rate_applied":False,
                "note_ja":"200年など超長期の工法差を見る補助指標。将来物価を予測せず現在価格で比較する。"
            },
            "sensitivity":{
                "role":"long_term_economic_uncertainty",
                "scenarios":["low","standard","high"],
                "note_ja":"長期の上昇率を確定予測とせず、低位・標準・高位で確認する。"
            }
        },
        "comparison_horizons":[60,120,180,200],
        "primary_horizon_recalculation":{
            "status":"rebuilt_from_current_inputs",
            "construction_cost_escalation_percent":construction_cost_escalation_rate*100.0,
            "general_inflation_percent":general_inflation_rate*100.0,
            "rent_growth_percent":rent_growth*100.0,
            "discount_rate_percent":discount_rate*100.0,
            "horizons":[60,120,180],
            "note_ja":"60・120・180年の主比較値は、保存済み旧集計を再利用せず、現在入力値から毎回再生成する。"
        },
        "sensitivity_scenarios":sensitivity_scenarios,
        "discount_rate_sensitivity":discount_rate_sensitivity,
        "discount_rate_sensitivity_policy":{
            "rates_percent":discount_rate_candidates,
            "horizons":[50,100,150,200],
            "varied_input":"discount_rate_percent",
            "fixed_inputs":["rent_growth_percent","construction_cost_escalation_percent","general_inflation_percent","all_other_module6_settings"],
            "terminal_value_recalculated_at_each_horizon":True,
            "reference_status":"planning_sensitivity_not_forecast"
        },
        "sensitivity_policy":{
            "low_construction_percent":2.3,
            "low_general_inflation_percent":2.1,
            "standard_construction_percent":2.8,
            "standard_general_inflation_percent":2.6,
            "high_construction_percent":3.3,
            "high_general_inflation_percent":3.1,
            "new_project_default_construction_percent":2.8,
            "new_project_default_general_inflation_percent":2.6,
            "reference_country":"Japan",
            "reference_sources":[
                "MLIT Construction Work Cost Deflator",
                "Statistics Bureau of Japan Consumer Price Index (CPI)"
            ],
            "reference_status":"sensitivity_reference_not_forecast",
            "varied_inputs":["construction_cost_escalation_percent","general_inflation_percent"],
            "fixed_inputs":["rent_growth_percent","discount_rate_percent","all_other_module6_settings"],
            "note_ja":"標準参考は建設・更新工事費2.8%/年、一般物価2.6%/年。日本の過去約60年の統計を参考にした感度条件であり将来予測ではない。120年・180年・200年は低位・標準・高位のシナリオとして解釈し、現在価格比較を併記する。"
        },
        "tax_policy":{
            "consumption_tax":"reported_separately_not_in_npv",
            "construction_tax":construction_tax,
            "lifecycle_tax_total":sum(_f(r.get("lifecycle_event_tax")) for r in rows),
            "lifecycle_tax_total_base_year":sum(lifecycle_tax_by_year.values()),
            "note_ja":"消費税は建設費・更新修繕費・NPVから除外し、別項目として表示する。固定資産税等は従来どおりEvaluation対象外。"
        },
        "status":"provisional_planning_comparison",
        "disclaimer":"Planning comparison only. Land/building-related taxes are excluded and must be considered separately according to the applicable jurisdiction. Use verified market, financing and valuation assumptions for formal decisions."
    }
