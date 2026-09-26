
from __future__ import annotations
def f(v,d=0.0):
    try:return float(v)
    except:return d
# PATCH_007: where each lifecycle component's new cost comes from.
#
# Until now every component was priced as (Module 5 total construction cost x a
# fixed share).  That makes the replacement cost of an IDENTICAL air conditioner,
# window or refrigerator depend on how expensive the building's STRUCTURE is:
# on the Kasugai sample set the RC air-conditioner replacement came out about
# 1.85x the 2x6 one, and the structural cost difference was multiplied into
# every equipment and finish renewal for 200 years.  A construction-method
# comparison cannot be read on that basis.
#
# Components are now priced from the Module 5 breakdown that actually contains
# them.  The mapping lives in the assumptions JSON (component_cost_sources) so it
# can be reviewed and edited; this dict is only the fallback when that key is
# absent.  Order of precedence for every component:
#   1. settings["component_cost_overrides"][key]    - an explicit human value
#   2. Module 5 priced lines / equipment packages     - the real breakdown
#   3. total construction cost x share               - legacy, flagged
DEFAULT_COMPONENT_COST_SOURCES={
    "whole_building":{"source":"total"},
    "structure":{"source":"lines","cost_item_keys":[
        "concrete","reinforcing_steel","formwork","dimension_lumber","structural_plywood","clt",
        "structural_steel","phc_pile","blinding_concrete","excavation","backfill","imported_fill",
        "soil_disposal","ground_preparation"]},
    "windows":{"source":"lines","cost_item_keys":["glass","tempered_glass","doors","shutter","louver"]},
    "roof":{"source":"lines","cost_item_keys":["roofing","parapet_coping","rainwater_gutter"]},
    "infill_exterior":{"source":"lines","cost_item_keys":["external_finish","external_finish_rc","external_finish_timber"]},
    "infill_layout":{"source":"lines","cost_item_keys":["interior_finish","gypsum_board","ceiling_lgs","oa_floor"]},
    "insulation":{"source":"lines","cost_item_keys":[
        "phenolic_foam","xps","roof_glass_wool","ceiling_glass_wool","ceiling_insulation_area","vapor_barrier"]},
    "equipment_hvac":{"source":"package","package_key":"hvac","split_with":["equipment_ventilation"]},
    "equipment_ventilation":{"source":"package","package_key":"hvac","split_with":["equipment_hvac"]},
    "equipment_lighting":{"source":"package","package_key":"electrical","split_with":["equipment_outlets"]},
    "equipment_outlets":{"source":"package","package_key":"electrical","split_with":["equipment_lighting"]},
    "all_infill":{"source":"non_structural","groups":[
        "windows","roof","infill_exterior","infill_layout","insulation"]},
}
STRUCTURE_COMPONENT_KEYS={"structure_rc_core","structure_rc_frame","structure_rc_wall",
                          "structure_steel","structure_timber","structure_clt"}


def _module5_breakdown(m5):
    """PATCH_007: priced direct amounts per cost item and per included package,
    and the ratio that brings a direct amount to the same basis as Module 5's
    total construction cost (overhead, contingency, design and tax included).
    The legacy share method was on that total basis, so mapped components use it
    too and the lifecycle totals stay on one basis."""
    lines={}
    for L in (m5.get("cost_lines") or []):
        if not isinstance(L,dict):
            continue
        k=str(L.get("cost_item_key") or "")
        if k:
            lines[k]=lines.get(k,0.0)+f(L.get("line_total_after_conditions"))
    packages={}
    for P in (m5.get("equipment_packages") or []):
        if isinstance(P,dict) and P.get("include",True) and f(P.get("cost"))>0:
            packages[str(P.get("package_key") or "")]=f(P.get("cost"))
    s=m5.get("summary") or {}
    base=f(s.get("direct_construction_cost"))+f(s.get("additional_equipment_cost"))
    total=f(s.get("total_construction_cost"))
    markup=(total/base) if base>0 else 1.0
    return lines,packages,markup


