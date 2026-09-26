from __future__ import annotations
from pathlib import Path
import sys
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
from services.investment_engine_v9_5 import calculate_investment

def project(method,year,cost):
    timeline=[{"year":y,"annual_cost":cost if y==year else 0.0,"cumulative_cost":cost if y>=year else 0.0} for y in range(1,201)]
    return {"common":{"scale_gfa_m2":100.0,"unit_count":1,"construction_method_profile":method},
      "module_outputs":{
        "module5":{"currency":"JPY","summary":{"subtotal_before_tax":100000000.0,"tax_amount":0.0,"total_construction_cost":100000000.0}},
        "module7":{"annual_cost_timeline":timeline,"summary":{"total_lifecycle_work_cost":cost}},
        "module3":{"timeline":[]}}}

def main():
    s={"rent_setting_method":"gross_yield","target_gross_yield_percent":8.0,"vacancy_rate_percent":5.0,
       "operating_expense_rate_percent":10.0,"routine_maintenance_rate_percent":0.0,"insurance_rate_percent":0.0,
       "discount_rate_percent":4.0,"rent_growth_rate_percent":0.0,"construction_cost_escalation_percent":0.0,
       "general_inflation_percent":0.0,"terminal_cap_rate_percent":5.0,"sale_cost_rate_percent":0.0,"use_loan":False}
    errors=[]
    for method,year,cost in [("2x6 Timber",60,90000000.0),("AZRAS",60,30000000.0),("RC Frame",90,140000000.0)]:
        out=calculate_investment(project(method,year,cost),s)
        r=next(x for x in out["cashflow"] if x["year"]==year)
        if abs(r["lifecycle_event_cost"]-cost)>1e-6: errors.append(method+" cost not loaded")
        if abs(r["unlevered_cash_flow"]-(r["noi"]-cost))>1e-6: errors.append(method+" cost not deducted")
    bad=project("2x6 Timber",60,90000000.0)
    bad["module_outputs"]["module7"]["annual_cost_timeline"].pop()
    try: calculate_investment(bad,s); errors.append("incomplete timeline accepted")
    except ValueError: pass
    if errors:
        for e in errors: print("[NG]",e)
        return 1
    print("[OK] Module7 costs are deducted from Module6 CF")
    print("[OK] 2x6 year-60 rebuild regression")
    print("[OK] AZRAS year-60 renewal regression")
    print("[OK] RC Frame year-90 rebuild regression")
    print("[OK] incomplete Module7 timeline fails closed")
    return 0
if __name__=="__main__": raise SystemExit(main())
