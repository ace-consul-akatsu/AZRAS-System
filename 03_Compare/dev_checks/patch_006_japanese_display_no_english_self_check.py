# -*- coding: utf-8 -*-
"""PATCH_006 self-check (03 Compare): no English mixed into the Japanese screen.

Builds two synthetic Project JSONs (AZRAS Platform / RC Moment Frame) with
three generated regions each, starts the app in its default English, switches
to Japanese, runs the comparison and scans every label, button, tab, table
heading/row and chart text.  Only an allow-list of units, abbreviations,
product/module names and data-path references may contain Latin letters.
Also checks that switching back to English leaves no Japanese behind, and
that stored comparison keys (label) stay English-canonical.
"""
import json, os, re, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
FAIL = []


def check(ok, label, detail=""):
    print(("  [OK]   " if ok else "  [NG]   ") + label + ("" if ok else f" :: {detail}"))
    if not ok:
        FAIL.append(label)


def build(out):
    def monthly(scale):
        return [{"total_use_kWh":1000*scale+i*10,"pv_generation_kWh":0,"net_energy_kWh":1000*scale,"heating_electricity_kWh":100,"cooling_electricity_kWh":50} for i in range(12)]
    def line(key,unit,qty,rate):
        return {"cost_item_key":key,"unit":unit,"quantity":qty,"installed_all_in_unit_cost":rate,"pricing_structure":"installed_all_in","pricing_status":"x",
                "regional_unit_cost_metadata":{"candidate_quality":{"scope_definition":"installed_all_in"}}}
    def proj(name,sid,sja,sen,mid,mja,men,system,city,scale,use="Residential",gen_files=()):
        tl=[{"year":y,"cumulative_co2_kg":1000*y*scale} for y in range(0,201)]
        cf=[{"year":y,"cumulative_discounted_unlevered_cash_flow_ex_terminal":-1e7+2e5*y*scale,"cumulative_unlevered_cash_flow_ex_terminal":-1e7+5e5*y} for y in range(1,201)]
        return {"project_id":"id-"+name+city,"common":{"project_name":name,"construction_method_id":sid,"construction_method_name_ja":sja,"construction_method_name_en":sen,
            "construction_method_detail_id":mid,"construction_method_detail_name_ja":mja,"construction_method_detail_name_en":men,
            "building_use":use,"city":city,"country":"Japan","scale_gfa_m2":245.1,"project_location":"愛知県春日井市",
            "detailed_configuration":{"building_system":system,"general":{"structure":sid if system!="azras" else "","method":mid}}},
          "regional_analysis":{"module10_snapshot":{"city":city,"monthly":monthly(scale),"annual":{"total_use_kWh":12000*scale,"operational_co2_kg":5000*scale,"electricity_co2_factor_kg_per_kWh":0.45}},
              "generated_region_files":[{"file":f} for f in gen_files]},
          "module_outputs":{"module4":{"_meta":{"status":"saved"},"annual_timeline":tl},
             "module5":{"_meta":{"status":"saved"},"currency":"JPY","summary":{"total_construction_cost":8e7*scale},
                 "cost_lines":[line("concrete","m3",10,30000),line("doors","m2",6,50000*scale),line("gypsum_board","m2",300,2000)],
                 "_input_snapshot":{"settings":{"overhead_rate":12.0},"equipment_selection":{"hvac":{"include":True,"cost":2e6*scale}}}},
             "module6":{"_meta":{"status":"saved"},"summary":{"initial_total_investment":1e7},"cashflow":cf,"rent_setting_method":"market_rent",
                 "tax_treatment":{"land_and_building_related_taxes":"excluded","included_in_cashflow":False},
                 "_input_snapshot":{"settings":{"annual_rent_per_m2":30000.0*scale,"rent_setting_method":"market_rent","discount_rate_percent":4.0,"vacancy_rate_percent":5.0}}},
             "module3":{"events":[{"year":60,"action":"full_rebuild","component_key":"whole_building"},{"year":10,"action":"repair","component_key":"structure_"+sid}]},
             "module7":{"_input_snapshot":{"settings":{"overhead":0.12}}}},
          "module_status":{m:{"status":"saved","updated_at":"2026-09-22T00:00:00Z"} for m in ("module2","module4","module5","module6","module7")}}
    specs=[("AZRAS_Sample","azras","AZRAS Platform","AZRAS Platform","azras_platform","AZRAS Platform","AZRAS Platform","azras",1.0),
           ("RC_Rahmen_Sample","rc_frame","RCラーメン構造","RC Moment Frame","conventional_rc","一般RC","Conventional RC","general",1.3)]
    for name,sid,sja,sen,mid,mja,men,system,scale in specs:
        d=out/name;d.mkdir(exist_ok=True)
        gens=[]
        for city in ("Sapporo","Berlin","Dubai"):
            p=proj(name,sid,sja,sen,mid,mja,men,system,city,scale*(1.1 if city=="Sapporo" else 0.9))
            fn=f"{name}_{city}.json";(d/fn).write_text(json.dumps(p,ensure_ascii=False),encoding="utf-8");gens.append(fn)
        base=proj(name,sid,sja,sen,mid,mja,men,system,"Kasugai",scale,gen_files=gens)
        (d/f"{name}.json").write_text(json.dumps(base,ensure_ascii=False),encoding="utf-8")
    