def component_new_cost(component_key,m5,initial,db,settings,_breakdown=None):
    """PATCH_007: (new cost, basis label, legacy share cost) for one component."""
    shares=db.get("component_shares") or {}
    legacy=initial*f(shares.get(component_key,.02))
    overrides=(settings or {}).get("component_cost_overrides") or {}
    if component_key in overrides and f(overrides.get(component_key),-1.0)>=0:
        return f(overrides[component_key]),"human_override",legacy
    sources=db.get("component_cost_sources") or DEFAULT_COMPONENT_COST_SOURCES
    rule=sources.get("structure" if component_key in STRUCTURE_COMPONENT_KEYS else component_key)
    if not isinstance(rule,dict):
        return legacy,"legacy_share_of_total_no_source",legacy
    lines,packages,markup=_breakdown or _module5_breakdown(m5)
    kind=rule.get("source")
    if kind=="total":
        return initial,"module5_total_construction_cost",legacy
    if kind=="lines":
        direct=sum(lines.get(k,0.0) for k in rule.get("cost_item_keys") or [])
        if direct>0:
            return direct*markup,"module5_cost_lines",legacy
        return legacy,"legacy_share_of_total_no_priced_lines",legacy
    if kind=="package":
        pkg=packages.get(str(rule.get("package_key") or ""),0.0)
        if pkg>0:
            # A package that covers several lifecycle components is divided in
            # the ratio of their shares.  The package amount itself is the same
            # for identical equipment whatever the structure, so this split is
            # method-neutral.
            mine=f(shares.get(component_key,.02))
            partners=sum(f(shares.get(x,.02)) for x in rule.get("split_with") or [])
            frac=mine/(mine+partners) if (mine+partners)>0 else 1.0
            return pkg*frac*markup,"module5_equipment_package",legacy
        return legacy,"legacy_share_of_total_no_priced_package",legacy
    if kind=="non_structural":
        direct=0.0
        for g in rule.get("groups") or []:
            gr=sources.get(g) or {}
            direct+=sum(lines.get(k,0.0) for k in gr.get("cost_item_keys") or [])
        direct+=sum(packages.values())
        if direct>0:
            return direct*markup,"module5_non_structural_lines_and_packages",legacy
        return legacy,"legacy_share_of_total_no_priced_lines",legacy
    return legacy,"legacy_share_of_total_unknown_source",legacy


_REFERENCE_EXCLUDED=STRUCTURE_COMPONENT_KEYS|{"whole_building","all_infill"}
# PATCH_007: the components that are the SAME for the same plan whatever the
# structure.  Only these may define the method-neutral reference: roof area,
# exterior finish and insulation legitimately differ between construction
# methods (an RC frame carries external insulation and a larger roof, for
# example), so letting them into the reference would carry a method difference
# into every fallback.
METHOD_INVARIANT_REFERENCE_COMPONENTS={
    "equipment_hvac","equipment_ventilation","equipment_lighting","equipment_outlets",
    "windows","infill_layout",
}


