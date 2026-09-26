# -*- coding: utf-8 -*-
"""PATCH_009 self-check: market-rent validation and saved JSON semantics."""
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
FAIL=[]

def ok(cond,label,detail=""):
    if cond:
        print(f"  [OK]   {label}")
    else:
        FAIL.append(f"{label}: {detail}")
        print(f"  [NG]   {label}: {detail}")

print("PATCH_009 self-check")
ui=(ROOT/'module6/app.py').read_text(encoding='utf-8')
engine=(ROOT/'services/investment_engine_v9_5.py').read_text(encoding='utf-8')

# Extract the helper only; no Tkinter UI is needed.
start=ui.index('    def _empty_required_fields(self):')
end=ui.index('\n    def calculate(self):',start)
body=ui[start:end]
ns={}
exec('class M:\n'+body,ns)
M=ns['M']

class Var:
    def __init__(self,v=''): self.v=v
    def get(self): return self.v
class Method:
    def __init__(self,v): self.v=v
    def get(self): return self.v

def make(method,target='',rent=''):
    m=M(); m.rent_setting_method=Method(method)
    m.vars={
        'target_gross_yield_percent':Var(target),
        'annual_rent_per_m2':Var(rent),
        'vacancy_rate_percent':Var('5.0'),
    }
    return m

m=make('market_rent','', '15000')
empty=m._empty_required_fields()
ok('target_gross_yield_percent' not in empty,'market-rent mode does not require target yield',str(empty))
ok('annual_rent_per_m2' not in empty,'market-rent mode accepts entered market rent',str(empty))

m=make('gross_yield','8.0','')
empty=m._empty_required_fields()
ok('annual_rent_per_m2' not in empty,'gross-yield mode does not require market rent',str(empty))
ok('target_gross_yield_percent' not in empty,'gross-yield mode accepts entered target',str(empty))

m=make('market_rent','','')
empty=m._empty_required_fields()
ok('annual_rent_per_m2' in empty,'market-rent mode still requires market rent',str(empty))

ok('"target_gross_yield_percent":(target_gross_yield_percent if rent_setting_method=="gross_yield" else None)' in engine,
   'summary active target is null in market-rent mode')
ok('"stored_target_gross_yield_percent":target_gross_yield_percent' in engine,
   'summary preserves the user target separately')
ok('"target_gross_yield_active":bool(rent_setting_method=="gross_yield")' in engine,
   'summary marks whether the target is active')
ok('settings["target_gross_yield_active"]=(rent_setting_method=="gross_yield")' in engine,
   'resolved settings mark whether the target is active')
ok('"gross_yield_value_source":("market_rent_derived"' in engine,
   'JSON records the source of the displayed yield')
ok('settings["implied_gross_yield_percent"]=implied_gross_yield_percent' in engine,
   'derived yield remains persisted')

if FAIL:
    print('\n[NG] PATCH_009 self-check FAILED')
    for f in FAIL: print(' -',f)
    raise SystemExit(1)
print('\nPATCH_009_MARKET_RENT_VALIDATION_JSON_PASS')
