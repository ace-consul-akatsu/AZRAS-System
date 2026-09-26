
from __future__ import annotations
from typing import Any
import math
import re

TAKEOFF_MAP = {
    "コンクリート合計":"concrete",
    "コンクリート":"concrete",
    "鉄筋":"reinforcing_steel",
    "構造用鉄骨":"structural_steel",
    "2×6・一般構造木材":"dimension_lumber",
    "2×6・一般木材":"dimension_lumber",
    "2×6構造木材量（暫定一般仕様）":"dimension_lumber",
    "2×6 structural timber quantity":"dimension_lumber",
    "AZRAS timber infill (provisional general specification)":"dimension_lumber",
    "2×6構造木材量（部位別暫定合計）":"dimension_lumber",
    "AZRAS timber framing total (method-specific provisional total)":"dimension_lumber",
    "RC internal partition LGS steel total (provisional general specification)":"structural_steel",
    "CLT・Mass Timber":"clt",
    "フェノールフォーム":"phenolic_foam",
    "RC外壁フェノールフォーム":"phenolic_foam",
    "木造外壁フェノールフォーム":"phenolic_foam",
    "屋根断熱材":"phenolic_foam",
    "XPS":"xps",
    "基礎下断熱材":"xps",
    "構造用合板12mm":"structural_plywood",
    "外壁窓ガラス":"glass",
    "Exterior window glazing":"glass",
    "ガラス":"glass",
    "石膏ボード13mm":"gypsum_board",
    "石膏ボード":"gypsum_board",
    "屋根面積":"roofing",
    "屋根":"roofing",
    "ドア面積":"doors",
    "ドア":"doors",
    "外部ドア":"doors",
    "Exterior doors":"doors",
    "内装仕上面積":"interior_finish",
    "外装仕上面積":"external_finish",
    "型枠":"formwork",
    "型枠工事":"formwork",
    "型枠面積":"formwork"
}