def resolve_component_costs(m5,initial,db,settings):
    """PATCH_007: new cost of every lifecycle component, resolved once per Project.

    Returns ({component_key: (cost, basis, legacy_share_cost)}, reference) where
    ``reference`` is the method-neutral non-structural reference (see below).

    Fallback for a non-structural component with no Module 5 source
    ----------------------------------------------------------------
    The legacy rule (total construction cost x share) makes an appliance or a
    finish more expensive simply because the structure is.  Instead the share is
    applied to a METHOD-NEUTRAL reference derived from the Project's own
    method-invariant components that ARE priced from Module 5
    (METHOD_INVARIANT_REFERENCE_COMPONENTS: equipment, windows, interior layout):

        reference = sum(their priced costs) / sum(their shares)

    Those components are the same for the same plan whatever the structure, so
    the reference - and every fallback derived from it - does not move with the
    structural cost.
    Only when no non-structural component is priced at all does the legacy rule
    remain, and it is then flagged.  Structural components and whole_building
    are never re-based: their difference between methods is real.

    all_infill is the sum of the resolved non-structural components plus the
    equipment packages that no component already carries (plumbing, kitchen,
    bathroom, other), so nothing is counted twice and a fallback component is
    still included.
    """
    shares=db.get("component_shares") or {}
    sources=db.get("component_cost_sources") or DEFAULT_COMPONENT_COST_SOURCES
    bd=_module5_breakdown(m5)
    legacy_mode=str((settings or {}).get("component_cost_method") or "")=="legacy_total_share"
    out={}
    for key in shares:
        if key=="all_infill":
            continue
        if legacy_mode:
            leg=initial*f(shares.get(key,.02))
            out[key]=(leg,"legacy_total_share_selected",leg)
        else:
            out[key]=component_new_cost(key,m5,initial,db,settings,bd)
    reference=None
    if not legacy_mode:
        priced=[k for k,(c,b,_l) in out.items()
                if k in METHOD_INVARIANT_REFERENCE_COMPONENTS and str(b).startswith("module5_")]
        ssum=sum(f(shares.get(k)) for k in priced)
        csum=sum(out[k][0] for k in priced)
        if ssum>0 and csum>0:
            reference=csum/ssum
            for k,(c,b,leg) in list(out.items()):
                if k in _REFERENCE_EXCLUDED:
                    continue
                if str(b).startswith("legacy_share"):
                    out[k]=(f(shares.get(k,.02))*reference,"method_neutral_share_of_nonstructural_reference",leg)
    if "all_infill" in shares:
        leg=initial*f(shares.get("all_infill",.02))
        overrides=(settings or {}).get("component_cost_overrides") or {}
        if "all_infill" in overrides and f(overrides.get("all_infill"),-1.0)>=0:
            out["all_infill"]=(f(overrides["all_infill"]),"human_override",leg)
        elif legacy_mode:
            out["all_infill"]=(leg,"legacy_total_share_selected",leg)
        else:
            lines,packages,markup=bd
            covered={str((r or {}).get("package_key") or "") for r in sources.values()
                     if isinstance(r,dict) and r.get("source")=="package"}
            comp=sum(out[k][0] for k in out if k not in _REFERENCE_EXCLUDED)
            comp+=sum(v for pk,v in packages.items() if pk not in covered)*markup
            if comp>0:
                out["all_infill"]=(comp,"sum_of_resolved_non_structural_components",leg)
            else:
                out["all_infill"]=(leg,"legacy_share_of_total_no_priced_lines",leg)
    return out,reference