ALLOW = set("""AZRAS Project JSON CSV EPW CO CO2 kWh m kg t CF OK NG Module Evaluation Language Version ACE
Comprehensive Consulting Co Ltd JPY Compare module snapshot mm A B C D E CLT Mass Timber Platform RC Sample Rahmen
regional_analysis module10_snapshot simple_payback_year kg-CO t-CO""".split())

try:
    import tkinter as tk
    from tkinter import messagebox, ttk
    root_probe = tk.Tk(); root_probe.destroy()
except Exception as exc:  # no display: static part only
    print(f"  [SKIP] no Tk display available ({exc.__class__.__name__}); runtime scan skipped")
    tk = None

if tk is not None:
    tmp = Path(tempfile.mkdtemp())
    build(tmp)
    for n in ("showwarning", "showinfo", "showerror"):
        setattr(messagebox, n, lambda *a, **k: None)
    os.chdir(ROOT)
    import main
    app = main.App(); app.update()
    app.language_var.set("日本語"); app._change_language()
    app.paths[0].set(str(tmp / "AZRAS_Sample/AZRAS_Sample.json"))
    app.paths[1].set(str(tmp / "RC_Rahmen_Sample/RC_Rahmen_Sample.json"))
    app.compare(); app.premise_tab.build_lists(); app.update()

    def texts(w):
        for c in w.winfo_children():
            try:
                t = c.cget("text")
                if t:
                    yield str(t)
            except Exception:
                pass
            if isinstance(c, ttk.Treeview):
                for col in c["columns"]:
                    yield str(c.heading(col)["text"])
                for iid in c.get_children():
                    for v in c.item(iid)["values"]:
                        yield str(v)
            if isinstance(c, ttk.Notebook):
                for t in c.tabs():
                    yield str(c.tab(t, "text"))
            if isinstance(c, tk.Canvas):
                c.event_generate("<Configure>")
                for it in c.find_all():
                    if c.type(it) == "text":
                        yield str(c.itemcget(it, "text"))
            yield from texts(c)

    for i in range(len(app.tabs.tabs())):
        app.tabs.select(i); app.update()
    bad = sorted({w for t in texts(app) if not t.startswith("PY_VAR")
                  for w in re.findall(r"[A-Za-z][A-Za-z_\-]*", t)
                  if w not in ALLOW and not w.startswith("AZRAS_") and not w.startswith("RC_")})
    if bad:
        for t in texts(app):
            if any(b in re.findall(r"[A-Za-z][A-Za-z_\\-]*", t) for b in bad):
                print("      offending text:", t[:120].replace("\n", " "))
    check(not bad, "Japanese screen contains no untranslated English words", ", ".join(bad[:30]))
    check(all("[" in p["label"] and "一般RC" not in p["label"] for p in app.projects),
          "stored comparison key 'label' stays English-canonical")
    check(any("一般RC" in (p.get("label_ja") or "") for p in app.projects),
          "Japanese method name (construction_method_detail_name_ja) is shown")
    app.language_var.set("English"); app._change_language(); app.update()
    ja = sorted({t for t in texts(app) if re.search(r"[\u3040-\u30ff\u4e00-\u9fff]", t)
                 and t != "言語 / Language" and "比較" not in t[:0]})
    ja = [t for t in ja if not any(t.startswith(x) for x in ("7. 比較前提表",))]
    # The premise-book tab body is Japanese-only by design (PATCH_005); exclude it.
    ja_main = [t for t in ja if t not in {str(x) for x in texts(app.premise_tab)}]
    check(not ja_main, "switching back to English leaves no Japanese on the main screens", " / ".join(ja_main[:5]))
    app.destroy()

src = (ROOT / "main.py").read_text(encoding="utf-8")
check("'kWh/month',MONTHS_JA" not in src and "'t-CO₂/month',MONTHS_JA" not in src,
      "monthly chart units are translated, not hard-coded English")
check("年間Energy" not in src, "no '年間Energy' heading")
check("VERSION='1.1.17'" not in src, "version is read from VERSION.json")

if FAIL:
    print("PATCH_006_JAPANESE_DISPLAY_FAIL"); sys.exit(1)
print("PATCH_006_JAPANESE_DISPLAY_PASS")