def _f(v: Any, default: float=0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default

def _construction_method(project: dict[str, Any]) -> str:
    common=project.get("common",{}) or {}
    cfg=common.get("detailed_configuration",{}) or {}
    if cfg.get("building_system")=="azras" or common.get("construction_method_id")=="azras":
        return "azras"
    method_id=str(common.get("construction_method_id") or "").lower()
    detail_id=str(common.get("construction_method_detail_id") or "").lower()
    general=cfg.get("general",{}) or {}
    structure=str(general.get("structure") or "").lower()
    method=str(general.get("method") or "").lower()
    joined=" ".join((method_id,detail_id,structure,method))
    if "rc_frame" in joined or "conventional_rc" in joined:
        return "rc_frame"
    if "wood_frame" in joined or "2x6" in joined or "2×6" in joined:
        return "wood_frame"
    return method_id or detail_id or "general"

def _method_allowed_keys(method: str) -> set[str]:
    common={
        "glass","gypsum_board","roofing","doors","interior_finish",
        "phenolic_foam","xps",
        "external_finish_rc","external_finish_timber",
        # PATCH 051: foundation preparation is a comparable scope for all
        # three construction methods, not RC-frame-only.
        "excavation","backfill","imported_fill","soil_disposal","blinding_concrete","ground_preparation"
    }
    if method=="wood_frame":
        # Timber superstructure + RC foundation.
        return common|{"concrete","reinforcing_steel","formwork","dimension_lumber","structural_plywood"}
    if method=="azras":
        # Long-life RC core + renewable timber infill/outfill.
        return common|{"concrete","reinforcing_steel","formwork","dimension_lumber","structural_plywood"}
    if method=="rc_frame":
        # Conventional RC roof/walls/slabs do not require structural plywood
        # as a permanent building material in this comparison model.
        return common|{"concrete","reinforcing_steel","formwork","structural_steel",
                       "excavation","backfill","imported_fill","soil_disposal","blinding_concrete","ground_preparation"}
    return common|{"concrete","reinforcing_steel","formwork","dimension_lumber","structural_steel","clt"}

def _concrete_installation_complexity(method: str) -> dict[str, float]:
    """PATCH 040: method-specific concrete placement complexity.

    Material price is never reduced. Only placement labor/equipment are
    adjusted for geometric/operational complexity.
    """
    return {
        "wood_frame":{"labor":0.85,"equipment":0.90,
                      "basis_ja":"2×6は主に単純な基礎コンクリート施工"},
        "azras":{"labor":0.70,"equipment":0.75,
                 "basis_ja":"AZRASは連続壁＋ベタ基礎主体で柱梁接合・梁型等の凹凸が少ない"},
        "rc_frame":{"labor":1.00,"equipment":1.00,
                    "basis_ja":"RCラーメンを柱・梁・床スラブを含む基準施工難易度1.00とする"},
    }.get(method,{"labor":1.00,"equipment":1.00,"basis_ja":"一般工法基準"})


def _azras_geometry_formwork_m2(profile: dict[str, Any]) -> tuple[float, str] | None:
    """Estimate AZRAS formwork from actual simple geometry when possible.

    Walls: two faces of RC wall gross area derived from RC wall volume / thickness.
    Foundation slab: exposed perimeter edge only.
    This is preferable to an undifferentiated concrete-volume multiplier.
    """
    construction=profile.get("construction",{}) or {}
    geometry=profile.get("geometry",{}) or {}
    surfaces=profile.get("surfaces",[]) or []
    cvol=construction.get("concrete_volume_m3",{}) or {}
    rc_wall_vol=_f(cvol.get("rc_walls"))
    rc_t_mm=_f(construction.get("rc_wall_thickness_mm"))
    slab_t_mm=_f(construction.get("slab_thickness_mm"))
    if rc_wall_vol<=0 or rc_t_mm<=0:
        return None
    wall_one_face=rc_wall_vol/(rc_t_mm/1000.0)
    wall_form=wall_one_face*2.0
    perimeter=sum(_f(x.get("length_m")) for x in surfaces)
    if perimeter<=0:
        # rectangular fallback if dimensions are not explicitly available
        footprint=_f(geometry.get("footprint_m2"))
        perimeter=4.0*math.sqrt(footprint) if footprint>0 else 0.0
    slab_edge=perimeter*(slab_t_mm/1000.0) if perimeter>0 and slab_t_mm>0 else 0.0
    total=wall_form+slab_edge
    return total, (
        f"AZRAS単純形状型枠: RC壁 {rc_wall_vol:.3f}m3 ÷ {rc_t_mm:g}mm × 両面"
        f" = {wall_form:.3f}m2 + 基礎端部 周長{perimeter:.3f}m × {slab_t_mm:g}mm"
        f" = {slab_edge:.3f}m2"
    )


def _formwork_factor(method: str) -> float:
    # Planning fallback only, used when Module 1 does not provide formwork area.
    # m2 of formwork per m3 of concrete. Kept explicit in quantity provenance.
    return {
        "wood_frame":2.0,   # mainly foundation/grade beams
        "azras":4.0,        # RC core/walls + foundation
        "rc_frame":5.0,     # columns/beams/slabs + foundation
    }.get(method,4.0)



def _row_downstream_eligible(row: dict[str,Any]) -> tuple[bool,str]:
    downstream=str(row.get("downstream_use") or "").strip().lower()
    display=str(row.get("quantity_display_state") or "").strip().lower()
    adoption=str(row.get("quantity_adoption_class") or "").strip().lower()
    # PATCH_201: audit/superseded ownership always wins over compatibility
    # bridges so a historical provisional row cannot re-enter cost/LCA.
    if downstream.startswith("audit") or display=="audit_only_neutral" or adoption=="audit_only" or str(row.get("aggregation_role") or "").strip().lower()=="audit_only":
        return False,"audit_only_quantity_owner"
    try:
        q=float(row.get("accepted_quantity", row.get("quantity")))
        numeric=math.isfinite(q) and q >= 0.0
    except Exception:
        numeric=False

    # PATCH 199: yellow is an adopted planning quantity.  This explicit visual /
    # adoption state overrides stale legacy blocked flags in old Project JSONs.
    if numeric and (display=="assumed_yellow" or adoption=="assumed"):
        return True,"yellow_provisional_quantity_adopted_patch199"

    # PATCH 200: compatibility for old Project JSONs created before Planning 532.
    # A clearly-labelled provisional-general-spec numeric calculation is a yellow
    # planning quantity by policy, even if stale saved flags still say unknown/red.
    status=str(row.get("evidence_status") or row.get("status") or "").strip().lower()
    blob=" ".join(str(row.get(k) or "") for k in ("item","source_mode","formula","evidence")).lower()
    legacy_rational=(
        numeric
        and any(tok in blob for tok in ("provisional general specification","暫定一般仕様","provisional value"))
        and status not in {"conflict","conflicting","unreadable"}
    )
    if legacy_rational:
        return True,"legacy_rational_provisional_adopted_patch200"

    if display in {"unknown_red","spec_only_neutral","audit_only_neutral"} or adoption in {"audit_only","spec_only","unknown","unresolved","blocked"}:
        return False,"non_adoptable_quantity_certainty"
    if downstream in {"blocked_until_resolved","hold_for_human_review","audit_only","audit_only_unresolved","scope_evidence_only","quantity_basis_only"}:
        return False,f"downstream_use:{downstream}"
    if "downstream_quantity_eligible" in row:
        return bool(row.get("downstream_quantity_eligible")),("explicit_gate" if row.get("downstream_quantity_eligible") else "explicit_block")
    return True,"legacy_compatible"


def _concrete_component(row: dict[str,Any]) -> str:
    item=str(row.get("item") or "").strip().lower().replace("　"," ")
    formula=str(row.get("formula") or row.get("canonical_formula") or "").strip().lower()
    blob=" ".join((item,formula))
    if any(tok in blob for tok in ("foundation / slab-on-grade concrete","slab_foundation","ベタ基礎コンクリート","基礎・土間コンクリート","土間コンクリート","mat foundation")):
        return "foundation_slab"
    if any(tok in blob for tok in ("azras外周rc壁","external rc wall","perimeter rc wall","gable-end rc wall")):
        return "external_rc_wall"
    if any(tok in blob for tok in ("azras internal rc wall","internal rc wall","内部rc壁")):
        return "internal_rc_wall"
    if "rc wall concrete" in blob or "rc壁コンクリート" in blob:
        return "rc_wall"
    if "column" in blob or "柱コンクリート" in blob: return "columns"
    if "beam" in blob or "梁コンクリート" in blob: return "beams"
    if any(tok in blob for tok in ("upper_slabs","上階・屋根スラブ","upper slab","roof slab")): return "upper_slabs"
    if any(tok in blob for tok in ("underground_foundations","独立基礎・地中梁","isolated footing","grade beam")): return "underground_foundations"
    return "other:"+re.sub(r"\s+"," ",item)


def _concrete_priority(row: dict[str,Any]) -> tuple[int,float]:
    role=str(row.get("aggregation_role") or "").strip().lower()
    source=str(row.get("source_mode") or "").strip().lower()
    item=str(row.get("item") or "").strip().lower()
    adoption=str(row.get("quantity_adoption_class") or "").strip().lower()
    evidence=str(row.get("evidence_status") or "").strip().lower()
    score=0
    if role=="detail_component": score+=100
    if "current-pdf" in source or "current pdf" in source: score+=45
    if str(row.get("material_key") or "").strip().lower()=="concrete": score+=30
    if adoption=="confirmed": score+=20
    elif adoption=="assumed": score+=5
    if evidence=="confirmed": score+=20
    elif evidence=="estimated": score+=8
    if any(tok in item for tok in ("candidate","before internal-opening","range candidate")): score-=60
    if source=="aggregation" or role=="summary_fallback": score-=80
    return score,_f(row.get("confidence"))


def _canonical_concrete_quantity(module1: dict[str,Any]) -> tuple[float,dict[str,Any],list[dict[str,Any]]]:
    rows=((module1.get("quantity_takeoff") or {}).get("rows") or []) if isinstance(module1,dict) else []
    details=[]; summaries=[]; excluded=[]
    for row in rows:
        if not isinstance(row,dict): continue
        item=str(row.get("item") or "")
        low=item.lower(); unit=str(row.get("unit") or "").strip().lower()
        group=str(row.get("aggregation_group") or "").strip().lower()
        mkey=str(row.get("material_key") or "").strip().lower()
        is_concrete=(group=="concrete" or mkey=="concrete" or (unit in {"m3","m³"} and ("concrete" in low or "コンクリート" in item)))
        if not is_concrete: continue
        eligible,reason=_row_downstream_eligible(row)
        qty=_f(row.get("accepted_quantity",row.get("quantity")))
        if not eligible or qty<=0:
            excluded.append({"item":item,"cost_item_key":"concrete","quantity":qty,"reason":reason if not eligible else "nonpositive_quantity"})
            continue
        role=str(row.get("aggregation_role") or "").strip().lower()
        source=str(row.get("source_mode") or "").strip().lower()
        is_summary=(role=="summary_fallback" or source=="aggregation" or low in {"total concrete","concrete total"} or "コンクリート合計" in item or ("total" in low and "concrete" in low))
        if role=="audit_only":
            excluded.append({"item":item,"cost_item_key":"concrete","quantity":qty,"reason":"aggregation_audit_only"}); continue
        (summaries if is_summary else details).append(row)
    if details:
        winners={}
        for row in details:
            comp=_concrete_component(row); old=winners.get(comp)
            if old is None or _concrete_priority(row)>_concrete_priority(old):
                if old is not None:
                    excluded.append({"item":str(old.get("item") or ""),"cost_item_key":"concrete","quantity":_f(old.get("accepted_quantity",old.get("quantity"))),"reason":f"duplicate_physical_component:{comp}"})
                winners[comp]=row
            else:
                excluded.append({"item":str(row.get("item") or ""),"cost_item_key":"concrete","quantity":_f(row.get("accepted_quantity",row.get("quantity"))),"reason":f"duplicate_physical_component:{comp}"})
        for row in summaries:
            excluded.append({"item":str(row.get("item") or ""),"cost_item_key":"concrete","quantity":_f(row.get("accepted_quantity",row.get("quantity"))),"reason":"summary_fallback_excluded_because_detail_owners_exist"})
        owners=list(winners.values())
        return sum(_f(r.get("accepted_quantity",r.get("quantity"))) for r in owners),{
            "source_type":"canonical_physical_quantity_ownership","source":"Module 1 quantity_takeoff",
            "basis":"Concrete is counted once per physical component; generic-profile/summary duplicates remain audit-only.",
            "source_items":[str(r.get("item") or "") for r in owners],
            "component_owners":{_concrete_component(r):str(r.get("item") or "") for r in owners},
        },excluded
    if summaries:
        best=max(summaries,key=_concrete_priority)
        return _f(best.get("accepted_quantity",best.get("quantity"))),{
            "source_type":"summary_fallback_only","source":"Module 1 quantity_takeoff",
            "basis":f"No eligible detail owner; one summary fallback used ({best.get('item','')}).",
            "source_items":[str(best.get("item") or "")],
        },excluded
    return 0.0,{"source_type":"none","source":"Module 1 quantity_takeoff","basis":"No eligible concrete quantity owner."},excluded


def _tagged_rebar_planning_quantity(module1: dict[str,Any]) -> tuple[float,dict[str,Any]]:
    rows=((module1.get("quantity_takeoff") or {}).get("rows") or []) if isinstance(module1,dict) else []
    candidates=[]
    for row in rows:
        if not isinstance(row,dict): continue
        item=str(row.get("item") or ""); low=item.lower(); unit=str(row.get("unit") or "").strip().lower()
        mkey=str(row.get("material_key") or "").strip().lower()
        if not (mkey=="reinforcing_steel" or "reinforcing steel" in low or "reinforcement" in low or "鉄筋" in item): continue
        qty=_f(row.get("accepted_quantity",row.get("quantity")))
        if unit=="kg": qty/=1000.0
        if qty<=0 or unit not in {"t","ton","tons","tonne","tonnes","kg"}: continue
        eligible,_=_row_downstream_eligible(row)
        if not eligible: continue
        provisional=("provisional general specification" in low or "暫定一般仕様" in item or mkey=="reinforcing_steel")
        spec=row.get("provisional_general_spec") if isinstance(row.get("provisional_general_spec"),dict) else {}
        rate=_f(spec.get("parameter_value")) if str(spec.get("parameter_name") or "")=="rebar_rate_kg_per_m3" else 0.0
        candidates.append((1 if provisional else 0,qty,row,rate))
    if not candidates: return 0.0,{}
    _,qty,row,rate=max(candidates,key=lambda x:(x[0],x[1]))
    return qty,{"source":"Module 1 tagged reinforcement planning row","source_item":str(row.get("item") or ""),"basis":str(row.get("formula") or "Module 1 adopted reinforcement planning quantity"),"rebar_rate_kg_per_m3":rate,"provisional_dependency":bool(rate>0)}

def extract_quantities(project: dict[str, Any], module1: dict[str, Any], settings: dict[str,Any] | None=None) -> tuple[dict[str,float],dict[str,dict[str,Any]],list[dict[str,Any]]]:
    method=_construction_method(project)
    allowed=_method_allowed_keys(method)
    quantities={}
    provenance={}
    excluded=[]

    # PATCH 197/530 bridge: first load legacy exact non-concrete rows; concrete
    # is resolved separately by physical ownership so summaries and detail rows
    # can never be added together.
    for row in module1.get("quantity_takeoff",{}).get("rows",[]):
        item=str(row.get("item", ""))
        key=TAKEOFF_MAP.get(item)
        if key=="reinforcing_steel":
            _spec=row.get("provisional_general_spec") if isinstance(row.get("provisional_general_spec"),dict) else {}
            _rate=_f(_spec.get("parameter_value")) if str(_spec.get("parameter_name") or "")=="rebar_rate_kg_per_m3" else 0.0
            _src=str(row.get("source_mode") or "").lower()
            _human=any(tok in _src for tok in ("human","manual","user-confirmed","user confirmed")) or bool(row.get("human_confirmed"))
            if _rate>0 and not _human:
                key=None  # dependency mass is recomputed from current concrete by fallback below
        if not key or key=="concrete":
            continue
        eligible,reason=_row_downstream_eligible(row)
        if not eligible:
            excluded.append({"item":item,"cost_item_key":key,"quantity":_f(row.get("accepted_quantity",row.get("quantity"))),"reason":reason})
            continue
        qty=_f(row.get("accepted_quantity",row.get("quantity")))
        if qty<=0:
            continue
        if key not in allowed:
            excluded.append({"item":item,"cost_item_key":key,"quantity":qty,"reason":f"{method} の標準工法構成に含めないため除外"})
            continue
        quantities[key]=quantities.get(key,0.0)+qty
        if key not in provenance:
            provenance[key]={"source_type":"drawing_quantity","source":"Module 1 quantity_takeoff","basis":f"図面・数量解析の採用数量（{item}）","source_items":[item],"construction_method":method}
        else:
            provenance[key].setdefault("source_items",[]).append(item)
            provenance[key]["basis"]="図面・数量解析の採用数量合計（"+ "＋".join(provenance[key]["source_items"]) +"）"

    concrete_qty,concrete_prov,concrete_excluded=_canonical_concrete_quantity(module1)
    if concrete_qty>0 and "concrete" in allowed:
        quantities["concrete"]=concrete_qty
        concrete_prov["construction_method"]=method
        provenance["concrete"]=concrete_prov
    excluded.extend(concrete_excluded)

    profile=module1.get("profile",{}) or {}
    drawing_profile=((module1.get("drawing_analysis",{}) or {}).get("profile",{}) or {})

    # PATCH 042: preserve newer drawing-recognized foundation construction.
    drawing_construction=drawing_profile.get("construction",{}) or {}
    if drawing_construction.get("foundation_geometry"):
        profile=dict(profile)
        merged_construction=dict(profile.get("construction",{}) or {})
        for key in (
            "slab_thickness_mm",
            "concrete_volume_m3",
            "foundation_geometry",
            "foundation_quantity_policy",
        ):
            if key in drawing_construction:
                merged_construction[key]=drawing_construction[key]
        profile["construction"]=merged_construction

    geometry=profile.get("geometry",{})
    surfaces=profile.get("surfaces",[])
    construction=profile.get("construction",{})

    def fallback(key,qty,basis):
        if key in allowed and key not in quantities and qty>0:
            quantities[key]=qty
            provenance[key]={
                "source_type":"method_fallback_estimate",
                "source":"Module 5 method profile",
                "basis":basis,
                "construction_method":method
            }

    # PATCH 042: authoritative drawing-derived 2×6 foundation linkage.
    foundation_geometry=construction.get("foundation_geometry",{}) or {}
    if method=="wood_frame" and foundation_geometry.get("status")=="matched_dimensioned_plan":
        fv=foundation_geometry.get("concrete_volume_m3",{}) or {}
        drawing_concrete=_f(fv.get("total"))
        if drawing_concrete>0:
            stale_concrete=quantities.get("concrete")
            quantities["concrete"]=drawing_concrete
            provenance["concrete"]={
                "source_type":"drawing_foundation_geometry",
                "source":"Module 1 drawing_analysis.profile.construction.foundation_geometry",
                "basis":(
                    f"布基礎 {_f(fv.get('strip_foundation')):.4f} m3 + "
                    f"土間 {_f(fv.get('slab_on_ground')):.4f} m3 = "
                    f"{drawing_concrete:.4f} m3"
                ),
                "construction_method":method,
                "replaced_stale_quantity":stale_concrete,
            }

            quantities["reinforcing_steel"]=drawing_concrete*100.0/1000.0
            provenance["reinforcing_steel"]={
                "source_type":"foundation_geometry_planning_allowance",
                "source":"Module 1 recognized 2×6 foundation concrete",
                "basis":f"{drawing_concrete:.4f} m3 × 100 kg/m3 ÷ 1000",
                "construction_method":method,
            }

            fw=_f((foundation_geometry.get("formwork_m2") or {}).get("total"))
            if fw>0:
                quantities["formwork"]=fw
                provenance["formwork"]={
                    "source_type":"drawing_foundation_geometry",
                    "source":"Module 1 foundation_geometry.formwork_m2",
                    "basis":f"布基礎立上り両面型枠 {fw:.3f} m2（底盤側面は自動計上しない）",
                    "construction_method":method,
                }

    # PATCH 051: common foundation earthwork quantities for all three comparison methods.
    # PATCH 048 already covered RC frame. PATCH 051 adds geometry-based 2x6 and AZRAS
    # quantities using the same planning assumptions. Unit prices remain zero until
    # a confirmed current-year composite rate is entered by the user.
    ew=_foundation_earthwork_geometry(profile,method,str((settings or {}).get("excavated_soil_stockpile_mode") or "no_stockpile"))
    if ew:
        q=ew.get("quantities",{}) or {}
        source=str(ew.get("source") or "Module 5 PATCH 051 foundation geometry")
        basis_map=ew.get("quantity_basis",{}) or {}
        for key,qty in (
            ("excavation",_f(q.get("excavation_m3"))),
            ("backfill",_f(q.get("backfill_m3"))),
            ("imported_fill",_f(q.get("imported_backfill_m3"))),
            ("soil_disposal",_f(q.get("soil_disposal_loose_m3"))),
            ("blinding_concrete",_f(q.get("blinding_concrete_m3"))),
            ("ground_preparation",_f(q.get("ground_preparation_crushed_stone_m3"))),
        ):
            if key in allowed and qty>0:
                quantities[key]=qty
                provenance[key]={
                    "source_type":"planning_geometry_assumption",
                    "source":source,
                    "basis":str(basis_map.get(key) or "基礎形状と共通計画仮定による数量"),
                    "construction_method":method,
                    "requires_confirmation":True,
                }

    fallback("roofing",_f(geometry.get("roof_area_m2")),"Module 1屋根面積を屋根・防水工事数量として採用")
    fallback("doors",sum(_f(x.get("door_area_m2")) for x in surfaces),"Module 1各面のドア面積合計")
    gfa=_f(geometry.get("conditioned_floor_area_m2")) or _f(project.get("common",{}).get("scale_gfa_m2"))
    if gfa>0:
        fallback("interior_finish",gfa*2.0,"延床面積×2.0を内装仕上げ面積の計画補完値として使用")
    rc_external_area=_f(construction.get("rc_wall_area_m2"))
    timber_external_area=_f(construction.get("light_wall_area_m2"))
    fallback("external_finish_rc",rc_external_area,
             f"Module 1 RC外壁面積 {rc_external_area:.3f} m2")
    fallback("external_finish_timber",timber_external_area,
             f"Module 1 木造・軽量外壁面積 {timber_external_area:.3f} m2")

    # PATCH 038: insulation-cost linkage safety net.
    # Module 1 normally supplies explicit insulation rows. If an older/partial
    # takeoff omits them, derive quantities from confirmed profile areas and
    # component-specific insulation thicknesses. This keeps Module 5 from
    # silently dropping insulation after Module 1 automatic linkage.
    assemblies=profile.get("assemblies",{}) or {}
    roof_area=_f(geometry.get("roof_area_m2"))
    slab_area=_f(geometry.get("slab_area_m2")) or _f(geometry.get("footprint_m2"))
    rc_ins_mm=_f((assemblies.get("rc_wall") or {}).get("thickness_mm"))
    light_ins_mm=_f((assemblies.get("light_wall") or {}).get("thickness_mm"))
    roof_ins_mm=_f((assemblies.get("roof") or {}).get("thickness_mm"))
    slab_ins_mm=_f((assemblies.get("slab") or {}).get("thickness_mm"))

    # Phenolic foam is accumulated across RC wall, light/timber wall and roof.
    phenolic_components=[]
    if rc_external_area>0 and rc_ins_mm>0:
        phenolic_components.append(("RC外壁",rc_external_area*rc_ins_mm/1000.0,rc_ins_mm))
    if timber_external_area>0 and light_ins_mm>0:
        phenolic_components.append(("木造・2×6外壁",timber_external_area*light_ins_mm/1000.0,light_ins_mm))
    if roof_area>0 and roof_ins_mm>0:
        phenolic_components.append(("屋根",roof_area*roof_ins_mm/1000.0,roof_ins_mm))
    if "phenolic_foam" not in quantities and phenolic_components:
        phenolic_qty=sum(x[1] for x in phenolic_components)
        quantities["phenolic_foam"]=phenolic_qty
        provenance["phenolic_foam"]={
            "source_type":"profile_component_fallback",
            "source":"Module 1 profile.assemblies + component areas",
            "basis":" + ".join(f"{name} {qty:.5f}m3 ({mm:g}mm)" for name,qty,mm in phenolic_components),
            "construction_method":method,
        }

    if "xps" not in quantities and slab_area>0 and slab_ins_mm>0:
        quantities["xps"]=slab_area*slab_ins_mm/1000.0
        provenance["xps"]={
            "source_type":"profile_component_fallback",
            "source":"Module 1 profile.assemblies.slab + slab area",
            "basis":f"基礎・土間下 {slab_area:.3f}m2 × {slab_ins_mm:g}mm ÷ 1000",
            "construction_method":method,
        }

    # Structural quantities that are absent in old/partial Module 1 takeoffs.
    # These are planning fallbacks only and are tagged as such in provenance.
    concrete_qty=quantities.get("concrete",0.0)
    # PATCH 197/530: preserve an existing Module 1 reinforcement planning row
    # before deriving a new mass from concrete.
    if "reinforcing_steel" not in quantities and "reinforcing_steel" in allowed:
        _rq,_rm=_tagged_rebar_planning_quantity(module1)
        if _rm.get("provisional_dependency") and concrete_qty>0 and _f(_rm.get("rebar_rate_kg_per_m3"))>0:
            _rate=_f(_rm.get("rebar_rate_kg_per_m3"))
            _rq=concrete_qty*_rate/1000.0
            _rm["source"]="Module 1 provisional reinforcement specification + current canonical concrete"
            _rm["basis"]=f"Recomputed dependency: current concrete {concrete_qty:.6f} m3 × {_rate:.3f} kg/m3 ÷ 1000; stored provisional mass ignored"
        if _rq>0:
            quantities["reinforcing_steel"]=_rq
            provenance["reinforcing_steel"]={"source_type":"module1_tagged_planning_quantity","source":_rm.get("source","Module 1 reinforcement rows"),"basis":_rm.get("basis","Module 1 reinforcement planning quantity"),"source_items":[_rm.get("source_item")],"construction_method":method,"certainty":"estimated","planning_only":True,"rebar_rate_kg_per_m3":_rm.get("rebar_rate_kg_per_m3")}
    gfa=_f((project.get("common",{}) or {}).get("scale_gfa_m2"))
    if method=="wood_frame":
        # 2x6 superstructure timber. The project assumption used by the Evaluation
        # suite is 0.145 m3 per m2 of floor area when a timber takeoff is absent.
        fallback("dimension_lumber",gfa*0.145,
                 f"2×6木拾い数量未入力のため、延床面積 {gfa:.3f} m2 × 0.145 m3/m2")
        # RC foundation reinforcement is required even for timber construction.
        # 100 kg/m3 is a transparent planning allowance until foundation rebar
        # drawings/takeoff are supplied.
        fallback("reinforcing_steel",concrete_qty*100.0/1000.0,
                 f"2×6基礎鉄筋数量未入力のため、基礎コンクリート {concrete_qty:.3f} m3 × 100 kg/m3 ÷ 1000")
    elif method=="azras":
        fallback("dimension_lumber",gfa*0.060,
                 f"AZRAS更新木造数量未入力のため、延床面積 {gfa:.3f} m2 × 0.060 m3/m2")
        fallback("reinforcing_steel",concrete_qty*90.0/1000.0,
                 f"AZRAS鉄筋数量未入力のため、コンクリート {concrete_qty:.3f} m3 × 90 kg/m3 ÷ 1000")
    elif method=="rc_frame":
        fallback("reinforcing_steel",concrete_qty*120.0/1000.0,
                 f"RCラーメン鉄筋数量未入力のため、コンクリート {concrete_qty:.3f} m3 × 120 kg/m3 ÷ 1000")

    # Formwork is a required trade for concrete construction. If the drawing
    # has no explicit takeoff, derive a transparent planning fallback from concrete.
    if concrete_qty>0 and "formwork" not in quantities and "formwork" in allowed:
        if method=="azras":
            geo_fw=_azras_geometry_formwork_m2(profile)
            if geo_fw:
                fw_qty, fw_basis=geo_fw
                fallback("formwork",fw_qty,fw_basis)
            else:
                factor=_formwork_factor(method)
                fallback("formwork",concrete_qty*factor,
                         f"型枠数量未入力のため、コンクリート {concrete_qty:.3f} m3 × 工法別係数 {factor:.1f} m2/m3")
        elif method=="wood_frame":
            fg=(profile.get("construction",{}) or {}).get("foundation_geometry",{}) or {}
            fw=((fg.get("formwork_m2") or {}).get("total"))
            if _f(fw)>0:
                fallback("formwork",_f(fw),
                         f"Module 1 布基礎実形状: 立上り両面型枠 {_f(fw):.3f} m2（底盤側面は自動計上しない）")
            else:
                factor=_formwork_factor(method)
                fallback("formwork",concrete_qty*factor,
                         f"型枠数量未入力のため、コンクリート {concrete_qty:.3f} m3 × 工法別係数 {factor:.1f} m2/m3")
        elif method=="rc_frame":
            rc_fw=_rc_frame_formwork_geometry(profile)
            if rc_fw:
                fallback(
                    "formwork",_f(rc_fw.get("quantity_m2")),
                    "RCラーメン部位別形状: "
                    + " + ".join(
                        f"{k}={_f(v):.3f}m2"
                        for k,v in (rc_fw.get("components_m2") or {}).items()
                    )
                )
            else:
                factor=_formwork_factor(method)
                fallback("formwork",concrete_qty*factor,
                         f"型枠数量未入力のため、コンクリート {concrete_qty:.3f} m3 × 工法別係数 {factor:.1f} m2/m3")
        else:
            factor=_formwork_factor(method)
            fallback("formwork",concrete_qty*factor,
                     f"型枠数量未入力のため、コンクリート {concrete_qty:.3f} m3 × 工法別係数 {factor:.1f} m2/m3")

    return ({k:v for k,v in quantities.items() if v>0},provenance,excluded)


# PATCH 034 — common 2004 price basis for all construction methods.
COMMON_2004_BASIS = {
    "base_year":2004,
    "reference_region":"Japan / Nagoya",
    "azras_actual_estimate_jpy_ex_tax":34500000.0,
    "azras_actual_gfa_m2":245.52,
    "default_escalation_2004_to_target":1.60,
    # Common market-level calibration derived from the AZRAS 2004 actual
    # benchmark versus the former planning model. It is applied to ALL methods.
    "common_market_calibration_factor":0.5630354957160343,
}


# PATCH 072 — 2026 Aichi market calibration.
# The former 0.563... factor came from the 2004 AZRAS historical estimate.
# It is retained only as historical metadata and is no longer used as a
# universal calibration for unrelated structures.
MARKET_CALIBRATION_2026 = {
    "region":"Aichi, Japan",
    "target_year":2026,
    "wood_frame_factor":0.6116430802027721,
    "rc_frame_factor":0.8453004829041244,
    "basis":{
        "wood_2025_jpy_per_m2":217000.0,
        "wood_2026_trend_percent":5.9,
        "wood_2026_reference_jpy_per_m2":229803.0,
        "rc_2025_jpy_per_m2":338000.0,
        "rc_2026_trend_percent":5.5,
        "rc_2026_reference_jpy_per_m2":356590.0,
    },
    "policy_ja":(
        "2004年AZRAS実績から得た共通係数を2×6・RCへ一律適用する方式を廃止。"
        "木造とRCはそれぞれ独立した2026年市場監査値で地域推定成分を校正する。"
        "AZRASはRC工種をRC側、木造・共通住宅工種を木造側の校正値で評価する。"
        "確認済み現地単価は従来どおり校正を掛けない。"
    )
}

def _market_calibration_factor_2026(
    method: str,
    cost_group: str,
    settings: dict[str,Any]
) -> tuple[float,str]:
    """PATCH 072: method/component-aware current-market calibration."""
    wood=max(_f(settings.get("market_calibration_factor_wood_2026"),
                MARKET_CALIBRATION_2026["wood_frame_factor"]),0.01)
    rc=max(_f(settings.get("market_calibration_factor_rc_2026"),
              MARKET_CALIBRATION_2026["rc_frame_factor"]),0.01)

    if method=="rc_frame":
        return rc,"rc_2026_market_calibration"
    if method=="wood_frame":
        return wood,"wood_2026_market_calibration"
    if method=="azras":
        if cost_group in {"rc_structure","rc_foundation_preparation"}:
            return rc,"azras_rc_component_uses_rc_2026_calibration"
        return wood,"azras_wood_or_common_component_uses_wood_2026_calibration"
    return wood,"default_wood_common_2026_calibration"

def _common_2004_price_settings(settings: dict[str, Any]):
    enabled=settings.get("use_common_2004_price_basis", True)
    if isinstance(enabled,str):
        enabled=enabled.strip().lower() not in {"0","false","no","off"}
    escalation=max(_f(settings.get("common_2004_to_target_cost_factor"),1.60),0.01)
    calibration=max(_f(settings.get("common_2004_market_calibration_factor"),COMMON_2004_BASIS["common_market_calibration_factor"]),0.01)
    return bool(enabled),escalation,calibration


def _market_cost_group(cost_item_key: str) -> str:
    """PATCH 043: neutral market-audit grouping; does not change prices."""
    if cost_item_key in {"concrete","reinforcing_steel","formwork"}:
        return "rc_structure"
    if cost_item_key in {"excavation","backfill","imported_fill","soil_disposal","blinding_concrete","ground_preparation"}:
        return "rc_foundation_preparation"
    if cost_item_key in {"dimension_lumber","structural_plywood"}:
        return "wood_structure"
    if cost_item_key in {"phenolic_foam","xps"}:
        return "insulation"
    if cost_item_key in {"external_finish","external_finish_rc","external_finish_timber","roofing"}:
        return "envelope_finish"
    if cost_item_key in {"gypsum_board","interior_finish"}:
        return "interior_finish"
    if cost_item_key in {"glass","doors"}:
        return "openings"
    return "other"


def _market_benchmark_reference(method: str) -> dict[str, Any]:
    """External whole-building benchmark, for audit only."""
    base = {
        "region":"Aichi, Japan",
        "reference_year":2026,
        "base_reference_year":2025,
        "source":"National Tax Agency (Japan), 2025 regional/structural construction cost table",
        "source_url":"https://www.nta.go.jp/taxes/shiraberu/saigai/h30/0018008-045/07.htm",
        "scope_note_ja":"構造別の外部ベンチマーク。今回の3戸長屋と完全同一条件ではないため、総額を強制一致させる係数には使用しない。",
    }
    if method=="wood_frame":
        return {**base,
                "benchmark_structure":"wood",
                "benchmark_jpy_per_m2":229803.0,
                "benchmark_jpy_per_tsubo":229803.0*3.3057851239669422,
                "base_2025_jpy_per_m2":217000.0,
                "2026_trend_percent":5.9}
    if method=="rc_frame":
        return {**base,
                "benchmark_structure":"reinforced_concrete",
                "benchmark_jpy_per_m2":356590.0,
                "benchmark_jpy_per_tsubo":356590.0*3.3057851239669422,
                "base_2025_jpy_per_m2":338000.0,
                "2026_trend_percent":5.5}
    return {**base,
            "benchmark_structure":"hybrid_rc_wood",
            "benchmark_jpy_per_m2":None,
            "benchmark_jpy_per_tsubo":None,
            "policy_ja":"AZRASには独自の市場坪単価を設定しない。検証済みRC系単価と木造系単価を各実数量へ適用し、結果を木造・RCベンチマークの間で監査する。"}


def _is_residential_project(project: dict[str, Any]) -> bool:
    common=project.get("common",{}) or {}
    use=str(common.get("building_use") or (common.get("building",{}) or {}).get("use") or "").lower()
    return any(token in use for token in ("residential","住宅","テラスハウス","terrace","apartment","貸家","長屋"))

def _normalize_residential_equipment_selection(project,database,equipment_selection):
    selection={k:dict(v or {}) for k,v in (equipment_selection or {}).items()}
    standards=("hvac","electrical","plumbing","kitchen","bathroom")
    all_false=all(not bool((selection.get(k) or {}).get("include")) for k in standards)
    migrated=False
    if _is_residential_project(project) and all_false:
        for k in standards:
            db_item=(database.get("equipment_packages",{}) or {}).get(k,{})
            item=selection.setdefault(k,{})
            item["include"]=True
            if _f(item.get("cost"))<=0: item["cost"]=_f(db_item.get("default_cost_jpy"))
        migrated=True
    return selection,{
        "residential_project":_is_residential_project(project),
        "legacy_all_standard_packages_false":all_false,
        "auto_migrated_to_complete_building_scope":migrated,
        "standard_packages":list(standards),
        "policy_ja":"住宅市場坪単価との比較では空調・電気・給排水衛生・キッチン・浴室を含む完成建物価格を標準とする。"
    }

def _rc_frame_formwork_geometry(profile: dict[str,Any]) -> dict[str,Any] | None:
    """RC formwork only from current-PDF explicit member geometry and volumes."""
    construction=profile.get("construction",{}) or {}
    cv=construction.get("concrete_volume_m3",{}) or {}
    mg=construction.get("member_geometry",{}) or {}
    if mg.get("source")!="pdf_text_explicit_only": return None
    def mmv(key,n):
        v=mg.get(key) or []
        try:
            vals=[float(v[i])/1000.0 for i in range(n)]
            return vals if all(x>0 for x in vals) else None
        except Exception: return None
    wall_t=_f(mg.get("rc_wall_thickness_mm"))/1000.0
    col=mmv("column_mm",2); beam=mmv("beam_mm",2)
    slab_t=_f(mg.get("upper_slab_thickness_mm"))/1000.0
    wall_v=_f(cv.get("rc_walls")); col_v=_f(cv.get("columns")); beam_v=_f(cv.get("beams")); slab_v=_f(cv.get("upper_slabs"))
    comps={}
    if wall_t>0 and wall_v>0: comps["rc_walls_both_faces"]=(wall_v/wall_t)*2.0
    if col and col_v>0:
        L=col_v/(col[0]*col[1]); comps["columns_four_sides"]=L*2.0*(col[0]+col[1])
    if beam and beam_v>0:
        L=beam_v/(beam[0]*beam[1]); comps["beams_two_sides_plus_soffit"]=L*(2.0*beam[1]+beam[0])
    if slab_t>0 and slab_v>0: comps["upper_slabs_soffit"]=slab_v/slab_t
    if not comps: return None
    return {"status":"current_pdf_explicit_geometry","quantity_m2":sum(comps.values()),"components_m2":comps,
            "confidence":"requires_user_confirmation","requires_confirmation":True,
            "basis_ja":"現在PDFから明示取得した部材寸法と部位別コンクリート量のみで算定。比較サンプル固定値は使用しない。"}


def _rc_structure_market_audit(lines: list[dict[str,Any]], method: str) -> dict[str,Any]:
    """PATCH 045: diagnostic audit of RC structure quantities and effective unit rates.
    No cost adjustment is performed.
    """
    if method not in {"rc_frame","azras"}:
        return {"status":"not_applicable"}

    wanted={"concrete","reinforcing_steel","formwork"}
    rows={r.get("cost_item_key"):r for r in lines if r.get("cost_item_key") in wanted}

    audit={
        "status":"audit_only_no_price_adjustment",
        "items":{},
        "source_policy_ja":"数量・現在有効単価・数量根拠を分離表示し、RC価格不足が数量不足か単価不足かを判断する。公開市場単価で裏付けられない値は勝手に補正しない。",
        "public_market_context_ja":[
            "愛知県の主要資材単価（鋼材・生コン等）は毎月、物価資料により改定されるが、物価資料掲載単価のため非公表。",
            "市場単価・標準材料単価も原則年4回改定されるが、物価資料掲載単価のため非公表。",
            "従って公開資料のみでは生コン・鉄筋・型枠の2026愛知県実勢単価を厳密に確定できない。"
        ],
        "source_url":"https://www.pref.aichi.jp/soshiki/kensetsu-kikaku/kenchikusekisan.html"
    }
    for key in ("concrete","reinforcing_steel","formwork"):
        r=rows.get(key)
        if not r:
            audit["items"][key]={"status":"missing"}
            continue
        unit_total=_f(r.get("material_unit_cost"))+_f(r.get("labor_unit_cost"))+_f(r.get("equipment_unit_cost"))
        audit["items"][key]={
            "status":"present",
            "quantity":_f(r.get("quantity")),
            "unit":r.get("unit"),
            "material_unit_cost_jpy":_f(r.get("material_unit_cost")),
            "labor_unit_cost_jpy":_f(r.get("labor_unit_cost")),
            "equipment_unit_cost_jpy":_f(r.get("equipment_unit_cost")),
            "effective_total_unit_cost_jpy":unit_total,
            "line_total_jpy":_f(r.get("line_total_after_conditions")),
            "quantity_source_type":r.get("quantity_source_type"),
            "quantity_source":r.get("quantity_source"),
            "quantity_basis":r.get("quantity_basis"),
        }

    fw=audit["items"].get("formwork",{})
    if fw.get("quantity_source_type")=="method_fallback_estimate":
        fw["quantity_confidence"]="low_to_medium"
        fw["warning_ja"]="型枠数量は図面実拾いではなく工法係数推定。RCラーメンの市場価格校正前に、柱・梁・床・基礎の型枠面積を部位別に確認することが望ましい。"
    else:
        fw["quantity_confidence"]="drawing_or_geometry_based"

    if method=="rc_frame":
        audit["rc_frame_gap_diagnosis_ja"]=[
            "完成建物範囲に設備5工種を含めても、RCラーメンは外部RCベンチマークを大きく下回る。",
            "コンクリート量と鉄筋量はModule 1 drawing_quantity。型枠はPATCH 046で部位別形状算定へ更新済み。",
            "現段階では総額差をRC躯体単価へ一括上乗せせず、RC固有工種の欠落と型枠実数量を先に点検する。"
        ]
    else:
        audit["azras_policy_ja"]="AZRASはRCラーメン側で検証済みとなったRC単価体系のみをRC部分へ適用する。AZRAS独自のRC市場補正は設定しない。"
    return audit



def _foundation_earthwork_geometry(profile: dict[str,Any], method: str, soil_handling_mode: str="no_stockpile") -> dict[str,Any] | None:
    """PATCH 053: earthwork + groundwork comparison under the current project assumptions.

    Common assumptions:
      good ground
      working clearance 300 mm each side
      blinding concrete 50 mm
      crushed stone 100 mm
      blinding projection 100 mm each side
      loose-soil bulking factor 1.20
      soil handling is user-selectable:
        stockpile_available -> excavated soil reused for required backfill,
                               only surplus is hauled off-site.
        no_stockpile        -> all excavated soil hauled off-site,
                               required backfill is imported fill.

    Ground preparation includes the 100 mm crushed-stone layer below the full
    ground-floor slab plus foundation groundwork, with overlap deducted.
    """
    construction=profile.get("construction",{}) or {}
    geometry=profile.get("geometry",{}) or {}
    working_clearance=0.300
    blinding_t=0.050
    stone_t=0.100
    blinding_projection=0.100
    bulking_factor=1.20
    footprint=_f(geometry.get("footprint_m2"))

    def apply_soil_handling(result: dict[str,Any]) -> dict[str,Any]:
        q=result.get("quantities",{}) or {}
        excavation=_f(q.get("excavation_m3"))
        backfill=_f(q.get("backfill_m3"))
        net_surplus=max(0.0,excavation-backfill)
        q["surplus_soil_in_situ_m3"]=net_surplus
        pa=result.setdefault("planning_assumptions",{})
        qb=result.setdefault("quantity_basis",{})

        if soil_handling_mode=="stockpile_available":
            # Excavated soil is temporarily stored on site and reused for backfill.
            q["excavated_soil_to_offsite_in_situ_m3"]=net_surplus
            q["soil_disposal_loose_m3"]=net_surplus*bulking_factor
            q["imported_backfill_m3"]=0.0
            pa["soil_handling_mode"]="on_site_reuse_then_surplus_disposal"
            pa["on_site_excavated_soil_stockpile_available"]=True
            pa["imported_fill_required"]=False
            qb["soil_disposal"]="現場内仮置場あり。必要埋戻しに掘削土を再利用し、正味余剰土（地山量）×ほぐし係数1.20のみ場外搬出・処分"
            qb["imported_fill"]="現場内仮置場あり。掘削土を埋戻しに再利用するため客土・購入土は0m3"
            qb["backfill"]="必要埋戻し量。現場内に仮置きした掘削土を再利用して締固める"
        else:
            # No stockpile: all excavation leaves the site; backfill is imported.
            q["excavated_soil_to_offsite_in_situ_m3"]=excavation
            q["soil_disposal_loose_m3"]=excavation*bulking_factor
            q["imported_backfill_m3"]=backfill
            pa["soil_handling_mode"]="off_site_all_excavated_soil_imported_backfill"
            pa["on_site_excavated_soil_stockpile_available"]=False
            pa["imported_fill_required"]=backfill>0
            qb["soil_disposal"]="現場内仮置場なし。根切土全量（地山量）×ほぐし係数1.20を場外搬出・処分対象とする"
            qb["imported_fill"]="現場内仮置場なし。必要埋戻し量を客土・購入土として搬入する"
            qb["backfill"]="必要埋戻し量。掘削土再利用ではなく客土・購入土を締固めて埋戻す"

        result["quantities"]=q
        return result

    if method=="rc_frame":
        result=_rc_foundation_earthwork_geometry(profile)
        if not result:
            return None
        result["source"]="Module 5 PATCH 048/051/053 RC foundation geometry"
        q=result.get("quantities",{}) or {}
        foundation_area=_f(q.get("ground_preparation_area_m2"))
        foundation_stone=_f(q.get("ground_preparation_crushed_stone_m3"))
        slab_area=max(0.0,footprint)
        # Planning assumption: independent-footing / ground-beam groundwork is
        # within the slab footprint, so the slab-wide layer supersedes overlap.
        unique_area=max(foundation_area,slab_area)
        q["foundation_ground_preparation_area_m2"]=foundation_area
        q["foundation_ground_preparation_crushed_stone_m3"]=foundation_stone
        q["slab_under_ground_preparation_area_m2"]=slab_area
        q["slab_under_ground_preparation_crushed_stone_m3"]=slab_area*stone_t
        q["ground_preparation_overlap_deduction_area_m2"]=min(foundation_area,slab_area)
        q["ground_preparation_area_m2"]=unique_area
        q["ground_preparation_crushed_stone_m3"]=unique_area*stone_t
        result["quantities"]=q
        result["planning_assumptions"].update({
            "good_ground_condition":True,
            "crushed_stone_thickness_mm":100.0,
            "slab_under_crushed_stone_included":True,
            "ground_preparation_overlap_deduction_applied":True,
            "ground_preparation_overlap_policy":"RC独立基礎・地中梁の地業範囲は、現在Projectの土間スラブ範囲との重複を幾何情報で確認して控除"
        })
        result["quantity_basis"]={
            "excavation":"RC独立基礎・地中梁の計画根切り数量（余幅300mm、捨てコン50mm、砕石100mm仮定）",
            "backfill":"根切りグロス数量－地下構造体－捨てコン－基礎下砕石による必要埋戻し量",
            "soil_disposal":"現場内仮置場なし。根切土全量（地山量）×ほぐし係数1.20を搬出・処分対象とする",
            "imported_fill":"必要埋戻し量を客土・購入土として搬入する",
            "blinding_concrete":"独立基礎・地中梁下 捨てコンクリート50mm、片側100mm張出し仮定",
            "ground_preparation":"良好地盤。独立基礎・地中梁下＋土間コン全面下の砕石100mm。重複範囲は一重計上",
        }
        return apply_soil_handling(result)

    if method=="wood_frame":
        fg=construction.get("foundation_geometry",{}) or {}
        if str(fg.get("foundation_type") or "")!="strip_foundation_with_slab_on_ground":
            return None
        dims=fg.get("dimensions_mm",{}) or {}
        lengths=fg.get("centerline_length_breakdown_m",{}) or {}
        cv=fg.get("concrete_volume_m3",{}) or {}
        footing_w=_f(dims.get("footing_width"))/1000.0
        total_h=_f(dims.get("total_height"))/1000.0
        length=_f(lengths.get("total"))
        strip_concrete=_f(cv.get("strip_foundation"))
        if min(footing_w,total_h,length,strip_concrete)<=0:
            return None
        excavation_w=footing_w+2*working_clearance
        excavation_depth=total_h+blinding_t+stone_t
        gross=length*excavation_w*excavation_depth
        blind_area=length*(footing_w+2*blinding_projection)
        blind=blind_area*blinding_t
        foundation_stone=blind_area*stone_t
        permanent=strip_concrete+blind+foundation_stone
        backfill=max(0.0,gross-permanent)

        slab_area=footprint
        plan_dims=fg.get("plan_dimensions_m",{}) or {}
        plan_w=_f(plan_dims.get("width") or geometry.get("width_m"))
        plan_d=_f(plan_dims.get("depth") or geometry.get("depth_m"))
        groundwork_width=footing_w+2*blinding_projection
        if plan_w>0 and plan_d>0 and abs(plan_w*plan_d-footprint)<=max(0.2, footprint*0.005):
            # Perimeter strip centerline lies on the building line. Half of the
            # groundwork width extends outward and half inward. Interior strips
            # are already inside the slab-wide groundwork and are therefore not
            # double-counted.
            outward=groundwork_width/2.0
            unique_ground_area=(plan_w+2*outward)*(plan_d+2*outward)
            outside_band=max(0.0,unique_ground_area-footprint)
            overlap_deduction=max(0.0,blind_area-outside_band)
            overlap_policy=(
                f"図面寸法{plan_w:.3f}m×{plan_d:.3f}mと布基礎地業幅{groundwork_width:.3f}mを使用。"
                "外周の外側半幅のみ土間範囲外へ追加し、内部側・内部布基礎は土間下砕石との重複を控除"
            )
        else:
            unique_ground_area=max(blind_area,slab_area)
            outside_band=max(0.0,unique_ground_area-slab_area)
            overlap_deduction=min(blind_area,slab_area)
            overlap_policy="矩形寸法を安全に確認できないため、基礎地業と土間全面の大きい方を採用する保守的重複控除"

        result={
            "status":"matched_planning_geometry",
            "source":"Module 5 PATCH 053 2x6 strip foundation + slab groundwork geometry",
            "planning_assumptions":{
                "working_clearance_each_side_mm":300.0,
                "blinding_concrete_thickness_mm":50.0,
                "crushed_stone_thickness_mm":100.0,
                "blinding_projection_each_side_mm":100.0,
                "soil_bulking_factor":1.20,
                "good_ground_condition":True,
                "slab_under_crushed_stone_included":True,
                "ground_preparation_overlap_deduction_applied":True,
                "ground_preparation_overlap_policy":overlap_policy,
                "excavation_overlap_deduction_applied":False,
                "note_ja":"布基礎中心線長・底盤幅・総高はModule 1で確認された基礎形状を使用。土間コン全面下にも砕石100mmを追加し、平面寸法が確認できる場合は外周外側分だけ追加して重複控除。"
            },
            "drawing_supported":{
                "foundation_type":"strip_foundation_with_slab_on_ground",
                "centerline_length_m":length,
                "footing_width_mm":footing_w*1000,
                "total_height_mm":total_h*1000,
                "strip_foundation_concrete_m3":strip_concrete,
                "slab_footprint_m2":slab_area
            },
            "quantities":{
                "excavation_m3":gross,
                "backfill_m3":backfill,
                "surplus_soil_in_situ_m3":max(0.0,gross-backfill),
                "soil_disposal_loose_m3":0.0,
                "imported_backfill_m3":backfill,
                "blinding_area_m2":blind_area,
                "blinding_concrete_m3":blind,
                "foundation_ground_preparation_area_m2":blind_area,
                "foundation_ground_preparation_crushed_stone_m3":foundation_stone,
                "slab_under_ground_preparation_area_m2":slab_area,
                "slab_under_ground_preparation_crushed_stone_m3":slab_area*stone_t,
                "ground_preparation_overlap_deduction_area_m2":overlap_deduction,
                "ground_preparation_outside_slab_area_m2":outside_band,
                "ground_preparation_area_m2":unique_ground_area,
                "ground_preparation_crushed_stone_m3":unique_ground_area*stone_t
            },
            "quantity_basis":{
                "excavation":"2×6布基礎中心線長×（底盤幅+両側余幅300mm）×（基礎総高+捨てコン50mm+砕石100mm）",
                "backfill":"根切りグロス数量－布基礎構造体－捨てコン－基礎下砕石による必要埋戻し量",
                "soil_disposal":"現場内仮置場なし。根切土全量（地山量）×ほぐし係数1.20を搬出・処分対象とする",
                "imported_fill":"必要埋戻し量を客土・購入土として搬入する",
                "blinding_concrete":"2×6布基礎下 捨てコンクリート50mm、片側100mm張出し仮定",
                "ground_preparation":"良好地盤。2×6布基礎下＋土間コン全面下の砕石100mm。重複範囲は一重計上"
            },
            "confidence":"medium_low_planning_assumptions",
            "requires_confirmation":True,
            "price_adjustment_applied":False
        }
        return apply_soil_handling(result)

    if method=="azras":
        cv=construction.get("concrete_volume_m3",{}) or {}
        slab=_f(cv.get("slab_foundation") or construction.get("foundation_slab_volume_m3"))
        slab_t=_f(construction.get("slab_thickness_mm"))/1000.0
        length=_f(geometry.get("width_m"))
        width=_f(geometry.get("depth_m"))
        if min(length,width,footprint,slab,slab_t)<=0:
            return None
        # Accept any rectangular drawing geometry when plan dimensions, footprint
        # and slab concrete are mutually consistent. Do not key the calculation
        # to the old 12.9 x 9.5 comparison sample.
        if abs(length*width-footprint)>max(0.2,footprint*0.005):
            return None
        expected_slab=footprint*slab_t
        if abs(slab-expected_slab)>max(0.2,expected_slab*0.01):
            return None
        gross=(length+2*working_clearance)*(width+2*working_clearance)*(slab_t+blinding_t+stone_t)
        blind_area=(length+2*blinding_projection)*(width+2*blinding_projection)
        blind=blind_area*blinding_t
        stone=blind_area*stone_t
        permanent=slab+blind+stone
        backfill=max(0.0,gross-permanent)
        result={
            "status":"matched_planning_geometry",
            "source":"Module 5 PATCH 053 AZRAS mat foundation geometry",
            "planning_assumptions":{
                "working_clearance_each_side_mm":300.0,
                "blinding_concrete_thickness_mm":50.0,
                "crushed_stone_thickness_mm":100.0,
                "blinding_projection_each_side_mm":100.0,
                "soil_bulking_factor":1.20,
                "good_ground_condition":True,
                "slab_under_crushed_stone_included":True,
                "ground_preparation_overlap_deduction_applied":True,
                "ground_preparation_overlap_policy":"AZRASベタ基礎下面の砕石範囲が土間・基礎全面を包含するため別加算なし",
                "excavation_overlap_deduction_applied":False,
                "note_ja":f"AZRAS図面から確認した{length:.3f}m×{width:.3f}m、ベタ基礎厚{slab_t*1000:.0f}mmを使用。ベタ基礎下面砕石100mmは全面地業として一重計上。"
            },
            "drawing_supported":{
                "foundation_type":"mat_foundation","length_m":length,"width_m":width,
                "footprint_m2":footprint,"slab_thickness_mm":slab_t*1000,
                "foundation_slab_concrete_m3":slab
            },
            "quantities":{
                "excavation_m3":gross,
                "backfill_m3":backfill,
                "surplus_soil_in_situ_m3":max(0.0,gross-backfill),
                "soil_disposal_loose_m3":0.0,
                "imported_backfill_m3":backfill,
                "blinding_area_m2":blind_area,
                "blinding_concrete_m3":blind,
                "foundation_ground_preparation_area_m2":blind_area,
                "foundation_ground_preparation_crushed_stone_m3":stone,
                "slab_under_ground_preparation_area_m2":footprint,
                "slab_under_ground_preparation_crushed_stone_m3":footprint*stone_t,
                "ground_preparation_overlap_deduction_area_m2":footprint,
                "ground_preparation_area_m2":blind_area,
                "ground_preparation_crushed_stone_m3":stone
            },
            "quantity_basis":{
                "excavation":f"AZRASベタ基礎{length:.3f}m×{width:.3f}m外周に余幅300mm、深さ=基礎厚{slab_t*1000:.0f}mm+捨てコン50mm+砕石100mmの計画根切り",
                "backfill":"根切りグロス数量－ベタ基礎構造体－捨てコン－砕石による必要埋戻し量",
                "soil_disposal":"現場内仮置場なし。根切土全量（地山量）×ほぐし係数1.20を搬出・処分対象とする",
                "imported_fill":"必要埋戻し量を客土・購入土として搬入する",
                "blinding_concrete":"AZRASベタ基礎下 捨てコンクリート50mm、外周100mm張出し仮定",
                "ground_preparation":"良好地盤。AZRASベタ基礎全面下の砕石100mm。土間・基礎範囲との重複は一重計上"
            },
            "confidence":"medium_low_planning_assumptions",
            "requires_confirmation":True,
            "price_adjustment_applied":False
        }
        return apply_soil_handling(result)

    return None


def _foundation_soil_balance_audit(earthwork: dict[str,Any] | None, method: str) -> dict[str,Any] | None:
    """PATCH 053: audit geometric soil balance, full disposal and imported fill."""
    if not earthwork:
        return None
    q=earthwork.get("quantities",{}) or {}
    a=earthwork.get("planning_assumptions",{}) or {}
    excavation=_f(q.get("excavation_m3"))
    backfill=_f(q.get("backfill_m3"))
    surplus=_f(q.get("surplus_soil_in_situ_m3"))
    disposal=_f(q.get("soil_disposal_loose_m3"))
    imported=_f(q.get("imported_backfill_m3"))
    bulking=_f(a.get("soil_bulking_factor"),1.20)
    no_stockpile=(a.get("on_site_excavated_soil_stockpile_available") is False)

    balance_error=excavation-backfill-surplus
    expected_disposal=(excavation if no_stockpile else surplus)*bulking
    expected_imported=backfill if no_stockpile else 0.0
    disposal_error=disposal-expected_disposal
    imported_error=imported-expected_imported
    tol=1e-6
    status="ok" if max(abs(balance_error),abs(disposal_error),abs(imported_error))<=tol else "check_required"

    if no_stockpile:
        formula_ja=[
            "幾何学的土量収支：根切り量 ＝ 必要埋戻し量 ＋ 正味余剰土（地山量）",
            "仮置場なし：搬出処分量（ほぐし）＝ 根切り土全量（地山量）×1.20",
            "仮置場なし：客土・購入土量 ＝ 必要埋戻し量",
        ]
        interpretation_ja=(
            "現場内仮置場なし。根切土は全量を場外搬出し、必要埋戻しは客土・購入土を搬入する。"
        )
    else:
        formula_ja=[
            "幾何学的土量収支：根切り量 ＝ 必要埋戻し量 ＋ 正味余剰土（地山量）",
            "仮置場あり：搬出処分量（ほぐし）＝ 正味余剰土（地山量）×1.20",
            "仮置場あり：客土・購入土量 ＝ 0m3（掘削土を必要埋戻しに再利用）",
        ]
        interpretation_ja=(
            "現場内仮置場あり。掘削土を必要埋戻しに再利用し、正味余剰土のみを場外搬出する。"
        )

    return {
        "patch":"PATCH 055",
        "status":status,
        "construction_method":method,
        "soil_handling_mode":a.get("soil_handling_mode","on_site_reuse_then_surplus_disposal"),
        "on_site_excavated_soil_stockpile_available":not no_stockpile,
        "excavation_m3":excavation,
        "backfill_m3":backfill,
        "net_surplus_soil_in_situ_m3":surplus,
        "imported_backfill_m3":imported,
        "soil_bulking_factor":bulking,
        "soil_disposal_loose_m3":disposal,
        "geometric_balance_error_m3":balance_error,
        "disposal_conversion_error_m3":disposal_error,
        "imported_fill_error_m3":imported_error,
        "formula_ja":formula_ja,
        "interpretation_ja":interpretation_ja,
        "price_adjustment_applied":False,
        "requires_confirmation":True,
    }


def _rc_foundation_earthwork_geometry(profile: dict[str,Any]) -> dict[str,Any] | None:
    """RC foundation earthwork from current-PDF explicit geometry only."""
    construction=profile.get("construction",{}) or {}
    mg=construction.get("member_geometry",{}) or {}
    if mg.get("source")!="pdf_text_explicit_only": return None
    try:
        f=[float(x)/1000.0 for x in (mg.get("isolated_footing_mm") or [])[:3]]
        b=[float(x)/1000.0 for x in (mg.get("ground_beam_mm") or [])[:2]]
        n=int(mg.get("isolated_footing_count") or 0)
        L=float(mg.get("ground_beam_length_m") or 0.0)
    except Exception: return None
    if len(f)!=3 or len(b)!=2 or n<=0 or L<=0 or min(f+b)<=0: return None
    footing_b,footing_d,footing_h=f; beam_b,beam_h=b
    working_clearance=0.300; blinding_t=0.050; stone_t=0.100; projection=0.100; bulking=1.20
    footing_exc=n*(footing_b+2*working_clearance)*(footing_d+2*working_clearance)*(footing_h+blinding_t+stone_t)
    beam_exc=L*(beam_b+2*working_clearance)*(beam_h+blinding_t+stone_t)
    excavation=footing_exc+beam_exc
    blind_area=n*(footing_b+2*projection)*(footing_d+2*projection)+L*(beam_b+2*projection)
    blind_vol=blind_area*blinding_t; stone_vol=blind_area*stone_t
    permanent=n*footing_b*footing_d*footing_h + L*beam_b*beam_h + blind_vol + stone_vol
    backfill=max(0.0,excavation-permanent); surplus=max(0.0,excavation-backfill)
    return {
        "status":"current_pdf_explicit_geometry","source":"Module 1 current PDF member geometry",
        "pricing_status":"quantity_only_unit_prices_required","requires_confirmation":True,
        "drawing_supported":{"isolated_footing_count":n,"isolated_footing_mm":[x*1000 for x in f],"ground_beam_mm":[x*1000 for x in b],"ground_beam_length_m":L},
        "planning_assumptions":{"working_clearance_each_side_mm":300,"blinding_concrete_thickness_mm":50,"crushed_stone_thickness_mm":100,"soil_bulking_factor":bulking,
            "note_ja":"部材形状・数量根拠は現在PDF明示値。根切り余幅・捨てコン・砕石厚のみ計画仮定。"},
        "quantities":{"excavation_m3":excavation,"excavation_footings_m3":footing_exc,"excavation_ground_beams_m3":beam_exc,"backfill_m3":backfill,
            "surplus_soil_in_situ_m3":surplus,"soil_disposal_loose_m3":surplus*bulking,"blinding_area_m2":blind_area,"blinding_concrete_m3":blind_vol,
            "ground_preparation_area_m2":blind_area,"ground_preparation_crushed_stone_m3":stone_vol},
        "confidence":"requires_user_confirmation","price_adjustment_applied":False,
    }


def _rc_specific_scope_audit(
    lines: list[dict[str,Any]],
    equipment_packages: list[dict[str,Any]],
    method: str,
) -> dict[str,Any]:
    """PATCH 047: identify RC-specific work scopes that are not explicitly priced.

    This is a scope audit only. It does not add cost. Some items may already be
    implicitly embedded in existing labor/equipment or indirect-cost rates, so
    they are flagged for confirmation rather than automatically added.
    """
    if method!="rc_frame":
        return {"status":"not_applicable"}

    keys={str(r.get("cost_item_key")) for r in lines}
    packages={str(r.get("package_key")) for r in equipment_packages}

    checks=[
        {
            "key":"earthwork_excavation_backfill",
            "name_ja":"根切り・掘削・埋戻し・残土処分",
            "explicit_cost_item_keys":["earthwork","excavation","backfill","soil_disposal"],
            "classification":"potential_missing_separate_trade",
            "double_count_risk":"low_to_medium",
            "reason_ja":"独立基礎・地中梁を持つRCラーメンでは地業前の土工が必要だが、現在のcost_linesに独立工種が見当たらない。",
        },
        {
            "key":"blinding_leveling_concrete",
            "name_ja":"捨てコンクリート・地業・基礎下調整",
            "explicit_cost_item_keys":["blinding_concrete","lean_concrete","ground_preparation"],
            "classification":"potential_missing_separate_trade",
            "double_count_risk":"medium",
            "reason_ja":"独立基礎・地中梁施工時に一般に必要となり得るが、現在のコンクリート数量が構造体のみなら別途となる可能性がある。",
        },
        {
            "key":"concrete_pumping_placing",
            "name_ja":"コンクリート圧送・打設補助",
            "explicit_cost_item_keys":["concrete_pump","concrete_pumping","placing"],
            "classification":"scope_unclear_possible_embedded",
            "double_count_risk":"high",
            "reason_ja":"現在concreteには労務・機械費が含まれているため一部内包の可能性が高い。独立追加前に単価内訳確認が必要。",
        },
        {
            "key":"formwork_shoring_support",
            "name_ja":"型枠支保工・スラブ支柱・解体",
            "explicit_cost_item_keys":["formwork_shoring","shoring","falsework"],
            "classification":"scope_unclear_possible_embedded",
            "double_count_risk":"high",
            "reason_ja":"formwork単価に労務・機械費が含まれているが、上階スラブ下面の支保工範囲が独立しているか不明。",
        },
        {
            "key":"construction_joint_waterstop_curing",
            "name_ja":"打継ぎ・止水・養生・補修",
            "explicit_cost_item_keys":["construction_joint","waterstop","curing","concrete_repair"],
            "classification":"scope_unclear_possible_embedded",
            "double_count_risk":"medium_to_high",
            "reason_ja":"RC躯体施工に付随するが、concrete/formwork単価内包か別途か現DBでは判別できない。",
        },
        {
            "key":"temporary_scaffold_rc",
            "name_ja":"RC躯体用足場・仮設",
            "explicit_cost_item_keys":["scaffold","scaffolding","temporary_works"],
            "classification":"scope_unclear_possible_indirect",
            "double_count_risk":"high",
            "reason_ja":"現場経費12%等に一部含まれる可能性があるため、独立追加すると二重計上の恐れがある。",
        },
        {
            "key":"rebar_splice_accessories",
            "name_ja":"鉄筋継手・スペーサー・結束等",
            "explicit_cost_item_keys":["rebar_splice","mechanical_coupler","rebar_accessories"],
            "classification":"scope_unclear_possible_embedded",
            "double_count_risk":"high",
            "reason_ja":"reinforcing_steel単価に材料・労務・機械を含むため通常施工分は内包の可能性がある。特殊継手がある場合のみ別途確認。",
        },
    ]

    for c in checks:
        present=[k for k in c["explicit_cost_item_keys"] if k in keys]
        c["explicitly_priced"]=bool(present)
        c["matched_cost_item_keys"]=present
        c["status"]="explicitly_priced" if present else "not_separately_identified"

    # Core structural items that ARE explicitly covered.
    covered={
        "concrete":"concrete" in keys,
        "reinforcing_steel":"reinforcing_steel" in keys,
        "formwork":"formwork" in keys,
        "thermal_insulation":bool({"phenolic_foam","xps"} & keys),
        "building_services":all(k in packages for k in ("hvac","electrical","plumbing","kitchen","bathroom")),
    }

    return {
        "status":"scope_review_required",
        "price_adjustment_applied":False,
        "covered_core_scopes":covered,
        "checks":checks,
        "diagnosis_ja":[
            "PATCH 046でRC型枠数量は部位別形状へ改善済み。",
            "残る市場差を埋めるための一律上乗せは行わない。",
            "まずRC固有工事が『未計上』なのか『既存単価・現場経費に内包』なのかを分類する。",
            "二重計上リスクが高い項目は、単価内訳が確認できるまで自動追加しない。",
        ],
        "next_action_ja":"PATCH 048で土工・地業の計画数量化を実施。次は2025～2026年の公開実勢資料またはユーザー確認単価を照合し、単価が確認できた項目だけ価格へ反映する。",
    }


def load_external_regional_cost_dataset(location: dict[str,Any], database_path_hint: str | None=None) -> dict[str,Any]:
    """PATCH 061: automatically choose the newest versioned regional cost dataset.

    Similar to weather-data selection:
      1. If dataset_pattern exists, scan matching JSON files.
      2. Parse each file's data_date.
      3. Choose the newest valid data_date.
      4. Fall back to the fixed dataset_file.
    """
    import json
    from pathlib import Path
    from datetime import datetime

    def _base_roots():
        roots=[Path(__file__).resolve().parents[1], Path.cwd()]
        if database_path_hint:
            roots.append(Path(database_path_hint).resolve().parent.parent)
        # preserve order, remove duplicates
        out=[]
        for r in roots:
            try:
                rr=r.resolve()
            except Exception:
                rr=r
            if rr not in out:
                out.append(rr)
        return out

    def _parse_date(v):
        if not v:
            return None
        s=str(v)
        for fmt in ("%Y-%m-%d","%Y-%m","%Y"):
            try:
                return datetime.strptime(s,fmt).date()
            except Exception:
                pass
        return None

    candidates=[]
    pattern=location.get("dataset_pattern")
    if pattern:
        p=Path(str(pattern))
        for root in _base_roots():
            if p.is_absolute():
                glob_root=p.parent
                glob_pat=p.name
            else:
                glob_root=root / p.parent
                glob_pat=p.name
            if glob_root.exists():
                candidates.extend(glob_root.glob(glob_pat))

    # Fixed file remains a fallback / candidate.
    dataset_file=location.get("dataset_file")
    if dataset_file:
        p=Path(str(dataset_file))
        if p.is_absolute():
            candidates.append(p)
        else:
            for root in _base_roots():
                candidates.append(root / p)

    # Unique, existing JSONs only.
    uniq=[]
    for p in candidates:
        try:
            rp=p.resolve()
        except Exception:
            rp=p
        if rp.exists() and rp.suffix.lower()==".json" and rp not in uniq:
            uniq.append(rp)

    if not uniq:
        out=dict(location)
        out["external_dataset_load_status"]="missing"
        out["external_dataset_path"]=str(dataset_file or pattern or "")
        return out

    parsed=[]
    errors=[]
    for src in uniq:
        try:
            ds=json.loads(src.read_text(encoding="utf-8"))
            d=_parse_date(ds.get("data_date"))
            parsed.append((d,src,ds))
        except Exception as exc:
            errors.append({"path":str(src),"error":str(exc)})

    if not parsed:
        out=dict(location)
        out["external_dataset_load_status"]="error"
        out["external_dataset_errors"]=errors
        return out

    # Newest valid data_date first; undated files sort last.
    parsed.sort(key=lambda x: (x[0] is not None, x[0] or datetime.min.date()), reverse=True)
    selected_date, src, ds = parsed[0]

    out=dict(location)
    out["external_dataset_load_status"]="loaded"
    out["external_dataset_path"]=str(src)
    out["external_dataset_candidate_count"]=len(parsed)
    out["external_dataset_selection_policy"]="latest_data_date"
    out["external_dataset_selected_data_date"]=ds.get("data_date")
    out["external_dataset_available_versions"]=[
        {"path":str(p),"data_date":d.isoformat() if d else None}
        for d,p,_ in parsed
    ]
    if errors:
        out["external_dataset_errors"]=errors

    out["unit_cost_dataset"]={
        "region_key":ds.get("region_key"),
        "data_date":ds.get("data_date"),
        "last_checked_date":ds.get("last_checked_date"),
        "source_name":ds.get("source_name"),
        "source_reference":(ds.get("source_references") or [None])[0],
        "source_references":ds.get("source_references") or [],
        "source_type":ds.get("source_type"),
        "status":ds.get("status","not_available"),
        "note_ja":ds.get("note_ja"),
        "source_snapshot":ds.get("source_snapshot") or {},
        "unit_costs_status":ds.get("unit_costs_status"),
    }

    # Allow versioned file to update indices without changing the central DB.
    ri=ds.get("regional_indices") or {}
    if ri:
        for k in ("material_index","labor_index","productivity_index"):
            if k in ri:
                out[k]=ri[k]

    if isinstance(ds.get("module5_cost_item_registry_patch070"),dict):
        out["module5_cost_item_registry_patch070"]=ds["module5_cost_item_registry_patch070"]
    if isinstance(ds.get("module5_cost_closeout_patch070"),dict):
        out["module5_cost_closeout_patch070"]=ds["module5_cost_closeout_patch070"]

    if isinstance(ds.get("unit_costs"),dict) and ds.get("unit_costs"):
        out["unit_costs"]=ds["unit_costs"]
        out["pricing_mode"]="verified_or_estimated_local_unit_costs"
        out["pricing_status"]=ds.get("status","estimated")
    return out


def evaluate_unit_cost_dataset_freshness(location: dict[str,Any], as_of_date: str | None=None) -> dict[str,Any]:
    """PATCH 058: weather-data-like freshness audit for regional construction prices."""
    from datetime import date, datetime

    ds=location.get("unit_cost_dataset") or {}
    raw_status=str(ds.get("status") or "not_available")
    data_date=ds.get("data_date")
    checked=ds.get("last_checked_date")
    today=date.today()
    if as_of_date:
        try:
            today=datetime.strptime(str(as_of_date)[:10],"%Y-%m-%d").date()
        except Exception:
            pass

    def parse_date(v):
        if not v:
            return None
        s=str(v)
        for fmt in ("%Y-%m-%d","%Y-%m","%Y"):
            try:
                d=datetime.strptime(s,fmt).date()
                return d
            except Exception:
                continue
        return None

    d=parse_date(data_date)
    age_months=None
    computed=raw_status
    if d:
        age_months=max(0,(today.year-d.year)*12 + (today.month-d.month))
        if age_months>=24:
            computed="update_required"
        elif age_months>=12 and raw_status=="verified":
            computed="outdated"
    elif raw_status not in {"estimated","not_available"}:
        computed="update_required"

    return {
        "region_key":ds.get("region_key"),
        "data_date":data_date,
        "last_checked_date":checked,
        "source_name":ds.get("source_name"),
        "source_reference":ds.get("source_reference"),
        "source_type":ds.get("source_type"),
        "stored_status":raw_status,
        "status":computed,
        "age_months":age_months,
        "update_required":computed in {"outdated","update_required","not_available"},
        "note_ja":ds.get("note_ja"),
    }


def resolve_location_profile_from_project(project: dict[str,Any], database: dict[str,Any]) -> dict[str,Any]:
    """PATCH 056: resolve Module 5 cost profile from registered project location."""
    common=project.get("common",{}) or {}
    locobj=common.get("location",{}) or {}
    country=str(common.get("country") or locobj.get("country") or "").strip()
    city=str(common.get("city") or locobj.get("city") or "").strip()
    address=str(common.get("address") or locobj.get("address") or "").strip()
    hay=(country+" "+city+" "+address).lower()

    candidates=[]
    if country.lower() in {"japan","日本"} or "japan" in hay or "日本" in hay:
        if any(x in hay for x in ["東京","tokyo"]): candidates=["Japan / Tokyo"]
        elif any(x in hay for x in ["北海道","札幌","sapporo","hokkaido"]): candidates=["Japan / Sapporo"]
        elif any(x in hay for x in ["愛知","名古屋","春日井","nagoya","aichi","kasugai"]): candidates=["Japan / Nagoya"]
    elif any(x in hay for x in ["united states","usa","u.s.","new york","ニューヨーク"]):
        if any(x in hay for x in ["new york","ニューヨーク"]): candidates=["United States / New York"]
    elif any(x in hay for x in ["united kingdom","uk","london","ロンドン","イギリス","英国"]):
        if any(x in hay for x in ["london","ロンドン"]): candidates=["United Kingdom / London"]

    key=next((x for x in candidates if x in (database.get("locations") or {})),None)
    return {
        "matched":bool(key),
        "location_key":key,
        "country":country,
        "city":city,
        "address":address,
        "source":"project.common / project.common.location",
        "fallback_location_key":"User Defined" if "User Defined" in (database.get("locations") or {}) else None,
    }


def _resolved_local_unit(unit: dict[str,Any], location: dict[str,Any], key: str,
                         material_index: float, labor_index: float,
                         fx_jpy_per_local: float) -> tuple[float,float,float,str,dict[str,bool]]:
    """PATCH 069: resolve unit components and mark which components are local-current values.

    Local verified/estimated components are already expressed at the regional
    dataset's current price level and therefore MUST bypass the legacy common
    2004 -> target-year price transformation.  Components that fall back to
    the legacy base database continue through the existing common transform.
    """
    local=(location.get("unit_costs") or {}).get(key)
    currency=str(location.get("currency") or "JPY")

    if currency=="JPY":
        fallback_material=_f(unit["material"])*material_index
        fallback_labor=_f(unit["labor"])*labor_index
        fallback_equipment=_f(unit["equipment"])*material_index
        fallback_source="japan_base_regional_index"
    else:
        if fx_jpy_per_local<=0:
            raise ValueError(
                f"Foreign location '{currency}' requires a confirmed FX rate "
                "(JPY per local currency) or verified local unit costs."
            )
        fallback_material=_f(unit["material"])*material_index/fx_jpy_per_local
        fallback_labor=_f(unit["labor"])*labor_index/fx_jpy_per_local
        fallback_equipment=_f(unit["equipment"])*material_index/fx_jpy_per_local
        fallback_source="foreign_regional_index_fallback_with_confirmed_fx"

    local_flags={"material":False,"labor":False,"equipment":False}

    if not isinstance(local,dict):
        return (
            fallback_material,fallback_labor,fallback_equipment,
            fallback_source,local_flags
        )

    def pick(component: str, fallback: float) -> tuple[float,bool]:
        value=local.get(component)
        if value is None or value=="":
            return fallback,False
        try:
            return float(value),True
        except (TypeError,ValueError):
            return fallback,False

    material,local_flags["material"]=pick("material",fallback_material)
    labor,local_flags["labor"]=pick("labor",fallback_labor)
    equipment,local_flags["equipment"]=pick("equipment",fallback_equipment)

    used=[name for name,flag in local_flags.items() if flag]
    if not used:
        return (
            fallback_material,fallback_labor,fallback_equipment,
            fallback_source,local_flags
        )

    if len(used)==3:
        source="local_unit_cost_all_components"
    else:
        source="partial_local_unit_cost_"+"_".join(used)+"_with_regional_fallback"

    return material,labor,equipment,source,local_flags


def build_regional_unit_cost_coverage_audit(
    location: dict[str,Any],
    base_costs: dict[str,Any],
    cost_lines: list[dict[str,Any]]
) -> dict[str,Any]:
    """PATCH 070: summarize verified/local vs regional-estimate price coverage."""
    registry=(location.get("module5_cost_item_registry_patch070") or {})
    local=(location.get("unit_costs") or {})

    used_keys=[]
    for line in cost_lines or []:
        key=str(line.get("cost_item_key") or "")
        if key and key not in used_keys:
            used_keys.append(key)

    items=[]
    full_local_count=0
    partial_local_count=0
    fallback_count=0
    local_component_count=0

    for key in used_keys:
        meta=local.get(key) if isinstance(local.get(key),dict) else {}
        flags={
            "material": meta.get("material") not in (None,""),
            "labor": meta.get("labor") not in (None,""),
            "equipment": meta.get("equipment") not in (None,""),
        }
        count=sum(1 for v in flags.values() if v)
        local_component_count += count
        if count==3:
            full_local_count += 1
            pricing_mode="local_all_components"
        elif count>0:
            partial_local_count += 1
            pricing_mode="partial_local_plus_fallback"
        else:
            fallback_count += 1
            pricing_mode="regional_index_fallback"

        reg=registry.get(key) if isinstance(registry.get(key),dict) else {}
        items.append({
            "cost_item_key":key,
            "pricing_mode":pricing_mode,
            "local_components":flags,
            "registry_status":reg.get("status"),
            "registry_note_ja":reg.get("note_ja"),
        })

    total=len(used_keys)
    return {
        "patch":"PATCH 070",
        "used_cost_item_count":total,
        "full_local_item_count":full_local_count,
        "partial_local_item_count":partial_local_count,
        "regional_fallback_item_count":fallback_count,
        "local_component_count":local_component_count,
        "maximum_component_count":total*3,
        "calculation_price_status":(
            "source_complete" if total>0 and full_local_count==total
            else "mixed_verified_and_regional_estimate"
        ),
        "requires_future_data_update":fallback_count>0 or partial_local_count>0,
        "items":items,
        "note_ja":(
            "確認済み地域単価がある成分はその値を使用し、未確認成分は地域指数推定を使用。"
            "計算は継続可能だが、全項目が現地実単価で確定したことを意味しない。"
        ),
    }


def build_construction_cost_validity_diagnostic(
    method: str,
    gfa_m2: float,
    subtotal_before_tax: float,
    benchmark: dict[str,Any],
    market_group_direct_costs: dict[str,float],
    regional_coverage: dict[str,Any],
    rc_structure_audit: dict[str,Any],
    complete_scope: dict[str,Any],
) -> dict[str,Any]:
    """PATCH 071: diagnose why a whole-building estimate may be below market benchmark.

    Audit only. No automatic price correction is applied.
    """
    gfa=max(_f(gfa_m2),0.0)
    est_m2=subtotal_before_tax/gfa if gfa>0 else 0.0
    bm=_f(benchmark.get("benchmark_jpy_per_m2"),0.0)
    gap_jpy=None
    gap_pct=None
    ratio=None
    if bm>0 and gfa>0:
        ratio=est_m2/bm
        gap_pct=(ratio-1.0)*100.0
        gap_jpy=(bm-est_m2)*gfa

    if bm<=0:
        severity="no_external_benchmark"
        judgment_ja="AZRASは木造+RCの複合工法のため、単一構造の外部ベンチマークへ強制一致させない。"
    elif ratio is not None and ratio < 0.80:
        severity="materially_below_benchmark"
        judgment_ja="外部構造別ベンチマークより20%以上低い。数量・単価・未計上工種・仮設/諸経費を優先確認する。"
    elif ratio is not None and ratio < 0.90:
        severity="below_benchmark"
        judgment_ja="外部構造別ベンチマークより10%以上低い。市場妥当性の追加確認が必要。"
    elif ratio is not None and ratio <= 1.10:
        severity="near_benchmark"
        judgment_ja="外部構造別ベンチマークの±10%範囲。なお実際の請負価格との一致を保証するものではない。"
    else:
        severity="above_benchmark"
        judgment_ja="外部構造別ベンチマークを上回る。仕様差・規模差を確認する。"

    group_total=sum(max(_f(v),0.0) for v in (market_group_direct_costs or {}).values())
    groups=[]
    for key,val in sorted((market_group_direct_costs or {}).items(), key=lambda kv:_f(kv[1]), reverse=True):
        v=max(_f(val),0.0)
        groups.append({
            "group":key,
            "cost_jpy":v,
            "share_percent":(v/group_total*100.0) if group_total>0 else 0.0,
        })

    checks=[]
    coverage=(regional_coverage or {})
    fallback_count=int(_f(coverage.get("regional_fallback_item_count"),0))
    partial_count=int(_f(coverage.get("partial_local_item_count"),0))
    if fallback_count>0:
        checks.append({
            "priority":"high",
            "issue":"regional_unit_price_coverage",
            "detail_ja":f"{fallback_count}工事項目が地域指数推定。現地実単価・見積へ置換できる余地がある。"
        })
    if partial_count>0:
        checks.append({
            "priority":"medium",
            "issue":"partial_local_price",
            "detail_ja":f"{partial_count}工事項目は一部成分のみ現地確認済み。未確認成分は地域推定。"
        })

    if not bool((complete_scope or {}).get("status")=="complete_residential_scope"):
        checks.append({
            "priority":"high",
            "issue":"building_services_scope",
            "detail_ja":"住宅設備パッケージの完成建物範囲を再確認する。"
        })

    if method=="rc_frame":
        rc_items=(rc_structure_audit or {}).get("items",{}) or {}
        for k,label in [("concrete","コンクリート"),("reinforcing_steel","鉄筋"),("formwork","型枠")]:
            item=rc_items.get(k,{}) or {}
            if item.get("status")!="present":
                checks.append({
                    "priority":"high",
                    "issue":f"rc_{k}_missing",
                    "detail_ja":f"RC主要工種「{label}」が欠落または監査不能。"
                })
        if severity in {"materially_below_benchmark","below_benchmark"}:
            checks.extend([
                {
                    "priority":"high",
                    "issue":"temporary_works_and_site_overhead",
                    "detail_ja":"RC施工の足場・揚重・仮設・現場管理等が市場請負価格レベルまで含まれているか確認する。"
                },
                {
                    "priority":"high",
                    "issue":"finishes_and_services",
                    "detail_ja":"RC躯体以外の外装・内装・建具・給排水・電気・空調の仕様/数量/単価を確認する。"
                },
            ])
    elif method=="wood_frame" and severity=="near_benchmark":
        checks.append({
            "priority":"medium",
            "issue":"benchmark_scope_difference",
            "detail_ja":"木造ベンチマークに近いが、国税庁の構造別指標は今回の3戸長屋の実際の請負見積そのものではない。"
        })

    return {
        "patch":"PATCH 071",
        "audit_only":True,
        "automatic_price_adjustment":False,
        "method":method,
        "gross_floor_area_m2":gfa,
        "software_estimate_ex_tax_jpy":subtotal_before_tax,
        "software_estimate_ex_tax_jpy_per_m2":est_m2,
        "benchmark_jpy_per_m2":benchmark.get("benchmark_jpy_per_m2"),
        "benchmark_total_for_same_gfa_jpy":bm*gfa if bm>0 and gfa>0 else None,
        "shortfall_to_benchmark_jpy":gap_jpy,
        "gap_vs_benchmark_percent":gap_pct,
        "benchmark_ratio":ratio,
        "severity":severity,
        "judgment_ja":judgment_ja,
        "direct_cost_group_total_jpy":group_total,
        "direct_cost_group_breakdown":groups,
        "priority_checks":checks,
        "benchmark_reference":benchmark,
        "source_scope_warning_ja":"国税庁の構造別工事費指標は外部妥当性監査用。今回建物の契約見積ではないため、総額を自動補正する係数には使用しない。",
    }


def calculate_construction_cost(project: dict[str, Any], database: dict[str, Any],
                                location_key: str, settings: dict[str, Any],
                                equipment_selection: dict[str, dict[str, Any]]) -> dict[str, Any]:
    module1=project.get("module_outputs",{}).get("module1")
    if not module1:
        raise ValueError("Module 1 output is required.")
    location=database["locations"][location_key]
    location=load_external_regional_cost_dataset(location)
    base_costs=database["base_unit_costs_jpy"]
    fx_jpy_per_local=_f(
        settings.get("fx_jpy_per_local_currency"),
        _f(location.get("fx_jpy_per_local_currency"))
    )
    quantities,quantity_provenance,excluded_quantities=extract_quantities(project,module1,settings)
    common_2004_enabled,common_escalation,common_market_calibration=_common_2004_price_settings(settings)
    equipment_selection,equipment_scope_policy=_normalize_residential_equipment_selection(
        project,database,equipment_selection
    )

    material_index=_f(settings.get("material_index"),location["material_index"])/100.0

    # PATCH 049: current-year, all-in unit price overrides for RC foundation
    # preparation. These are deliberately separate from the legacy 2004 basis.
    rc_foundation_unit_price_overrides={
        str(k):_f(v) for k,v in
        ((settings.get("rc_foundation_unit_price_overrides") or {}).items())
    }
    labor_index=_f(settings.get("labor_index"),location["labor_index"])/100.0
    productivity_index=max(_f(settings.get("productivity_index"),location["productivity_index"])/100.0,0.01)
    site_factor=_f(settings.get("site_factor"),1.0)
    access_factor=_f(settings.get("access_factor"),1.0)
    work_time_factor=_f(settings.get("work_time_factor"),1.0)
    condition_factor=site_factor*access_factor*work_time_factor

    lines=[]
    material_total=labor_total=equipment_total=0.0
    for key,qty in quantities.items():
        unit=base_costs.get(key)
        if not unit:
            continue
        override_current_rate=_f(rc_foundation_unit_price_overrides.get(key))
        override_applied=(
            key in {"excavation","backfill","imported_fill","soil_disposal","blinding_concrete","ground_preparation"}
            and override_current_rate>0
        )

        if override_applied:
            unit_price_source="user_confirmed_current_year_all_in_local_currency"
            # User-entered rate is a CURRENT-YEAR ALL-IN unit price.
            material_unit=override_current_rate
            labor_unit=0.0
            equipment_unit=0.0
            local_component_flags={"material":True,"labor":True,"equipment":True}
        else:
            material_unit,labor_unit,equipment_unit,unit_price_source,local_component_flags=_resolved_local_unit(
                unit,location,key,material_index,labor_index,fx_jpy_per_local
            )

        complexity={"labor":1.0,"equipment":1.0,"basis_ja":"対象外"}
        if key=="concrete":
            complexity=_concrete_installation_complexity(_construction_method(project))
            labor_unit*=complexity["labor"]
            equipment_unit*=complexity["equipment"]
        market_group=_market_cost_group(key)
        market_calibration_factor,market_calibration_source=_market_calibration_factor_2026(
            _construction_method(project),market_group,settings
        )
        if common_2004_enabled and not override_applied:
            # PATCH 072:
            # Legacy/base-database components are brought to the 2026 Aichi market
            # level by structure-aware calibration. Verified local components bypass it.
            if not local_component_flags.get("material",False):
                material_unit*=market_calibration_factor
            if not local_component_flags.get("labor",False):
                labor_unit*=market_calibration_factor
            if not local_component_flags.get("equipment",False):
                equipment_unit*=market_calibration_factor
        material_cost=qty*material_unit
        labor_cost=qty*labor_unit
        equipment_cost=qty*equipment_unit
        subtotal=material_cost+labor_cost+equipment_cost
        material_total+=material_cost
        labor_total+=labor_cost
        equipment_total+=equipment_cost
        lines.append({
            "cost_item_key":key,
            "quantity":qty,
            "unit":unit["unit"],
            "material_unit_cost":material_unit,
            "labor_unit_cost":labor_unit,
            "equipment_unit_cost":equipment_unit,
            "material_cost":material_cost,
            "labor_cost":labor_cost,
            "equipment_cost":equipment_cost,
            "line_total_before_conditions":subtotal,
            "line_total_after_conditions":subtotal*condition_factor,
            "quantity_source_type":quantity_provenance.get(key,{}).get("source_type","unknown"),
            "quantity_source":quantity_provenance.get(key,{}).get("source",""),
            "quantity_basis":quantity_provenance.get(key,{}).get("basis",""),
            "construction_method":quantity_provenance.get(key,{}).get("construction_method",_construction_method(project)),
            "installation_complexity_factor": complexity if key=="concrete" else None,
            "market_cost_group": market_group,
            "market_calibration_factor_2026":market_calibration_factor,
            "market_calibration_source_2026":market_calibration_source,
            "pricing_status": (
                "user_confirmed_current_unit_rate"
                if override_applied else unit.get("pricing_status","priced")
            ),
            "scope_note_ja": unit.get("scope_note_ja"),
            "unit_price_override_current_year_jpy":override_current_rate if override_applied else None,
            "unit_price_override_bypasses_2004_basis":True if override_applied else False
            ,"unit_price_source":unit_price_source
            ,"local_current_component_flags":local_component_flags
            ,"legacy_2004_transform_applied_to_components":{
                "material":bool(common_2004_enabled and not override_applied and not local_component_flags.get("material",False)),
                "labor":bool(common_2004_enabled and not override_applied and not local_component_flags.get("labor",False)),
                "equipment":bool(common_2004_enabled and not override_applied and not local_component_flags.get("equipment",False))
            }
            ,"regional_unit_cost_metadata":(
                (location.get("unit_costs") or {}).get(key)
                if isinstance((location.get("unit_costs") or {}).get(key),dict)
                else None
            )
        })

    direct_before_conditions=material_total+labor_total+equipment_total
    adjusted_direct=direct_before_conditions*condition_factor
    condition_adjustment=adjusted_direct-direct_before_conditions

    equipment_packages=[]
    additional_equipment=0.0
    for key,item in equipment_selection.items():
        if not bool(item.get("include")):
            continue
        cost=_f(item.get("cost"))
        if common_2004_enabled:
            equipment_market_factor,equipment_market_source=_market_calibration_factor_2026(
                _construction_method(project),"building_services_equipment",settings
            )
            cost*=equipment_market_factor
        else:
            equipment_market_factor=1.0
            equipment_market_source="market_calibration_disabled"
        additional_equipment+=cost
        db_pkg=(database.get("equipment_packages",{}) or {}).get(key,{})
        equipment_packages.append({"package_key":key,"name_ja":db_pkg.get("ja",key),
                                   "name_en":db_pkg.get("en",key),"cost":cost,
                                   "market_cost_group":"building_services_equipment",
                                   "market_calibration_factor_2026":equipment_market_factor,
                                   "market_calibration_source_2026":equipment_market_source})

    overhead_rate=_f(settings.get("overhead_rate"))/100.0
    contingency_rate=_f(settings.get("contingency_rate"))/100.0
    design_rate=_f(settings.get("design_rate"))/100.0
    tax_rate=_f(settings.get("tax_rate"))/100.0

    construction_base=adjusted_direct+additional_equipment
    overhead=construction_base*overhead_rate
    contingency=(construction_base+overhead)*contingency_rate
    design=(construction_base+overhead+contingency)*design_rate
    subtotal_before_tax=construction_base+overhead+contingency+design
    tax=subtotal_before_tax*tax_rate
    total=subtotal_before_tax+tax

    gfa=max(_f(project.get("common",{}).get("scale_gfa_m2")),1.0)
    schedule=database["schedule"]
    base_duration=gfa/max(_f(schedule["base_productivity_m2_per_month"])*productivity_index,1.0)

    # Method/workload adjustment. The common floor area is intentionally the same
    # in comparison projects, so duration must also respond to structural workload.
    method=_construction_method(project)
    concrete_m3=quantities.get("concrete",0.0)
    rebar_t=quantities.get("reinforcing_steel",0.0)
    lumber_m3=quantities.get("dimension_lumber",0.0)
    formwork_m2=quantities.get("formwork",0.0)
    structural_workload_months=(
        concrete_m3/90.0 +
        rebar_t/18.0 +
        formwork_m2/650.0 +
        lumber_m3/45.0
    )/4.0
    method_factor={"wood_frame":0.82,"azras":0.95,"rc_frame":1.10}.get(method,1.0)
    production_duration=max(base_duration*method_factor, structural_workload_months)
    duration=(
        production_duration*site_factor*access_factor*work_time_factor+
        _f(schedule["mobilization_months"])+_f(schedule["commissioning_months"])
    )

    # PATCH 049: source/basis audit for RC foundation unit prices.
    rc_foundation_unit_price_basis_audit={
        "status":"public_methodology_user_rate_required",
        "current_year_rate_overrides_jpy_per_unit":rc_foundation_unit_price_overrides,
        "public_standard_productivity":{
            "excavation_backhoe_0_28m3":{
                "backhoe_day_per_m3":0.025,
                "ordinary_worker_person_day_per_m3":0.03
            },
            "backfill_backhoe_0_28m3":{
                "backhoe_day_per_m3":0.020,
                "tamper_day_per_m3":0.031,
                "ordinary_worker_person_day_per_m3":0.07
            },
            "gravel_groundwork":{
                "material_input_m3_per_finished_m3":1.1,
                "ordinary_worker_person_day_per_m3":0.2
            }
        },
        "public_source_urls":[
            "https://www.mlit.go.jp/gobuild/content/001733130.pdf",
            "https://www.mlit.go.jp/gobuild/content/001733132.pdf",
            "https://www.pref.aichi.jp/soshiki/kensetsu-kikaku/kenchikusekisan.html"
        ],
        "nonpublic_or_project_specific_items_ja":[
            "愛知県の主要資材・市場単価は物価資料掲載のため非公表。",
            "残土処分は運搬距離・処分先・受入条件に依存。",
            "したがって完成単価は0円を初期値とし、確認された現在年単価のみ入力して反映する。"
        ],
        "price_adjustment_applied":any(v>0 for v in rc_foundation_unit_price_overrides.values()),
    }

    # PATCH 048: preserve RC earthwork/groundwork quantity calculation for audit.
    _m1_048=(project.get("module_outputs",{}) or {}).get("module1",{}) or {}
    _p048=_m1_048.get("profile",{}) or {}
    _dp048=((_m1_048.get("drawing_analysis",{}) or {}).get("profile",{}) or {})
    if (_dp048.get("construction",{}) or {}).get("concrete_volume_m3"):
        _p048=dict(_p048)
        _mc048=dict(_p048.get("construction",{}) or {})
        _mc048.update(_dp048.get("construction",{}) or {})
        _p048["construction"]=_mc048
        if _dp048.get("geometry"):
            _p048["geometry"]=_dp048.get("geometry")
    rc_foundation_earthwork_quantity_audit=(
        _foundation_earthwork_geometry(_p048,_construction_method(project),str(settings.get("excavated_soil_stockpile_mode") or "no_stockpile"))
    )
    # PATCH 052: generic soil-balance audit for all three comparison methods.
    # Kept separate from the historical rc_* field for backward compatibility.
    foundation_soil_balance_audit=_foundation_soil_balance_audit(
        rc_foundation_earthwork_quantity_audit,_construction_method(project)
    )

    # PATCH 047: audit RC-specific scopes that may be missing or embedded.
    rc_specific_scope_audit=_rc_specific_scope_audit(
        lines,equipment_packages,_construction_method(project)
    )

    # PATCH 046: preserve component formwork calculation for audit.
    _m1=(project.get("module_outputs",{}) or {}).get("module1",{}) or {}
    _profile=_m1.get("profile",{}) or {}
    _drawing_profile=((_m1.get("drawing_analysis",{}) or {}).get("profile",{}) or {})
    if (_drawing_profile.get("construction",{}) or {}).get("concrete_volume_m3"):
        _profile=dict(_profile)
        _merged=dict(_profile.get("construction",{}) or {})
        _merged.update(_drawing_profile.get("construction",{}) or {})
        _profile["construction"]=_merged
        if _drawing_profile.get("geometry"):
            _profile["geometry"]=_drawing_profile.get("geometry")
    rc_frame_formwork_geometry=(
        _rc_frame_formwork_geometry(_profile)
        if _construction_method(project)=="rc_frame" else None
    )

    # PATCH 045: RC structure market audit. Diagnostic only.
    rc_structure_market_audit=_rc_structure_market_audit(lines,_construction_method(project))
    if rc_frame_formwork_geometry and rc_structure_market_audit.get("status")!="not_applicable":
        rc_structure_market_audit["formwork_geometry"]=rc_frame_formwork_geometry
        fw_item=(rc_structure_market_audit.get("items",{}) or {}).get("formwork",{})
        fw_item["quantity_confidence"]="medium_planning_geometry"
        fw_item["warning_ja"]="PATCH 046でm3×5.0推定を廃止し、RC壁・柱・梁・スラブ・独立基礎・地中梁の部位別形状から算定。施工図数量ではないため最終見積時は確認が必要。"

    # PATCH 043: market benchmark audit. Diagnostic only; no price adjustment.
    market_group_direct_costs={}
    for row in lines:
        grp=row.get("market_cost_group") or "other"
        market_group_direct_costs[grp]=market_group_direct_costs.get(grp,0.0)+_f(row.get("line_total_after_conditions"))

    if additional_equipment>0:
        market_group_direct_costs["building_services_equipment"]=additional_equipment
    benchmark=_market_benchmark_reference(_construction_method(project))
    software_ex_tax_per_m2=subtotal_before_tax/gfa if gfa>0 else 0.0
    benchmark_m2=benchmark.get("benchmark_jpy_per_m2")
    benchmark_gap_pct=None
    benchmark_ratio=None
    if benchmark_m2:
        benchmark_ratio=software_ex_tax_per_m2/benchmark_m2
        benchmark_gap_pct=(software_ex_tax_per_m2/benchmark_m2-1.0)*100.0

    regional_unit_cost_coverage_audit=build_regional_unit_cost_coverage_audit(
        location,base_costs,lines
    )

    construction_cost_validity_diagnostic=build_construction_cost_validity_diagnostic(
        _construction_method(project),
        gfa,
        subtotal_before_tax,
        benchmark,
        market_group_direct_costs,
        regional_unit_cost_coverage_audit,
        rc_structure_market_audit,
        {
            **equipment_scope_policy,
            "included_packages":[x.get("package_key") for x in equipment_packages],
            "additional_equipment_cost_jpy":additional_equipment,
            "status":"complete_residential_scope" if (
                equipment_scope_policy.get("residential_project") and
                all(k in [x.get("package_key") for x in equipment_packages]
                    for k in equipment_scope_policy.get("standard_packages",[]))
            ) else "check_scope"
        }
    )

    # PATCH_208: Evaluation/Planning cost is not modified by retired
    # 04 Feasibility compatibility data.  Current total/duration are authoritative.
    adjusted_total=total
    adjusted_duration=duration

    return {
        "version":"9.4",
        "module":"module5",
        "location_profile":location_key,
        "external_regional_cost_dataset_status":location.get("external_dataset_load_status"),
        "external_regional_cost_dataset_path":location.get("external_dataset_path"),
        "external_regional_cost_dataset_selected_data_date":location.get("external_dataset_selected_data_date"),
        "external_regional_cost_dataset_candidate_count":location.get("external_dataset_candidate_count"),
        "external_regional_cost_dataset_available_versions":location.get("external_dataset_available_versions"),
        "unit_cost_dataset_audit":evaluate_unit_cost_dataset_freshness(location),
        "regional_unit_cost_coverage_audit":regional_unit_cost_coverage_audit,
        "construction_cost_validity_diagnostic":construction_cost_validity_diagnostic,
        "regional_cost_workflow_status":(
            (location.get("module5_cost_closeout_patch070") or {}).get("workflow_status")
        ),
        "location_pricing_mode":location.get("pricing_mode"),
        "location_pricing_status":location.get("pricing_status"),
        "fx_jpy_per_local_currency":fx_jpy_per_local,
        "currency":location["currency"],
        "cost_year":int(_f(settings.get("cost_year"),location["year"])),
        "exchange_rate_applied":False,
        "settings":{
            **settings,
            "condition_factor":condition_factor
        },
        "construction_method":_construction_method(project),
        "rc_foundation_unit_price_basis_audit":rc_foundation_unit_price_basis_audit,
        "rc_foundation_earthwork_quantity_audit":rc_foundation_earthwork_quantity_audit,
        "foundation_soil_balance_audit":foundation_soil_balance_audit,
        "rc_specific_scope_audit":rc_specific_scope_audit,
        "rc_frame_formwork_geometry":rc_frame_formwork_geometry,
        "rc_structure_market_audit":rc_structure_market_audit,
        "complete_building_scope":{
            **equipment_scope_policy,
            "included_packages":[x.get("package_key") for x in equipment_packages],
            "additional_equipment_cost_jpy":additional_equipment,
            "status":"complete_residential_scope" if (
                equipment_scope_policy.get("residential_project") and
                all(k in [x.get("package_key") for x in equipment_packages]
                    for k in equipment_scope_policy.get("standard_packages",[]))
            ) else "check_scope"
        },
        "market_benchmark_audit":{
            "status":"audit_only_no_price_adjustment",
            "reference":benchmark,
            "software_estimate_ex_tax_jpy":subtotal_before_tax,
            "software_estimate_ex_tax_jpy_per_m2":software_ex_tax_per_m2,
            "software_estimate_ex_tax_jpy_per_tsubo":software_ex_tax_per_m2*3.3057851239669422,
            "benchmark_ratio":benchmark_ratio,
            "gap_vs_benchmark_percent":benchmark_gap_pct,
            "direct_cost_group_breakdown_jpy":market_group_direct_costs,
            "bcci_2026_trend_reference":{
                "source":"Construction Price Research Association, BCCI March 2026",
                "rc_collective_housing_yoy_percent":5.5,
                "wood_housing_yoy_percent":5.9,
                "use_policy_ja":"2026年の上昇方向を確認する参考値。2025基準額へ機械的に掛けて総額を強制補正しない。"
            },
            "calibration_policy_ja":[
                "2×6は木造市場ベンチマークに対して独立監査する。",
                "RCラーメンはRC市場ベンチマークに対して独立監査する。",
                "AZRASには独自の目標坪単価を設定しない。",
                "AZRASのRC工種にはRC側で検証済み単価、木造工種には2×6側で検証済み単価、共通工種には共通単価を適用する。",
                "2004年AZRAS実績3,450万円はHistorical Referenceとして保持し、現在価格の直接校正には使用しない。"
            ]
        },
        "insulation_cost_linkage":{
            "phenolic_foam_quantity_m3":quantities.get("phenolic_foam",0.0),
            "xps_quantity_m3":quantities.get("xps",0.0),
            "phenolic_foam_in_cost_lines":any(x.get("cost_item_key")=="phenolic_foam" for x in lines),
            "xps_in_cost_lines":any(x.get("cost_item_key")=="xps" for x in lines),
            "status":"ok" if (
                quantities.get("phenolic_foam",0.0)>0 and quantities.get("xps",0.0)>0 and
                any(x.get("cost_item_key")=="phenolic_foam" for x in lines) and
                any(x.get("cost_item_key")=="xps" for x in lines)
            ) else "check_required",
            "note_ja":"Module 1の部位別断熱数量をModule 5工事費へ連携。数量拾い行が欠ける場合はprofile.assembliesと部位面積から補完する。"
        },
        "foundation_quantity_linkage":{
            "status":"ok" if not (
                _construction_method(project)=="wood_frame" and
                (((module1.get("drawing_analysis",{}) or {}).get("profile",{}) or {}).get("construction",{}) or {}).get("foundation_geometry",{}).get("status")=="matched_dimensioned_plan"
            ) or (
                quantities.get("concrete",0.0)>0 and
                quantities.get("formwork",0.0)>0 and
                quantities.get("reinforcing_steel",0.0)>0
            ) else "check_required",
            "concrete_m3":quantities.get("concrete",0.0),
            "reinforcing_steel_t":quantities.get("reinforcing_steel",0.0),
            "formwork_m2":quantities.get("formwork",0.0),
            "concrete_source":quantity_provenance.get("concrete",{}).get("source",""),
            "formwork_source":quantity_provenance.get("formwork",{}).get("source",""),
            "note_ja":"Module 1で認識した2×6布基礎実形状を旧保存数量より優先してModule 5へ連携する。"
        },
        "scope_overlap_audit":{
            "interior_finish":{
                "status":"resolved_by_scope_definition",
                "fallback_quantity_m2":quantities.get("interior_finish",0.0),
                "gypsum_board_separately_costed":quantities.get("gypsum_board",0.0)>0,
                "definition_ja":"内装仕上は最終仕上のみ。石膏ボード等の下地を含めないため二重計上しない。",
                "source_quality":"planning_fallback" if quantity_provenance.get("interior_finish",{}).get("source_type")=="method_fallback_estimate" else "drawing_quantity"
            },
            "external_finish":{
                "status":"resolved_by_scope_definition",
                "rc_finish_m2":quantities.get("external_finish_rc",0.0),
                "timber_finish_m2":quantities.get("external_finish_timber",0.0),
                "phenolic_foam_separately_costed":quantities.get("phenolic_foam",0.0)>0,
                "structural_plywood_separately_costed":quantities.get("structural_plywood",0.0)>0,
                "definition_ja":"外装仕上は表面仕上のみ。断熱材・構造用合板を含めないため二重計上しない。"
            },
            "formwork":{
                "status":"geometry_based" if _construction_method(project)=="azras" and quantity_provenance.get("formwork",{}).get("source_type")=="method_fallback_estimate" else "planning_fallback_or_drawing",
                "quantity_m2":quantities.get("formwork",0.0),
                "basis":quantity_provenance.get("formwork",{}).get("basis",""),
                "definition_ja":"コンクリート材料・打設労務とは別の型枠工種。AZRASは単純形状を使った幾何推定を優先。"
            }
        },
        "concrete_installation_complexity":{
            **_concrete_installation_complexity(_construction_method(project)),
            "applies_to":"concrete labor and equipment only",
            "material_factor":1.0,
            "note_ja":"生コン材料単価は全工法共通。施工難易度差は労務・機械のみに反映。型枠は別工種で数量差を反映。"
        },
        "market_calibration_2026":{
            **MARKET_CALIBRATION_2026,
            "selected_method":_construction_method(project),
            "wood_factor_applied_to_fallback_components":_market_calibration_factor_2026(
                "wood_frame","wood_structure",settings
            )[0],
            "rc_factor_applied_to_fallback_components":_market_calibration_factor_2026(
                "rc_frame","rc_structure",settings
            )[0],
            "known_unpriced_foundation_items":[
                key for key in (
                    "excavation","backfill","imported_fill",
                    "soil_disposal","blinding_concrete","ground_preparation"
                )
                if key in quantities and
                all(abs(_f(x))<1e-12 for x in (
                    (base_costs.get(key) or {}).get("material"),
                    (base_costs.get(key) or {}).get("labor"),
                    (base_costs.get(key) or {}).get("equipment"),
                ))
            ],
            "provisional_note_ja":(
                "根切り・埋戻し・残土・捨てコン・砕石等で確認単価が0円の項目は、"
                "数量は計上しても金額未計上。市場校正後も別途確認単価の登録が必要。"
            ),
        },
        "common_price_basis":{
            "enabled":common_2004_enabled,
            "base_year":2004,
            "reference_region":"Japan / Nagoya",
            "cost_escalation_factor_2004_to_target":common_escalation,
            "common_market_calibration_factor":common_market_calibration,
            "applied_identically_to_all_methods":True,
            "azras_actual_2004_reference_jpy_ex_tax":34500000.0,
            "azras_actual_reference_only_not_direct_replacement":True,
            "note_ja":"全工法に同一の2004年価格基準・市場校正係数・評価年上昇係数を適用。AZRAS実績3,450万円は共通市場水準の校正基準であり、AZRASだけの総額置換には使用しない。"
        },
        "quantities":quantities,
        "quantity_provenance":quantity_provenance,
        "excluded_quantities":excluded_quantities,
        "cost_lines":lines,
        "equipment_packages":equipment_packages,
        "summary":{
            "direct_material_cost":material_total*condition_factor,
            "direct_labor_cost":labor_total*condition_factor,
            "direct_equipment_cost":equipment_total*condition_factor,
            "direct_cost_before_conditions":direct_before_conditions,
            "condition_adjustment":condition_adjustment,
            "adjusted_direct_cost":adjusted_direct,
            "additional_equipment_cost":additional_equipment,
            "overhead_cost":overhead,
            "contingency_cost":contingency,
            "design_supervision_cost":design,
            "subtotal_before_tax":subtotal_before_tax,
            "tax_amount":tax,
            "base_total_construction_cost":total,
            "total_construction_cost":adjusted_total,
            "cost_per_m2":adjusted_total/gfa,
            "base_estimated_construction_duration_months":duration,
            "estimated_construction_duration_months":adjusted_duration
        },
        "status":"provisional_planning_comparison",
        "disclaimer":"Planning comparison only; replace unit costs with current verified regional quotations."
    }