def calculate(project,db,settings):
    m3=project["module_outputs"].get("module3");m5=project["module_outputs"].get("module5")
    if not m3 or not m5: raise ValueError("Module 3 and Module 5 outputs are required.")
    initial=f(m5["summary"]["total_construction_cost"]);cur=m5.get("currency","JPY")
    period=int(f(m3.get("period_years"),200));gfa=max(f(project.get("common",{}).get("scale_gfa_m2")),1)
    fac=db["factors"]|settings;lines=[]
    _bd=_module5_breakdown(m5)
    _resolved,_reference=resolve_component_costs(m5,initial,db,settings)
    basis_audit={}
    for e in m3.get("events",[]):
        a=e.get("action");r=db["action_rates"].get(a)
        if not r:continue
        _ck=str(e.get("component_key") or "")
        if _ck in _resolved:
            comp,_basis,_legacy=_resolved[_ck]
        else:
            comp,_basis,_legacy=component_new_cost(_ck,m5,initial,db,settings,_bd)
        basis_audit.setdefault(_ck,{"component":e.get("component",""),"basis":_basis,
                                    "component_new_cost":comp,"legacy_share_cost":_legacy})

        # retain_skeleton records the decision to keep the existing skeleton/core.
        # It is not demolition, replacement, or repair work by itself.
        if a=="retain_skeleton":
            lines.append({
                "event_id":e.get("event_id",""),"year":int(f(e.get("year"))),
                "action":a,"component_key":e.get("component_key",""),
                "component":e.get("component",""),"component_new_cost":0.0,
                "work_cost":0.0,"demolition_cost":0.0,"waste_cost":0.0,
                "temporary_cost":0.0,"reuse_credit":0.0,"recycling_credit":0.0,
                "overhead":0.0,"contingency":0.0,"tax":0.0,"event_subtotal_before_tax":0.0,"event_total":0.0,"event_total_with_tax":0.0,"tax_treatment":"separate_not_in_lifecycle_work_cost",
                "cost_event_semantics":"retain_only_no_construction_cost"
            })
            continue

        scope=1 if e.get("scope")=="all" else max(f(e.get("removed_fraction")),.1)
        work=comp*f(r["work"])*scope
        demo=comp*f(r["demo"])*scope
        waste=demo*f(fac["waste"])
        temp=(work+demo)*f(fac["temporary"])

        # Credits cannot be claimed twice on the same component share:
        # recycling applies only to the non-reused remainder.
        reuse_fraction=max(min(f(e.get("reused_fraction")),1.0),0.0)
        recycle_fraction=max(min(f(e.get("recycled_fraction")),1.0),0.0)
        reuse=comp*reuse_fraction*f(fac["reuse_credit"])
        recyclable_remainder=max(1.0-reuse_fraction,0.0)
        recycle=comp*recyclable_remainder*recycle_fraction*f(fac["recycling_credit"])

        base=max(work+demo+waste+temp-reuse-recycle,0)
        oh=base*f(fac["overhead"])
        cont=(base+oh)*f(fac["contingency"])
        sub=base+oh+cont
        tax=sub*f(fac["tax"])
        total_with_tax=sub+tax
        lines.append({
            "event_id":e.get("event_id",""),"year":int(f(e.get("year"))),
            "action":a,"component_key":e.get("component_key",""),
            "component":e.get("component",""),"component_new_cost":comp,
            "work_cost":work,"demolition_cost":demo,"waste_cost":waste,
            "temporary_cost":temp,"reuse_credit":reuse,
            "recycling_credit":recycle,"overhead":oh,"contingency":cont,
            "tax":tax,
            "event_subtotal_before_tax":sub,
            "event_total":sub,
            "event_total_with_tax":total_with_tax,
            "tax_treatment":"separate_not_in_lifecycle_work_cost",
            "cost_event_semantics":"renewal_or_demolition_work",
            "component_cost_basis":_basis,
        })
    total_before_tax=sum(x["event_total"] for x in lines)
    total_tax=sum(x.get("tax",0.0) for x in lines)
    total_with_tax=total_before_tax+total_tax
    summary={
        "total_lifecycle_work_cost":total_before_tax,
        "total_lifecycle_work_cost_before_tax":total_before_tax,
        "total_lifecycle_tax":total_tax,
        "total_lifecycle_cost_with_tax":total_with_tax,
        "tax_treatment":"tax_reported_separately_not_in_evaluation_cashflow",
        "average_annual_cost":total_before_tax/period,
        "average_annual_tax":total_tax/period,
        "cost_per_m2_year":total_before_tax/(gfa*period),
        "event_count":len(lines),
        "total_demolition_cost":sum(x["demolition_cost"] for x in lines),
        "total_waste_cost":sum(x["waste_cost"] for x in lines),
        "total_credits":sum(x["reuse_credit"]+x["recycling_credit"] for x in lines),
        # PATCH_007: which basis priced each component.  Anything starting with
        # "legacy_share" still scales with the total construction cost and is
        # therefore NOT method-neutral; it is listed so it can be seen and, in a
        # comparison, overridden with a common value.
        "component_cost_basis_audit":basis_audit,
        "legacy_share_components":sorted(k for k,v in basis_audit.items() if str(v.get("basis","")).startswith("legacy_share")),
        "method_neutral_fallback_components":sorted(k for k,v in basis_audit.items()
                                                    if v.get("basis")=="method_neutral_share_of_nonstructural_reference"),
        "nonstructural_reference_cost":_reference,
        "component_cost_method":("legacy_total_share_selected"
                                 if str((settings or {}).get("component_cost_method") or "")=="legacy_total_share"
                                 else "PATCH_007_module5_breakdown_with_method_neutral_fallback"),
    }
    annual=[]
    for y in range(1,period+1):
        c=sum(x["event_total"] for x in lines if x["year"]==y)
        t=sum(x.get("tax",0.0) for x in lines if x["year"]==y)
        annual.append({"year":y,"annual_cost":c,"annual_cost_before_tax":c,
                       "annual_tax":t,"annual_cost_with_tax":c+t})
    cum=0
    for r in annual: cum+=r["annual_cost"];r["cumulative_cost"]=cum
    return {"version":"9.6","module":"module7","currency":cur,"period_years":period,"event_costs":lines,"annual_cost_timeline":annual,"summary":summary,"settings":settings}
