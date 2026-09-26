
from __future__ import annotations
from core.project_coordinator import require_current_module_output
def f(v,d=0.0):
    try:return float(v)
    except:return d
def calculate(project,db,settings):
    m3=require_current_module_output(project,"module3","Module 3");m5=require_current_module_output(project,"module5","Module 5")
    initial=f(m5["summary"]["total_construction_cost"]);cur=m5.get("currency","JPY")
    m5_unpriced=list(m5.get("unpriced_cost_lines") or [])
    m5_partial=(bool(m5.get("construction_cost_is_partial")) or (bool(m5.get("priced_total_excludes_unpriced_items")) and bool(m5_unpriced)))
    period=int(f(m3.get("period_years"),200));gfa=max(f(project.get("common",{}).get("scale_gfa_m2")),1)
    fac=db["factors"]|settings;lines=[]
    for e in m3.get("events",[]):
        a=e.get("action");r=db["action_rates"].get(a)
        if not r:continue
        share=f(db["component_shares"].get(e.get("component_key"),.02))
        comp=initial*share;scope=1 if e.get("scope")=="all" else max(f(e.get("removed_fraction")),.1)
        work=comp*f(r["work"])*scope;demo=comp*f(r["demo"])*scope;waste=demo*f(fac["waste"]);temp=(work+demo)*f(fac["temporary"])
        reuse=comp*f(e.get("reused_fraction"))*f(fac["reuse_credit"]);recycle=comp*f(e.get("recycled_fraction"))*f(fac["recycling_credit"])
        base=max(work+demo+waste+temp-reuse-recycle,0);oh=base*f(fac["overhead"]);cont=(base+oh)*f(fac["contingency"]);sub=base+oh+cont;tax=sub*f(fac["tax"]);total=sub+tax
        lines.append({"event_id":e.get("event_id",""),"year":int(f(e.get("year"))),"action":a,"component_key":e.get("component_key",""),"component":e.get("component",""),"component_new_cost":comp,"work_cost":work,"demolition_cost":demo,"waste_cost":waste,"temporary_cost":temp,"reuse_credit":reuse,"recycling_credit":recycle,"overhead":oh,"contingency":cont,"tax":tax,"event_total":total})
    total=sum(x["event_total"] for x in lines)
    summary={"total_lifecycle_work_cost":total,"average_annual_cost":total/period,"cost_per_m2_year":total/(gfa*period),"event_count":len(lines),"total_demolition_cost":sum(x["demolition_cost"] for x in lines),"total_waste_cost":sum(x["waste_cost"] for x in lines),"total_credits":sum(x["reuse_credit"]+x["recycling_credit"] for x in lines)}
    annual=[]
    for y in range(1,period+1):
        c=sum(x["event_total"] for x in lines if x["year"]==y)
        annual.append({"year":y,"annual_cost":c})
    cum=0
    for r in annual: cum+=r["annual_cost"];r["cumulative_cost"]=cum
    return {"version":"9.6","module":"module7","currency":cur,"period_years":period,"event_costs":lines,"annual_cost_timeline":annual,"summary":summary,"settings":settings,
            "construction_cost_input_status":{"source":"module5","is_partial":m5_partial,"priced_total_excludes_unpriced_items":m5_partial,"unpriced_item_count":len(m5_unpriced),"quantity_cost_gap_count":int((m5.get("quantity_cost_coverage_audit") or {}).get("monetary_gap_count") or 0)},
            "status":"provisional_planning_comparison_incomplete_construction_cost" if m5_partial else "provisional_planning_comparison"}
