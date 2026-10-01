
from __future__ import annotations
from typing import Any
from core.project_coordinator import require_current_module_output, module_output_fingerprint, module1_cost_dependency_fingerprint
import math
import re

TAKEOFF_MAP = {
    "コンクリート合計":"concrete",
    "コンクリート":"concrete",
    "鉄筋":"reinforcing_steel",
    "構造用鉄骨":"structural_steel",
    "2×6・一般構造木材":"dimension_lumber",
    "2×6・一般木材":"dimension_lumber",
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
    "クロス張り":"interior_finish",
    "外装仕上面積":"external_finish",
    "型枠":"formwork",
    "型枠工事":"formwork",
    "型枠面積":"formwork"
}

# PATCH 609: canonical physical unit contract for every direct cost key.
# A quantity whose dimension does not match the unit-cost dimension is never
# multiplied by that rate. This prevents e.g. labour/day or count values from
# being interpreted as tonnes, m2, or m3.
COST_KEY_CANONICAL_UNIT = {
    "backfill":"m3","blinding_concrete":"m3","ceiling_glass_wool":"m3",
    "ceiling_lgs":"m2","clt":"m3","concrete":"m3","dimension_lumber":"m3",
    "doors":"m2","excavation":"m3","external_finish":"m2",
    "external_finish_rc":"m2","external_finish_timber":"m2","formwork":"m2",
    "glass":"m2","ground_preparation":"m3","gypsum_board":"m2",
    "imported_fill":"m3","interior_finish":"m2","louver":"m2","oa_floor":"m2",
    "phc_pile":"m","phenolic_foam":"m3","reinforcing_steel":"t",
    "roof_glass_wool":"m3","roofing":"m2","shutter":"m2","soil_disposal":"m3",
    "structural_plywood":"m2","structural_steel":"t","tempered_glass":"m2",
    "vapor_barrier":"m2","xps":"m3",
    # PATCH_039: envelope/finish scopes that Module 1 already quantifies but
    # that had no registered Module 5 cost key, so they could never be priced.
    # ceiling_insulation_area is deliberately an AREA key and is mutually
    # exclusive with the existing volume key ceiling_glass_wool (see
    # extract_quantities); registering both for the same building would double
    # count the same physical layer.
    "ceiling_insulation_area":"m2","parapet_coping":"m","rainwater_gutter":"m",
}
def _normalize_physical_unit(unit: Any) -> str:
    s=str(unit or "").strip().lower().replace("㎡","m2").replace("m²","m2").replace("㎥","m3").replace("m³","m3")
    aliases={"ton":"t","tons":"t","tonne":"t","tonnes":"t","meter":"m","meters":"m","metre":"m","metres":"m"}
    return aliases.get(s,s)

def _cost_key_unit_compatible(key: str | None, unit: Any) -> bool:
    expected=COST_KEY_CANONICAL_UNIT.get(str(key or ""))
    if not expected:
        return False
    return _normalize_physical_unit(unit)==expected


def _takeoff_cost_key(row: dict[str,Any]) -> str | None:
    """PATCH 436: conservative bridge from detailed Module 1 rows to Module 5 trades.

    Exact legacy labels remain authoritative.  Detailed structural rows are
    recognized only when their physical unit makes the mapping unambiguous.
    Component concrete volumes may be summed; steel/rebar are admitted only as
    explicit total/roll-up mass rows so member/detail rows are never double-counted.
    """
    item=str(row.get("item") or "").strip()
    exact=TAKEOFF_MAP.get(item)
    if exact:
        return exact if _cost_key_unit_compatible(exact, row.get("unit")) else None
    low=item.lower()
    unit=str(row.get("unit") or "").strip().lower()
    material_key=str(row.get("material_key") or "").strip().lower()
    cost_key=str(row.get("cost_key") or "").strip().lower()

    # PATCH_581: a human-confirmed user-added scope may carry an explicit Cost Key.
    # This is the formal bridge created by the in-app review workflow. It is used
    # only for an adopted human quantity; without a key the row remains visible as
    # unpriced/unmapped and is never silently assigned a zero-value price.
    if bool(row.get("user_added_item")) and bool(row.get("downstream_quantity_eligible")):
        explicit=cost_key or material_key
        if explicit and _cost_key_unit_compatible(explicit, row.get("unit")):
            return explicit

    # PATCH 576: mandatory-scope coverage rows carry an explicit material key but
    # start unresolved. Once a human confirms the quantity, the downstream gate
    # opens and this explicit material key becomes the Module 5 cost bridge.
    if bool(row.get("coverage_gap_required")) and material_key in {
        "concrete","dimension_lumber","reinforcing_steel","structural_steel",
        "structural_plywood","gypsum_board","ceiling_lgs"
    } and _cost_key_unit_compatible(material_key, row.get("unit")):
        return material_key

    # Concrete component rows are additive physical volumes.  This covers
    # F1 pile-head foundations, slab-on-ground and FG beam concrete without
    # requiring every drawing-specific label in TAKEOFF_MAP.
    if unit in {"m3","m³"} and ("コンクリート" in item or "concrete" in low):
        return "concrete"
    # PATCH_534/201: rational yellow structural-timber planning rows are physical
    # quantities and must reach both cost and LCA.  Keep the bridge narrow so
    # exterior timber finishes are not mistaken for structural framing.
    if unit in {"m3","m³"} and (
        "構造木材" in item or "structural timber" in low or "timber infill" in low
    ):
        return "dimension_lumber"
    if unit in {"m3","m³"} and (
        ("砕石" in item and any(tok in item for tok in ("床下","地業","基礎")))
        or ("crushed stone" in low and any(tok in low for tok in ("ground","foundation","underfloor")))
    ):
        return "ground_preparation"

    # Only explicit total/roll-up mass rows may represent the whole steel trade.
    # Individual member theoretical weights and connection plates stay outside
    # this bridge and are governed by the final steel contract.
    # PATCH_535/202: RC non-structural LGS partitions are real permanent steel.
    # Admit only the explicit total mass owner; member-length rows remain audit evidence.
    if (unit in {"t","ton","tons","tonne","tonnes"} and material_key=="structural_steel"
            and "lgs" in low and "partition" in low and "total" in low):
        return "structural_steel"

    if unit in {"t","ton","tons","tonne","tonnes"}:
        if (("構造用鉄骨" in item or "structural steel" in low)
            and any(tok in low for tok in ("総重量","total","rollup","roll-up","provisional"))):
            return "structural_steel"
        # PATCH 471: Module 1's canonical English reinforcement summary row is
        # named e.g. "AZRAS reinforcement schedule theoretical weight total".
        # PATCH 470's planning fallback could not see that row because this bridge
        # recognized "reinforcing steel" / "rebar" but not the canonical word
        # "reinforcement".  Keep the existing total/roll-up + tonne gates so
        # individual bar/detail rows still cannot be double-counted.
        # PATCH_008: the structural_steel gate above already accepts
        # "provisional" (for AZRAS's "structural steel (provisional total
        # weight)" row), but this reinforcing_steel gate did not, even though
        # Module 1 generates the exact same kind of whole-scope row here:
        # "reinforcement (provisional general specification)". Without this,
        # that row could never bridge into Module 5's "reinforcing_steel" cost
        # line via this function, so it always showed up a second time in the
        # quantity/cost coverage audit as a separate "blocked" line -- with
        # whatever quantity happened to be stored on it -- even after Module 5
        # had already priced reinforcing steel correctly through its own,
        # independent quantity calculation. This is exactly the "鉄筋 appears
        # twice with two different numbers" symptom.
        if (("鉄筋" in item or "reinforcing steel" in low or "rebar" in low or "reinforcement" in low)
            and any(tok in low for tok in ("総重量","合計","total","rollup","roll-up","provisional"))):
            return "reinforcing_steel"

    # PATCH 437: safe detailed-finish bridges.  These are intentionally
    # narrow so a gross wall/roof area and its component layers are not both
    # costed.  Material-specific exterior finish areas can be additive.
    if unit in {"m2","m²"} and ("石膏ボード" in item or ("PB" in item and "内装" in item)):
        return "gypsum_board"
    if unit in {"m3","m³"} and "砕石" in item:
        return "ground_preparation"
    if ("PHC杭" in item or "phc pile" in low) and unit in {"m","meter","meters","metre","metres"} and any(x in item for x in ("総延長","延長")):
        return "phc_pile"
    if ("シャッター" in item or "shutter" in low) and unit in {"m2","m²"}: return "shutter"
    if ("ガラリ" in item or "louver" in low or item.startswith("AG-1")) and unit in {"m2","m²"}: return "louver"
    if ("屋根グラスウール" in item or ("glass wool" in low and "roof" in low)) and unit in {"m3","m³"}: return "roof_glass_wool"
    if ("天井グラスウール" in item or ("glass wool" in low and "ceiling" in low)) and unit in {"m3","m³"}: return "ceiling_glass_wool"
    if ("透明強化ガラス" in item or "tempered glass" in low) and unit in {"m2","m²"}: return "tempered_glass"
    if ("OAフロア" in item or "oa floor" in low) and unit in {"m2","m²"}: return "oa_floor"
    if ("防湿" in item or "vapor barrier" in low or "vapour barrier" in low) and unit in {"m2","m²"}: return "vapor_barrier"
    # PATCH 477: ceiling LGS is a real substrate trade, distinct from the
    # final interior-finish scope.  Admit only an explicit area quantity.
    if (("天井下地" in item and "LGS" in item.upper()) or "ceiling lgs" in low) and unit in {"m2","m²"}:
        return "ceiling_lgs"

    # PATCH_039: four scopes that Module 1 quantifies but Module 5 could not
    # price, so they stayed permanently red in the coverage audit and were
    # never sent to the AI Cost Provider.  Each bridge is deliberately narrow:
    # only an explicit whole-scope control row may become a monetary owner, so
    # a per-mark detail row (AW-1, AW-2, ...) still resolves through
    # _quantity_cost_parent_scope instead of being added a second time.
    if unit in {"m2","m²"} and (
        ("外部窓ガラス" in item or "exterior window glass" in low)
        and ("合計" in item or "total" in low)
    ):
        return "glass"
    if unit in {"m2","m²"} and (
        "天井グラスウール" in item
        or ("ceiling" in low and "glass wool" in low)
        or ("ceiling" in low and "insulation" in low and "area" in low)
    ):
        return "ceiling_insulation_area"
    if unit in {"m","ｍ","meter","meters","metre","metres"} and (
        "笠木" in item or "parapet coping" in low or "coping length" in low
    ):
        return "parapet_coping"
    if unit in {"m","ｍ","meter","meters","metre","metres"} and (
        "軒樋" in item or "竪樋" in item or "雨樋" in item
        or "eaves gutter" in low or "rainwater gutter" in low
        or "downpipe" in low or "downspout" in low
    ):
        return "rainwater_gutter"
    return None

def _f(v: Any, default: float=0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default

def _module1_rebar_planning_quantity(module1: dict[str, Any]) -> tuple[float, dict[str, Any]]:
    """Return a planning-only reinforcing-steel mass directly from Module 1 rows.

    PATCH 472 deliberately stops depending on text-to-cost-key bridging for this
    recovery path. Module 1 already tags reinforcement rows structurally with
    material_key/category/rebar_component, so those fields are the primary
    contract. Final reinforcement remains blocked when Module 1 says so; the
    returned quantity is only for the Approximate Cost Provider / business plan.
    """
    takeoff=(module1.get("quantity_takeoff") or {}) if isinstance(module1,dict) else {}
    rows=takeoff.get("rows") or []
    candidates=[]
    for row in rows:
        if not isinstance(row,dict):
            continue
        material_key=str(row.get("material_key") or "").strip().lower()
        category=str(row.get("category") or "").strip().lower()
        component=str(row.get("rebar_component") or "").strip().lower()
        item=str(row.get("item") or "").strip()
        low=item.lower()
        if not (material_key=="reinforcing_steel" or "reinforcement" in category or "reinforcing steel" in category or component
                or "鉄筋" in item or "reinforcement" in low or "reinforcing steel" in low or "rebar" in low):
            continue
        eligible,_reason=_quantity_row_cost_eligibility(row)
        if not eligible:
            continue
        unit=str(row.get("unit") or "").strip().lower()
        raw=_f(row.get("accepted_quantity",row.get("quantity")))
        if raw<=0 or unit not in {"t","ton","tons","tonne","tonnes","kg"}:
            continue
        qty_t=raw/1000.0 if unit=="kg" else raw
        source_mode=str(row.get("source_mode") or "").lower()
        # Explicit whole-scope summaries are preferred over component/detail rows.
        is_summary=(
            any(tok in low for tok in ("theoretical weight total","総重量","合計"," total","total "))
            or "summary" in source_mode
        )
        is_general_spec=("provisional general specification" in low or "暫定一般仕様" in item)
        _spec=row.get("provisional_general_spec") if isinstance(row.get("provisional_general_spec"),dict) else {}
        candidates.append({
            "quantity_t":qty_t,"item":item,"is_summary":is_summary,
            "is_general_spec":is_general_spec,"component":component,
            "source_mode":str(row.get("source_mode") or ""),
            "rebar_rate_kg_per_m3":_f(_spec.get("parameter_value")) if str(_spec.get("parameter_name") or "") == "rebar_rate_kg_per_m3" else 0.0,
        })
    summaries=[x for x in candidates if x["is_summary"]]
    if summaries:
        best=max(summaries,key=lambda x:x["quantity_t"])
        return best["quantity_t"],{
            "source":"Module 1 tagged reinforcement summary row",
            "basis":f"Planning-only reinforcement quantity from Module 1 summary: {best['item']}",
            "source_item":best["item"],"selection":"largest_positive_tagged_summary",
        }
    general=[x for x in candidates if x["is_general_spec"]]
    if general:
        best=max(general,key=lambda x:x["quantity_t"])
        return best["quantity_t"],{
            "source":"Module 1 tagged provisional reinforcement row",
            "basis":f"Planning-only reinforcement quantity from Module 1 provisional general specification: {best['item']}",
            "source_item":best["item"],"selection":"largest_positive_tagged_provisional_row",
            "rebar_rate_kg_per_m3":best.get("rebar_rate_kg_per_m3") or 0.0,
        }
    # If only physical mass components exist, use their sum only when every
    # selected row is explicitly tagged as a rebar component. This is a planning
    # subtotal, never a final reinforcement contract.
    component_rows=[x for x in candidates if x["component"]]
    if component_rows:
        qty=sum(x["quantity_t"] for x in component_rows)
        if qty>0:
            return qty,{
                "source":"Module 1 tagged reinforcement component rows",
                "basis":"Planning-only sum of explicitly tagged reinforcement mass components; final increments may remain unresolved",
                "source_items":[x["item"] for x in component_rows],
                "selection":"sum_explicit_tagged_mass_components",
            }
    return 0.0,{"source":"Module 1 reinforcement rows","basis":"No positive tagged reinforcement mass row available"}

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
        "glass","gypsum_board","roofing","doors","interior_finish","external_finish",
        "phenolic_foam","xps",
        "external_finish_rc","external_finish_timber",
        # PATCH 051: foundation preparation is a comparable scope for all
        # three construction methods, not RC-frame-only.
        "excavation","backfill","imported_fill","soil_disposal","blinding_concrete","ground_preparation",
        "phc_pile","shutter","louver","roof_glass_wool","ceiling_glass_wool","tempered_glass","oa_floor","vapor_barrier","ceiling_lgs",
        # PATCH_039: comparable across every construction method.
        "ceiling_insulation_area","parapet_coping","rainwater_gutter"
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
    return common|{"concrete","reinforcing_steel","formwork","dimension_lumber","structural_steel","clt","external_finish"}

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

def _quantity_row_cost_eligibility(row: dict[str,Any]) -> tuple[bool,str]:
    """PATCH 372: decide whether a Module 1 row may enter Module 5 direct cost.

    Current Module 1 rows carry an explicit ``downstream_quantity_eligible`` gate.
    Old Project JSON files may predate that field, so legacy compatibility is kept
    unless the saved row explicitly says audit-only/spec-only/unresolved.  MEP rows
    have an additional monetary-ownership gate: while Module 5 owns the equipment
    package, equipment detail must never be admitted as direct cost.
    """
    if not isinstance(row,dict):
        return False,"invalid_row"

    # MEP package/detail double-count invariant.  This is intentionally checked
    # before TAKEOFF_MAP so future map additions cannot accidentally bypass it.
    if bool(row.get("mep_trade")) and not bool(row.get("downstream_direct_cost_eligible")):
        return False,"mep_detail_blocked_by_module5_package_ownership"

    # PATCH 531: the user-visible quantity certainty is the final adoption rule.
    # A yellow provisional/assumed numeric quantity MUST participate in planning
    # calculations even when an older Project JSON still carries a stale blocked
    # downstream flag.  Red/unknown/spec/audit rows remain excluded.
    downstream_use=str(row.get("downstream_use") or "").strip().lower()
    display=str(row.get("quantity_display_state") or "").strip().lower()
    adoption=str(row.get("quantity_adoption_class") or "").strip().lower()
    # PATCH_534: audit ownership has absolute precedence.  A superseded row may
    # still contain a rational provisional number, but it must never be revived by
    # the legacy yellow-compatibility bridge and double-counted.
    if downstream_use.startswith("audit") or display=="audit_only_neutral" or adoption=="audit_only" or str(row.get("aggregation_role") or "").strip().lower()=="audit_only":
        return False,"audit_only_quantity_owner"
    try:
        _q=float(row.get("accepted_quantity", row.get("quantity")))
        _numeric=math.isfinite(_q) and _q >= 0.0
    except Exception:
        _numeric=False
    if _numeric and (display=="assumed_yellow" or adoption=="assumed"):
        return True,"yellow_provisional_quantity_adopted_patch531"

    # PATCH 532 legacy migration: old Project JSONs can carry unknown_red/unknown
    # even though the row itself is an explicit rational provisional calculation.
    # Admit only clearly-labelled provisional-general-spec numeric rows.  Do not
    # widen this to generic numeric unresolved rows, conflicts, or AI review rows.
    _status=str(row.get("evidence_status") or row.get("status") or "").strip().lower()
    _blob=" ".join(str(row.get(k) or "") for k in ("item","source_mode","formula","evidence")).lower()
    _legacy_rational=(
        _numeric
        and any(tok in _blob for tok in ("provisional general specification","暫定一般仕様","provisional value"))
        and _status not in {"conflict","conflicting","unreadable"}
    )
    if _legacy_rational:
        return True,"legacy_rational_provisional_adopted_patch532"

    # Explicit red/unknown and hard unresolved states are not adopted.
    if display in {"unknown_red","spec_only_neutral","audit_only_neutral"} or adoption in {"unknown","unresolved","spec_only","audit_only","blocked"}:
        return False,"non_adoptable_quantity_certainty"
    if downstream_use in {"blocked_until_resolved", "hold_for_human_review"}:
        return False,f"hard_downstream_block:{downstream_use}"

    if "downstream_quantity_eligible" in row:
        return (bool(row.get("downstream_quantity_eligible")),
                "explicit_module1_downstream_quantity_gate" if bool(row.get("downstream_quantity_eligible"))
                else "explicit_module1_downstream_quantity_block")

    # Legacy compatibility: reject only states that are explicitly non-adoptable.
    adoption=str(row.get("quantity_adoption_class") or "").strip().lower()
    if adoption in {"audit_only","spec_only","unknown","unresolved","blocked"}:
        return False,f"legacy_quantity_adoption_class:{adoption}"
    display=str(row.get("quantity_display_state") or "").strip().lower()
    if display in {"unknown_red","spec_only_neutral"}:
        return False,f"legacy_quantity_display_state:{display}"
    if downstream_use.startswith("audit") or downstream_use in {"scope_evidence_only","quantity_basis_only"}:
        return False,f"legacy_downstream_use:{downstream_use}"

    return True,"legacy_compatible_no_explicit_block"




def _canonical_concrete_component(row: dict[str,Any]) -> str:
    """PATCH 530: identify one physical concrete component across legacy/AI rows.

    Module 1 may retain a generic profile row, a current-PDF row and a human-readable
    total at the same time.  They are audit representations of the same concrete, not
    additive quantities.  This classifier lets downstream cost/LCA bridges select one
    owner per physical component while preserving every row for audit.
    """
    item=str(row.get("item") or "").strip().lower().replace("　"," ")
    formula=str(row.get("formula") or row.get("canonical_formula") or "").strip().lower()
    blob=" ".join((item,formula))
    if any(tok in blob for tok in (
        "foundation / slab-on-grade concrete","slab_foundation","ベタ基礎コンクリート",
        "基礎・土間コンクリート","土間コンクリート","mat foundation"
    )):
        return "foundation_slab"
    if any(tok in blob for tok in ("azras外周rc壁","external rc wall","perimeter rc wall","gable-end rc wall")):
        return "external_rc_wall"
    if any(tok in blob for tok in ("azras internal rc wall","internal rc wall","内部rc壁")):
        return "internal_rc_wall"
    if "rc wall concrete" in blob or "rc壁コンクリート" in blob:
        return "rc_wall"
    if "column" in blob or "柱コンクリート" in blob:
        return "columns"
    if "beam" in blob or "梁コンクリート" in blob:
        return "beams"
    if any(tok in blob for tok in ("upper_slabs","上階・屋根スラブ","upper slab","roof slab")):
        return "upper_slabs"
    if any(tok in blob for tok in ("underground_foundations","独立基礎・地中梁","isolated footing","grade beam")):
        return "underground_foundations"
    # Keep genuinely distinct unclassified detail rows separate.
    return "other:"+re.sub(r"\s+"," ",item)


def _concrete_owner_priority(row: dict[str,Any]) -> tuple[int,float]:
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
    """PATCH 530: return concrete once per physical component, never summary+detail."""
    takeoff=(module1.get("quantity_takeoff") or {}) if isinstance(module1,dict) else {}
    rows=takeoff.get("rows") or []
    details=[]
    summaries=[]
    excluded=[]
    for row in rows:
        if not isinstance(row,dict):
            continue
        group=str(row.get("aggregation_group") or "").strip().lower()
        mkey=str(row.get("material_key") or "").strip().lower()
        key=_takeoff_cost_key(row)
        if not (key=="concrete" or group=="concrete" or mkey=="concrete"):
            continue
        eligible,reason=_quantity_row_cost_eligibility(row)
        qty=_f(row.get("accepted_quantity",row.get("quantity")))
        if not eligible or qty<=0:
            excluded.append({
                "item":str(row.get("item") or ""),"cost_item_key":"concrete","quantity":qty,
                "reason":reason if not eligible else "nonpositive_quantity",
                "source":"Module 1 canonical concrete ownership"
            })
            continue
        role=str(row.get("aggregation_role") or "").strip().lower()
        item=str(row.get("item") or "").strip().lower()
        source=str(row.get("source_mode") or "").strip().lower()
        is_summary=(role=="summary_fallback" or source=="aggregation" or
                    item in {"total concrete","concrete total","コンクリート合計"} or
                    ("total" in item and "concrete" in item))
        if role=="audit_only":
            excluded.append({"item":str(row.get("item") or ""),"cost_item_key":"concrete","quantity":qty,
                             "reason":"aggregation_audit_only","source":"Module 1 canonical concrete ownership"})
            continue
        (summaries if is_summary else details).append(row)

    if details:
        winners={}
        for row in details:
            comp=_canonical_concrete_component(row)
            old=winners.get(comp)
            if old is None or _concrete_owner_priority(row)>_concrete_owner_priority(old):
                if old is not None:
                    excluded.append({"item":str(old.get("item") or ""),"cost_item_key":"concrete",
                                     "quantity":_f(old.get("accepted_quantity",old.get("quantity"))),
                                     "reason":f"duplicate_physical_component:{comp}",
                                     "source":"Module 1 canonical concrete ownership"})
                winners[comp]=row
            else:
                excluded.append({"item":str(row.get("item") or ""),"cost_item_key":"concrete",
                                 "quantity":_f(row.get("accepted_quantity",row.get("quantity"))),
                                 "reason":f"duplicate_physical_component:{comp}",
                                 "source":"Module 1 canonical concrete ownership"})
        for row in summaries:
            excluded.append({"item":str(row.get("item") or ""),"cost_item_key":"concrete",
                             "quantity":_f(row.get("accepted_quantity",row.get("quantity"))),
                             "reason":"summary_fallback_excluded_because_detail_owners_exist",
                             "source":"Module 1 canonical concrete ownership"})
        owners=list(winners.values())
        qty=sum(_f(r.get("accepted_quantity",r.get("quantity"))) for r in owners)
        return qty,{
            "source_type":"canonical_physical_quantity_ownership",
            "source":"Module 1 quantity_takeoff",
            "basis":"Concrete is summed once per physical component; summary/fallback and duplicate profile/PDF representations are audit-only downstream.",
            "source_items":[str(r.get("item") or "") for r in owners],
            "component_owners":{_canonical_concrete_component(r):str(r.get("item") or "") for r in owners},
        },excluded

    if summaries:
        best=max(summaries,key=_concrete_owner_priority)
        for row in summaries:
            if row is not best:
                excluded.append({"item":str(row.get("item") or ""),"cost_item_key":"concrete",
                                 "quantity":_f(row.get("accepted_quantity",row.get("quantity"))),
                                 "reason":"duplicate_concrete_summary_fallback",
                                 "source":"Module 1 canonical concrete ownership"})
        qty=_f(best.get("accepted_quantity",best.get("quantity")))
        return qty,{
            "source_type":"summary_fallback_only",
            "source":"Module 1 quantity_takeoff",
            "basis":f"No eligible concrete detail owner exists; using one summary fallback only ({best.get('item','')}).",
            "source_items":[str(best.get("item") or "")],
        },excluded
    return 0.0,{"source_type":"none","source":"Module 1 quantity_takeoff","basis":"No eligible positive concrete quantity owner."},excluded

def extract_quantities(project: dict[str, Any], module1: dict[str, Any], settings: dict[str,Any] | None=None) -> tuple[dict[str,float],dict[str,dict[str,Any]],list[dict[str,Any]]]:
    method=_construction_method(project)
    allowed=_method_allowed_keys(method)
    quantities={}
    provenance={}
    excluded=[]
    tagged_scope_quantities={"shutter":{},"louver":{}}
    # PATCH 572: provisional reinforcing-steel rows are dependency expressions,
    # not immutable quantities. Defer them until the canonical current concrete
    # total has been resolved, so an old Project row cannot survive a new RC total.
    deferred_rebar_rates=[]

    for row in module1.get("quantity_takeoff",{}).get("rows",[]):
        item=str(row.get("item",""))
        key=_takeoff_cost_key(row)
        if not key:
            continue
        eligible,eligibility_reason=_quantity_row_cost_eligibility(row)
        if not eligible:
            excluded.append({
                "item":item,"cost_item_key":key,
                "quantity":_f(row.get("accepted_quantity",row.get("quantity"))),
                "reason":eligibility_reason,
                "source":"Module 1 downstream quantity/cost gate",
            })
            continue
        qty=_f(row.get("accepted_quantity",row.get("quantity")))
        if qty<=0:
            continue
        if key=="reinforcing_steel":
            _spec=row.get("provisional_general_spec") if isinstance(row.get("provisional_general_spec"),dict) else {}
            _rate=_f(_spec.get("parameter_value")) if str(_spec.get("parameter_name") or "") == "rebar_rate_kg_per_m3" else 0.0
            _src=str(row.get("source_mode") or "").lower()
            _human=any(tok in _src for tok in ("human","manual","user-confirmed","user confirmed")) or bool(row.get("human_confirmed"))
            if _rate>0 and not _human:
                deferred_rebar_rates.append((_rate,item))
                continue
        # PATCH 530: concrete is resolved by a physical-component ownership pass
        # after this generic loop. Never add row-by-row here, because Module 1
        # intentionally retains detail, generic-profile and summary audit rows.
        if key=="concrete":
            continue
        if key not in allowed:
            excluded.append({
                "item":item,"cost_item_key":key,"quantity":qty,
                "reason":f"Excluded because it is not included in the standard construction composition for {method}"
            })
            continue
        if key in tagged_scope_quantities:
            _m=re.match(r"\b((?:SS|AG)-?\d+)\b",item,re.I)
            _tag=(_m.group(1).upper().replace("-","-") if _m else item)
            tagged_scope_quantities[key][_tag]=max(qty,tagged_scope_quantities[key].get(_tag,0.0))
            quantities[key]=sum(tagged_scope_quantities[key].values())
        else:
            quantities[key]=quantities.get(key,0.0)+qty
        if key not in provenance:
            provenance[key]={
                "source_type":"drawing_quantity",
                "source":"Module 1 quantity_takeoff",
                "basis":f"Adopted quantity from drawing/quantity analysis ({item})",
                "source_items":[item],
                "construction_method":method
            }
        else:
            provenance[key].setdefault("source_items",[]).append(item)
            provenance[key]["basis"]="Total adopted quantity from drawing/quantity analysis (" + " + ".join(provenance[key]["source_items"]) + ")"

    # PATCH 530: one authoritative downstream concrete quantity shared by cost
    # and LCA. This works with existing Project JSONs, so a user does not need to
    # rerun PDF takeoff merely to remove legacy summary/profile duplication.
    _concrete_qty,_concrete_prov,_concrete_excluded=_canonical_concrete_quantity(module1)
    if _concrete_qty>0 and "concrete" in allowed:
        quantities["concrete"]=_concrete_qty
        _concrete_prov["construction_method"]=method
        provenance["concrete"]=_concrete_prov
    excluded.extend(_concrete_excluded)

    if "reinforcing_steel" not in quantities and deferred_rebar_rates and _concrete_qty>0 and "reinforcing_steel" in allowed:
        _rate,_item=max(deferred_rebar_rates,key=lambda x:x[0])
        quantities["reinforcing_steel"]=_concrete_qty*_rate/1000.0
        provenance["reinforcing_steel"]={
            "source_type":"recomputed_dependency_quantity",
            "source":"Module 1 provisional reinforcement specification + canonical current concrete",
            "basis":f"Current canonical concrete {_concrete_qty:.6f} m3 × {_rate:.3f} kg/m3 ÷ 1000; stale stored mass ignored",
            "source_items":[_item],
            "construction_method":method,
            "certainty":"estimated",
            "planning_only":True,
            "rebar_rate_kg_per_m3":_rate,
        }

    # PATCH 414: honor Module 1 final quantity contracts before any Module 5
    # planning fallback is allowed to create a priced quantity.  This prevents
    # a blocked final reinforcement/steel contract from being silently replaced
    # by a generic concrete-volume allowance downstream.
    takeoff=module1.get("quantity_takeoff",{}) or {}
    rebar_contract=takeoff.get("reinforcement_quantity_contract") or {}
    steel_contract=takeoff.get("steel_connection_quantity_contract") or {}
    formwork_contract=takeoff.get("formwork_quantity_contract") or {}

    rebar_status=str(rebar_contract.get("final_rebar_weight_status") or "").strip().lower()
    steel_status=str(steel_contract.get("final_structural_steel_weight_status") or "").strip().lower()
    blocked_fallback_keys=set()

    # PATCH 470: a blocked Module 1 *final* steel/rebar contract must remain
    # blocked as a final quantity, but the Approximate Cost Provider is allowed
    # to consume a rational planning quantity when Module 1 already exposes one.
    # This does not overwrite Module 1 and does not promote the quantity to
    # confirmed; it is kept explicitly provisional/yellow in Module 5.
    if rebar_status.startswith("blocked"):
        _blocked_rebar_qty=quantities.get("reinforcing_steel",0.0)
        _rebar_direct_meta={}
        if _blocked_rebar_qty<=0:
            # PATCH 472: third-attempt method change. Read Module 1's structured
            # reinforcement tags directly instead of relying on the cost-key text
            # bridge / excluded-row route used by PATCH 470-471.
            _blocked_rebar_qty,_rebar_direct_meta=_module1_rebar_planning_quantity(module1)
            if _rebar_direct_meta.get("selection")=="largest_positive_tagged_provisional_row":
                _rate=_f(_rebar_direct_meta.get("rebar_rate_kg_per_m3"))
                _current_concrete=_f(quantities.get("concrete"))
                if _rate>0 and _current_concrete>0:
                    _blocked_rebar_qty=_current_concrete*_rate/1000.0
                    _rebar_direct_meta["source"]="Module 1 provisional reinforcement specification + canonical current concrete"
                    _rebar_direct_meta["basis"]=f"Recomputed dependency: current concrete {_current_concrete:.6f} m3 × {_rate:.3f} kg/m3 ÷ 1000; stored provisional mass ignored"
                    _rebar_direct_meta["selection"]="recomputed_provisional_dependency"
        if _blocked_rebar_qty<=0:
            # Business-plan continuity rule: if the final rebar contract is blocked
            # and Module 1 has no usable mass row, derive a transparent yellow-only
            # planning allowance from the already-adopted concrete quantity. This
            # never changes Module 1 and never becomes a confirmed quantity.
            _concrete_for_rebar=_f(quantities.get("concrete"))
            _kgpm3={"azras":90.0,"rc_frame":120.0,"wood_frame":100.0}.get(method,100.0)
            if _concrete_for_rebar>0:
                _blocked_rebar_qty=_concrete_for_rebar*_kgpm3/1000.0
                _rebar_direct_meta={
                    "source":"Module 5 planning allowance from adopted concrete quantity",
                    "basis":f"Final reinforcement contract blocked and no tagged mass row available; adopted concrete {_concrete_for_rebar:.3f} m3 × {_kgpm3:.0f} kg/m3 ÷ 1000",
                    "selection":"method_concrete_intensity_fallback",
                    "rebar_rate_kg_per_m3":_kgpm3,
                }
        if _blocked_rebar_qty>0:
            quantities["reinforcing_steel"]=_blocked_rebar_qty
            provenance["reinforcing_steel"]={
                "source_type":"module1_blocked_contract_planning_estimate",
                "source":str(_rebar_direct_meta.get("source") or "Module 1 reinforcement_quantity_contract + structured reinforcement rows"),
                "basis":str(_rebar_direct_meta.get("basis") or "Planning-only reinforcing-steel quantity; final reinforcement contract remains blocked"),
                "construction_method":method,
                "final_contract_status":rebar_status,
                "certainty":"estimated",
                "display_color":"yellow",
                "planning_only":True,
                "selection":_rebar_direct_meta.get("selection"),
                "source_item":_rebar_direct_meta.get("source_item"),
                "source_items":_rebar_direct_meta.get("source_items"),
                "rebar_rate_kg_per_m3":_rebar_direct_meta.get("rebar_rate_kg_per_m3"),
            }
            excluded[:]=[x for x in excluded if str(x.get("cost_item_key") or "")!="reinforcing_steel"]
        else:
            excluded.append({
                "item":"鉄筋",
                "cost_item_key":"reinforcing_steel",
                "quantity":0.0,
                "unit":"t",
                "reason":"Module 1 final reinforcement contract is blocked and neither a tagged planning mass nor a concrete-based planning allowance could be formed",
                "contract_status":rebar_status,
                "source":"Module 1 reinforcement_quantity_contract",
                "contract_block_evidence":True,
            })
            quantities.pop("reinforcing_steel",None)
            provenance.pop("reinforcing_steel",None)
            blocked_fallback_keys.add("reinforcing_steel")

    if steel_status.startswith("blocked"):
        _blocked_steel_qty=quantities.get("structural_steel",0.0)
        if _blocked_steel_qty<=0:
            _blocked_steel_qty=_f(steel_contract.get("provisional_member_plus_confirmed_connections_t")) or _f(steel_contract.get("provisional_member_mass_t"))
        if _blocked_steel_qty>0:
            quantities["structural_steel"]=_blocked_steel_qty
            provenance["structural_steel"]={
                "source_type":"module1_blocked_contract_planning_estimate",
                "source":"Module 1 steel_connection_quantity_contract",
                "basis":"Planning-only structural-steel quantity = provisional member mass + confirmed connection mass; final steel contract remains blocked",
                "construction_method":method,
                "final_contract_status":steel_status,
                "certainty":"estimated",
            }
            excluded[:]=[x for x in excluded if str(x.get("cost_item_key") or "")!="structural_steel"]
        else:
            excluded.append({
                "item":"構造用鉄骨",
                "cost_item_key":"structural_steel",
                "quantity":_blocked_steel_qty,
                "unit":"t" if _blocked_steel_qty>0 else None,
                "reason":"Module 1 steel_connection_quantity_contract blocks final structural-steel weight and no positive planning quantity is available",
                "contract_status":steel_status,
                "source":"Module 1 steel_connection_quantity_contract",
                "contract_block_evidence":True,
            })
            quantities.pop("structural_steel",None)
            provenance.pop("structural_steel",None)
            blocked_fallback_keys.add("structural_steel")

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
            "member_geometry",
            "drawing_member_extraction",
            "rc_overlap_deduction_policy",
            "rc_vector_takeoff",
        ):
            if key in drawing_construction:
                merged_construction[key]=drawing_construction[key]
        profile["construction"]=merged_construction

    geometry=profile.get("geometry",{})
    surfaces=profile.get("surfaces",[])
    construction=profile.get("construction",{})

    def fallback(key,qty,basis):
        if key in blocked_fallback_keys:
            return
        if key in allowed and key not in quantities and qty>0:
            quantities[key]=qty
            provenance[key]={
                "source_type":"planning_fallback_requires_confirmation",
                "source":"Module 5 method profile",
                "basis":basis,
                "construction_method":method
            }

    # PATCH 042: authoritative drawing-derived 2×6 foundation linkage.
    foundation_geometry=construction.get("foundation_geometry",{}) or {}
    if method=="wood_frame" and foundation_geometry.get("status") in {"matched_dimensioned_plan","current_pdf_explicit_geometry"}:
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

            if "reinforcing_steel" not in blocked_fallback_keys:
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
                    "basis":f"Strip-footing stem formwork, both faces: {fw:.3f} m2 (base-slab side faces are not auto-counted)",
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
                    "basis":str(basis_map.get(key) or "Quantity derived from foundation geometry and common planning assumptions"),
                    "construction_method":method,
                    "requires_confirmation":True,
                }

    # PATCH 437: steel/general exterior-final-finish bridge.
    # Prefer the authoritative net exterior-wall total when detailed finish
    # components do not yet cover every face.  When detail rows cover the full
    # wall area, their sum and the gross control converge.  This prevents both
    # silent omission and double counting.
    if "external_finish" in allowed and "external_finish" not in quantities:
        _wall_total=0.0
        _wall_detail=0.0
        _wall_detail_items=[]
        for _r in (takeoff.get("rows") or []):
            _it=str(_r.get("item") or "")
            _u=str(_r.get("unit") or "").lower()
            if _u not in {"m2","m²"}:
                continue
            _q=_f(_r.get("accepted_quantity",_r.get("quantity")))
            if _q<=0:
                continue
            if "外壁正味面積 合計" in _it or "外壁仕上面積 合計" in _it:
                _wall_total=max(_wall_total,_q)
            if any(_tok in _it for _tok in ("サイディング","スパンドレル")):
                _wall_detail+=_q
                _wall_detail_items.append(_it)
        _adopt=max(_wall_total,_wall_detail)
        if _adopt>0:
            quantities["external_finish"]=_adopt
            provenance["external_finish"]={
                "source_type":"drawing_finish_scope_control",
                "source":"Module 1 exterior-wall net area / finish-detail rows",
                "basis":(
                    f"Exterior final finish control: net wall total {_wall_total:.3f} m2; "
                    f"material-detail sum {_wall_detail:.3f} m2; adopted {_adopt:.3f} m2. "
                    "The larger control is used once; component finish rows are audit detail and are not added again."
                ),
                "construction_method":method,
                "detail_items":_wall_detail_items,
                "requires_confirmation":bool(_wall_total and abs(_wall_total-_wall_detail)>max(1.0,0.02*_wall_total)),
            }

    fallback("roofing",_f(geometry.get("roof_area_m2")),"Module 1屋根面積を屋根・防水工事数量として採用")
    fallback("doors",sum(_f(x.get("door_area_m2")) for x in surfaces),"Module 1各面のドア面積合計")
    gfa=_f(geometry.get("conditioned_floor_area_m2")) or _f(project.get("common",{}).get("scale_gfa_m2"))
    if gfa>0:
        fallback("interior_finish",gfa*2.0,"延床面積×2.0を内装仕上げ面積の計画補完値として使用")
    # PATCH_404: use the current exterior-only RC surface key first.  Without
    # this bridge an RC wall resolved by Module 1 could become 0 m2 in Module 5
    # fallback finishes/insulation while Module 2 correctly used the same wall.
    rc_external_area=_f(construction.get("exterior_rc_interior_surface_m2"))
    if rc_external_area<=0:
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
            "basis":f"Foundation / under-slab area {slab_area:.3f} m2 × {slab_ins_mm:g} mm ÷ 1000",
            "construction_method":method,
        }

    # PATCH 530: use an already-present tagged Module 1 reinforcement planning
    # quantity before deriving a new mass from concrete. This prevents a stale or
    # duplicated concrete total from inflating rebar downstream. The row remains
    # provisional; this does not promote a blocked final reinforcement contract.
    if "reinforcing_steel" not in quantities and "reinforcing_steel" in allowed:
        _m1_rebar_qty,_m1_rebar_meta=_module1_rebar_planning_quantity(module1)
        _selection=str(_m1_rebar_meta.get("selection") or "")
        if _selection=="largest_positive_tagged_provisional_row":
            _rate=_f(_m1_rebar_meta.get("rebar_rate_kg_per_m3"))
            _current_concrete=_f(quantities.get("concrete"))
            if _rate>0 and _current_concrete>0:
                _m1_rebar_qty=_current_concrete*_rate/1000.0
                _m1_rebar_meta["source"]="Module 1 provisional reinforcement specification + canonical current concrete"
                _m1_rebar_meta["basis"]=f"Recomputed dependency: current concrete {_current_concrete:.6f} m3 × {_rate:.3f} kg/m3 ÷ 1000; stored provisional mass ignored"
                _m1_rebar_meta["selection"]="recomputed_provisional_dependency"
        if _m1_rebar_qty>0:
            quantities["reinforcing_steel"]=_m1_rebar_qty
            provenance["reinforcing_steel"]={
                "source_type":"module1_tagged_planning_quantity",
                "source":str(_m1_rebar_meta.get("source") or "Module 1 reinforcement rows"),
                "basis":str(_m1_rebar_meta.get("basis") or "Module 1 planning reinforcement quantity"),
                "construction_method":method,
                "certainty":"estimated",
                "planning_only":True,
                "selection":_m1_rebar_meta.get("selection"),
                "source_item":_m1_rebar_meta.get("source_item"),
                "rebar_rate_kg_per_m3":_m1_rebar_meta.get("rebar_rate_kg_per_m3"),
            }

    # Structural quantities that are absent in old/partial Module 1 takeoffs.
    # These are planning fallbacks only and are tagged as such in provenance.
    concrete_qty=quantities.get("concrete",0.0)
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

    # PATCH 414: when Module 1 exposes explicit drawing-geometry formwork, use
    # that contract before any Module 5 geometry/planning fallback.
    if "formwork" not in quantities and "formwork" in allowed:
        fw_contract_qty=_f(formwork_contract.get("quantity_m2"))
        if str(formwork_contract.get("status") or "").strip().lower()=="drawing_geometry" and fw_contract_qty>0:
            quantities["formwork"]=fw_contract_qty
            provenance["formwork"]={
                "source_type":"drawing_quantity_contract",
                "source":"Module 1 formwork_quantity_contract",
                "basis":str(formwork_contract.get("policy") or "Module 1 drawing-geometry formwork quantity"),
                "construction_method":method,
            }

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

    # PATCH_039: ceiling_glass_wool (m3) and ceiling_insulation_area (m2)
    # describe the same physical ceiling insulation layer in two different
    # measurement bases.  Never keep both: the volume key wins because it is
    # thickness-explicit, and the area key is demoted to an audit record.  No
    # conversion is invented in either direction.
    if "ceiling_glass_wool" in quantities and "ceiling_insulation_area" in quantities:
        _dropped=quantities.pop("ceiling_insulation_area")
        provenance.pop("ceiling_insulation_area",None)
        excluded.append({
            "item":"Ceiling insulation (area basis)",
            "cost_item_key":"ceiling_insulation_area",
            "quantity":_dropped,
            "reason":"Same ceiling insulation layer is already owned by ceiling_glass_wool (volume basis); keeping both would double count",
            "source":"PATCH_039 ceiling insulation single-owner rule",
        })

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
    if cost_item_key in {"gypsum_board","interior_finish","ceiling_lgs"}:
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

def _normalize_residential_equipment_selection(project,database,equipment_selection,location=None):
    selection={k:dict(v or {}) for k,v in (equipment_selection or {}).items()}
    standards=("hvac","electrical","plumbing","kitchen","bathroom")
    all_false=all(not bool((selection.get(k) or {}).get("include")) for k in standards)
    migrated=False
    if _is_residential_project(project) and all_false:
        for k in standards:
            db_item=(database.get("equipment_packages",{}) or {}).get(k,{})
            item=selection.setdefault(k,{})
            item["include"]=True
            if _f(item.get("cost"))<=0:
                if str((location or {}).get("currency") or "JPY").upper()=="JPY":
                    item["cost"]=_f(db_item.get("default_cost_jpy"))
                    item["cost_basis"]="database_default_jpy"
                else:
                    item["cost"]=0.0
                    item["cost_basis"]="foreign_local_price_required"
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
        # PATCH_050: Module 1 stores concrete_volume_m3 as a scalar (its own row
        # contract) and the breakdown separately; older data used a dict here.
        cv=fg.get("concrete_volume_m3")
        if not isinstance(cv,dict):
            cv=fg.get("concrete_volume_breakdown_m3") or {"strip_foundation":cv}
        footing_w=_f(dims.get("footing_width") or fg.get("footing_base_width_mm"))/1000.0
        total_h=_f(dims.get("total_height") or (_f(fg.get("footing_base_thickness_mm"))+_f(fg.get("stem_height_mm"))))/1000.0
        length=_f(lengths.get("total") or fg.get("centerline_total_m"))
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
    # PATCH_049→050: Module 1 publishes the ground-beam length measured on the
    # foundation plan as rc_vector_takeoff.foundation.net_ground_beam_length_m,
    # never as member_geometry.ground_beam_length_m (no producer writes that
    # key).  Without this fallback every RC project lost all six earthwork
    # items even though the length existed.  Only a resolved vector result is
    # accepted; the earthwork stays requires_confirmation.
    length_source="member_geometry.ground_beam_length_m"
    if L<=0:
        vf=((construction.get("rc_vector_takeoff") or {}).get("foundation") or {})
        if str(vf.get("status") or "").startswith("vector_foundation_grid_resolved"):
            try: L=float(vf.get("net_ground_beam_length_m") or 0.0)
            except Exception: L=0.0
            length_source="rc_vector_takeoff.foundation.net_ground_beam_length_m"
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
        "drawing_supported":{"isolated_footing_count":n,"isolated_footing_mm":[x*1000 for x in f],"ground_beam_mm":[x*1000 for x in b],"ground_beam_length_m":L,"ground_beam_length_source":length_source},
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
    if ds.get("currency"):
        out["currency"]=ds.get("currency")
    # PATCH 463: FX metadata may remain in historical regional JSON files,
    # but construction-cost pricing never imports or consumes it.
    if isinstance(ds.get("whole_building_benchmark"),dict):
        out["whole_building_benchmark"]=ds.get("whole_building_benchmark")

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


def unicodedata_nfkc(value: str) -> str:
    """PATCH_042: NFKC-normalise a place string for substring matching."""
    import unicodedata
    return unicodedata.normalize("NFKC",str(value or ""))


_NEAREST_REGIONAL_MATCH_KM=100.0  # PATCH_053: same value as services.regional_profile_catalog


def resolve_location_profile_from_project(project: dict[str,Any], database: dict[str,Any]) -> dict[str,Any]:
    """PATCH 459: resolve all registered regional representative cities."""
    common=project.get("common",{}) or {}
    locobj=common.get("location",{}) or {}
    country=str(common.get("country") or locobj.get("country") or "").strip()
    project_location=str(common.get("project_location") or locobj.get("project_location") or "").strip()
    city=str(common.get("city") or locobj.get("city") or project_location or "").strip()
    address=str(project_location or common.get("address") or locobj.get("address") or "").strip()

    def norm(v: str) -> str:
        import unicodedata, re
        v=unicodedata.normalize("NFKC",str(v or "")).casefold()
        return re.sub(r"[^0-9a-z\u3040-\u30ff\u3400-\u9fff]+","",v)

    country_aliases={
        "日本":"japan","jp":"japan",
        "usa":"unitedstates","us":"unitedstates","u.s.":"unitedstates","アメリカ":"unitedstates","米国":"unitedstates",
        "uk":"unitedkingdom","u.k.":"unitedkingdom","英国":"unitedkingdom","イギリス":"unitedkingdom",
        "フランス":"france","アラブ首長国連邦":"unitedarabemirates","uae":"unitedarabemirates",
        "シンガポール":"singapore","タイ":"thailand","インド":"india","オーストラリア":"australia",
        "ドイツ":"germany","ノルウェー":"norway","カナダ":"canada","メキシコ":"mexico",
    }
    city_aliases={
        "東京":"tokyo","札幌":"sapporo","名古屋":"nagoya","春日井":"nagoya",
        "ニューヨーク":"newyork","ロサンゼルス":"losangeles","ロンドン":"london","パリ":"paris",
        "ドバイ":"dubai","バンコク":"bangkok","デリー":"delhi","ニューデリー":"delhi",
        "シドニー":"sydney","ベルリン":"berlin","オスロ":"oslo","トロント":"toronto","メキシコシティ":"mexicocity",
    }
    nc=country_aliases.get(str(country).strip().casefold(),norm(country))
    ncity=city_aliases.get(str(city).strip().casefold(),norm(city))
    naddr=norm(address)
    # PATCH_042: the Japanese alias keys were only ever compared with the WHOLE
    # city field.  Japanese projects routinely store a full street address there
    # ("愛知県春日井市松河戸町2-18-7"), so an explicit alias such as 春日井 -> nagoya
    # never fired, and the romaji-only address fallback below cannot find
    # "nagoya" in a Japanese address either.  Every Aichi sample therefore fell
    # through to the country reference city (Tokyo: material 112 / labor 118 /
    # productivity 95 instead of Nagoya's 105 / 105 / 100).  Match a non-Latin
    # alias as a substring of the city or address; longest key first, so a more
    # specific alias always wins over a shorter one it contains.
    _alias_hit=None
    if str(city).strip().casefold() not in city_aliases:
        _raw_place=unicodedata_nfkc(str(city))+" "+unicodedata_nfkc(str(address))
        for _ak in sorted(city_aliases,key=len,reverse=True):
            if any(ord(_ch)>0x2E7F for _ch in _ak) and _ak in _raw_place:
                ncity=city_aliases[_ak]; _alias_hit=_ak
                break

    locations=database.get("locations") or {}
    ranked=[]
    for key in locations:
        if key=="User Defined" or " / " not in key:
            continue
        kc,kcity=key.split(" / ",1)
        nkc=norm(kc); nkcity=norm(kcity)
        score=0
        if nc and nc==nkc: score+=3
        if ncity and ncity==nkcity: score+=5
        elif nkcity and nkcity in naddr: score+=4
        if score>0:
            ranked.append((score,key))
    ranked.sort(reverse=True)
    key=ranked[0][1] if ranked and ranked[0][0]>=5 else None
    # PATCH_039: remember whether the key came from a real city match.
    _city_matched_key=key

    # PATCH_053: nearest profile by great-circle distance.  When the city name
    # itself is not a registered profile, the Project coordinates (Module 0:
    # common.latitude/longitude) select the nearest profile in the same
    # country - "2-18-7 Matsukawadomachi, Kasugai-shi, Aichi-ken" -> Nagoya
    # (about 15 km) instead of the country reference city Tokyo.  If the
    # country has no profile at all, the nearest profile anywhere is chosen
    # and reported as outside the country.  Without coordinates the older
    # alias / prefecture / country-reference fallbacks below still apply.
    _nearest_km=None
    _nearest_scope=None
    if not key:
        from services.regional_profile_catalog import nearest_location, project_coordinates
        _pc=project_coordinates(project)
        if _pc:
            _k,_d=nearest_location(locations,_pc[0],_pc[1],nc or None) if nc else (None,None)
            if _k:
                key,_nearest_km,_nearest_scope=_k,_d,"in_country"
            else:
                _k,_d=nearest_location(locations,_pc[0],_pc[1],None)
                if _k:
                    key,_nearest_km,_nearest_scope=_k,_d,"outside_country"

    # Address fallback for projects where city field is not standardized.
    if not key and nc=="japan":
        for token,candidate in (("tokyo","Japan / Tokyo"),("sapporo","Japan / Sapporo"),("nagoya","Japan / Nagoya")):
            if token in ncity or token in naddr:
                if candidate in locations: key=candidate; break

    # PATCH_042: prefecture-level fallback for Japan.  A municipality that is not
    # itself an alias still belongs to a prefecture whose representative city is
    # registered; that is a regional match, not a national guess.  Only
    # prefectures whose representative city actually exists in the database are
    # listed, and nothing is inferred for any other prefecture.
    _prefecture_hit=None
    if not key and nc=="japan":
        _jp_prefecture_reference=(
            ("愛知県","Japan / Nagoya"),("岐阜県","Japan / Nagoya"),("三重県","Japan / Nagoya"),
            ("北海道","Japan / Sapporo"),
            ("東京都","Japan / Tokyo"),("神奈川県","Japan / Tokyo"),("埼玉県","Japan / Tokyo"),("千葉県","Japan / Tokyo"),
        )
        _raw_place=unicodedata_nfkc(str(city))+" "+unicodedata_nfkc(str(address))
        for _pref,_cand in _jp_prefecture_reference:
            if _pref in _raw_place and _cand in locations:
                key=_cand; _prefecture_hit=_pref
                break
        # PATCH_053: romanised addresses ("Kasugai-shi, Aichi-ken").  Whole
        # words only, so a short name such as "mie" never matches inside
        # another word.
        if not key:
            _words=set(re.findall(r"[a-z]+",_raw_place.casefold()))
            for _pref,_cand in (("aichi","Japan / Nagoya"),("gifu","Japan / Nagoya"),("mie","Japan / Nagoya"),
                                ("hokkaido","Japan / Sapporo"),("tokyo","Japan / Tokyo"),("kanagawa","Japan / Tokyo"),
                                ("saitama","Japan / Tokyo"),("chiba","Japan / Tokyo")):
                if _pref in _words and _cand in locations:
                    key=_cand; _prefecture_hit=_pref
                    break

    # PATCH 429: Project location is the initial regional-cost selector.  A project
    # city does not have to be one of the representative cities embedded in the
    # planning database (e.g. Williamsburg, VA).  When the country is known but
    # the exact city is not registered, select the country's canonical planning
    # reference city instead of falling back to JPY/User Defined.  The user can
    # still override the profile explicitly in Module 5.
    if not key and nc:
        country_reference={
            "japan":"Japan / Tokyo",
            "unitedstates":"United States / New York",
            "unitedkingdom":"United Kingdom / London",
            "france":"France / Paris",
            "unitedarabemirates":"United Arab Emirates / Dubai",
            "singapore":"Singapore / Singapore",
            "thailand":"Thailand / Bangkok",
            "india":"India / Delhi",
            "australia":"Australia / Sydney",
            "germany":"Germany / Berlin",
            "norway":"Norway / Oslo",
            "canada":"Canada / Toronto",
            "mexico":"Mexico / Mexico City",
        }
        candidate=country_reference.get(nc)
        if candidate in locations:
            key=candidate

    # PATCH_039: report HOW the profile was reached.  A country reference city
    # (e.g. Illinois -> "United States / New York") is a usable default, but it
    # is NOT the project's city, and every downstream consumer - the AI cost
    # request, the Module 5 header and the duration/productivity figure - must
    # be able to say so instead of presenting it as the project region.
    if key and key==_city_matched_key:
        match_level="matched_city"
    elif key and _nearest_scope=="in_country":
        match_level="nearest_in_country"
    elif key and _nearest_scope=="outside_country":
        match_level="nearest_outside_country"
    elif key and _prefecture_hit:
        match_level="matched_prefecture"
    elif key:
        match_level="country_reference_fallback"
    else:
        match_level="unresolved"
    return {
        "matched":bool(key),
        "location_key":key,
        "match_level":match_level,
        "profile_is_project_city":match_level=="matched_city",
        "profile_is_country_fallback":match_level=="country_reference_fallback",
        "profile_is_regional_match":(match_level in {"matched_city","matched_prefecture"}
                                     or (match_level=="nearest_in_country" and _nearest_km is not None
                                         and _nearest_km<=_NEAREST_REGIONAL_MATCH_KM)),
        "nearest_distance_km":_nearest_km,
        "matched_alias":_alias_hit,
        "matched_prefecture":_prefecture_hit,
        "country":country,
        "city":city,
        "address":address,
        "source":"project.common / project.common.location",
        "fallback_location_key":"User Defined" if "User Defined" in locations else None,
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
        # PATCH 462: foreign construction prices must originate in the
        # selected local market/local currency. Japanese base prices are not
        # converted by FX to manufacture a foreign construction price.
        fallback_material=None
        fallback_labor=None
        fallback_equipment=None
        fallback_source="foreign_local_unit_cost_required_no_jpy_fx_fallback"

    local_flags={"material":False,"labor":False,"equipment":False}

    # PATCH 466: an AI/public source may provide a defensible installed/all-in
    # unit rate without a material/labor/equipment split. Preserve that price
    # structure instead of mislabelling the combined rate as a component.
    if isinstance(local,dict) and str(local.get("pricing_structure") or "").lower()=="installed_all_in":
        try:
            installed=float(local.get("installed_unit_cost"))
        except (TypeError,ValueError):
            installed=-1.0
        if installed < 0:
            if currency!="JPY":
                # PATCH 475: a missing/invalid foreign local rate is a visible
                # unpriced scope, not a fatal Module 5 error.  Keep the quantity
                # and exclude the line from priced totals; never manufacture a
                # JPY/FX fallback or silently treat the item as a true zero cost.
                return 0.0,0.0,0.0,"foreign_local_unit_unpriced_invalid_installed_all_in",local_flags
            raise ValueError(f"{currency}: installed/all-in unit cost is invalid for '{key}'.")
        return installed,0.0,0.0,"local_installed_all_in",{"material":True,"labor":True,"equipment":True}

    if not isinstance(local,dict):
        if currency!="JPY":
            # PATCH 475: overseas approximate-cost calculations must continue
            # when a local-market price has not yet been obtained.  The item is
            # retained as an explicit red/unpriced monetary gap.  This is NOT a
            # zero-price assumption and does NOT re-enable the prohibited JPY/FX
            # fallback introduced by PATCH 462.
            return 0.0,0.0,0.0,"foreign_local_unit_unpriced_missing",local_flags
        return (
            fallback_material,fallback_labor,fallback_equipment,
            fallback_source,local_flags
        )

    # PATCH 475: a foreign component-split rate is usable only when all three
    # required components are present and numeric.  A partial/invalid split is
    # not partly counted because that would understate the line while looking
    # priced.  Preserve it as one explicit unpriced line instead.
    if currency!="JPY":
        _foreign_values={}
        for _component in ("material","labor","equipment"):
            _value=local.get(_component)
            if _value is None or _value=="":
                return 0.0,0.0,0.0,f"foreign_local_unit_unpriced_missing_{_component}",local_flags
            try:
                _foreign_values[_component]=float(_value)
            except (TypeError,ValueError):
                return 0.0,0.0,0.0,f"foreign_local_unit_unpriced_invalid_{_component}",local_flags
            if _foreign_values[_component] < 0:
                return 0.0,0.0,0.0,f"foreign_local_unit_unpriced_invalid_{_component}",local_flags
        return (
            _foreign_values["material"],_foreign_values["labor"],_foreign_values["equipment"],
            "local_unit_cost_all_components",{"material":True,"labor":True,"equipment":True}
        )

    def pick(component: str, fallback: float | None) -> tuple[float,bool]:
        value=local.get(component)
        if value is None or value=="":
            return float(fallback or 0.0),False
        try:
            return float(value),True
        except (TypeError,ValueError):
            return float(fallback or 0.0),False

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
        installed_all_in=(
            str(meta.get("pricing_structure") or "").lower()=="installed_all_in"
            and meta.get("installed_unit_cost") not in (None,"")
        )
        flags={
            "material": meta.get("material") not in (None,""),
            "labor": meta.get("labor") not in (None,""),
            "equipment": meta.get("equipment") not in (None,""),
        }
        count=sum(1 for v in flags.values() if v)
        if installed_all_in:
            full_local_count += 1
            local_component_count += 3
            pricing_mode="local_installed_all_in"
        else:
            local_component_count += count
            if count==3:
                full_local_count += 1
                pricing_mode="local_all_components"
            elif count>0:
                partial_local_count += 1
                pricing_mode="partial_local_plus_fallback"
            else:
                line=next((x for x in (cost_lines or []) if str(x.get("cost_item_key") or "")==key),{})
                if str(line.get("pricing_display_status") or "")=="unpriced":
                    pricing_mode="unpriced_no_local_rate"
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
    maximum_component_count=total*3
    local_component_coverage_percent=(
        (local_component_count/maximum_component_count)*100.0
        if maximum_component_count>0 else 0.0
    )
    full_local_item_coverage_percent=(
        (full_local_count/total)*100.0 if total>0 else 0.0
    )

    # PATCH 461: do not upgrade "registered local" data to "verified"
    # unless the dataset freshness metadata itself says verified.
    freshness=evaluate_unit_cost_dataset_freshness(location)
    dataset_status=str(freshness.get("status") or "not_available")
    unpriced_item_count=sum(1 for x in items if x.get("pricing_mode")=="unpriced_no_local_rate")
    if total>0 and full_local_count==total and dataset_status=="verified":
        pricing_basis_class="verified_local_unit_prices"
    elif total>0 and unpriced_item_count==total:
        pricing_basis_class="unpriced_local_rates_required"
    elif local_component_count>0:
        pricing_basis_class="mixed_local_and_azras_regional_estimate"
    else:
        pricing_basis_class="azras_regional_estimate"

    return {
        "patch":"PATCH 461",
        "used_cost_item_count":total,
        "full_local_item_count":full_local_count,
        "partial_local_item_count":partial_local_count,
        "regional_fallback_item_count":fallback_count,
        "local_component_count":local_component_count,
        "maximum_component_count":maximum_component_count,
        "local_component_coverage_percent":local_component_coverage_percent,
        "full_local_item_coverage_percent":full_local_item_coverage_percent,
        "pricing_basis_class":pricing_basis_class,
        "unit_cost_dataset_status":dataset_status,
        "unit_cost_dataset_source_name":freshness.get("source_name"),
        "unit_cost_dataset_source_reference":freshness.get("source_reference"),
        "unit_cost_dataset_data_date":freshness.get("data_date"),
        "unpriced_item_count":unpriced_item_count,
        "calculation_price_status":(
            "source_complete" if pricing_basis_class=="verified_local_unit_prices"
            else "unpriced_local_rates_required" if pricing_basis_class=="unpriced_local_rates_required"
            else "mixed_local_and_regional_estimate" if local_component_count>0
            else "regional_estimate"
        ),
        "requires_future_data_update":(
            fallback_count>0 or partial_local_count>0 or dataset_status!="verified"
        ),
        "items":items,
        "note_ja":(
            "現地単価として登録された成分はその値を使用し、未登録成分はAZRAS地域概算値を使用する。"
            "「確認済み現地単価」と表示するのは、使用全工事項目の全成分が現地単価で揃い、"
            "かつ単価データセット自体がverifiedの場合だけとする。"
        ),
    }


def build_construction_cost_validity_diagnostic(
    method: str,
    gfa_m2: float,
    subtotal_before_tax: float,
    benchmark: dict[str,Any],
    currency: str,
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
        judgment_en="AZRAS is a hybrid timber + RC method, so it is not forced to match a single-structure external benchmark."
    elif ratio is not None and ratio < 0.80:
        severity="materially_below_benchmark"
        judgment_ja="外部構造別ベンチマークより20%以上低い。数量・単価・未計上工種・仮設/諸経費を優先確認する。"
        judgment_en="More than 20% below the external structure benchmark. Prioritize review of quantities, unit prices, omitted trades, temporary works and overhead."
    elif ratio is not None and ratio < 0.90:
        severity="below_benchmark"
        judgment_ja="外部構造別ベンチマークより10%以上低い。市場妥当性の追加確認が必要。"
        judgment_en="More than 10% below the external structure benchmark. Additional market-validity review is required."
    elif ratio is not None and ratio <= 1.10:
        severity="near_benchmark"
        judgment_ja="外部構造別ベンチマークの±10%範囲。なお実際の請負価格との一致を保証するものではない。"
        judgment_en="Within ±10% of the external structure benchmark. This does not guarantee agreement with an actual contract price."
    else:
        severity="above_benchmark"
        judgment_ja="外部構造別ベンチマークを上回る。仕様差・規模差を確認する。"
        judgment_en="Above the external structure benchmark. Review specification and scale differences."

    group_total=sum(max(_f(v),0.0) for v in (market_group_direct_costs or {}).values())
    groups=[]
    for key,val in sorted((market_group_direct_costs or {}).items(), key=lambda kv:_f(kv[1]), reverse=True):
        v=max(_f(val),0.0)
        groups.append({
            "group":key,
            "cost":v,
            "currency":str(currency or "JPY"),
            # Backward-compatibility alias. Values are in result currency, not
            # necessarily JPY; new code must use ``cost``.
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
        "currency":str(currency or "JPY"),
        "audit_only":True,
        "automatic_price_adjustment":False,
        "method":method,
        "gross_floor_area_m2":gfa,
        # PATCH 434: canonical currency-neutral names. All monetary values in
        # this diagnostic are denominated in ``currency``. Legacy *_jpy keys
        # are retained below only for compatibility with older Project JSONs.
        "software_estimate_ex_tax":subtotal_before_tax,
        "software_estimate_ex_tax_per_m2":est_m2,
        "benchmark_per_m2":benchmark.get("benchmark_jpy_per_m2"),
        "benchmark_total_for_same_gfa":bm*gfa if bm>0 and gfa>0 else None,
        "shortfall_to_benchmark":gap_jpy,
        "direct_cost_group_total":group_total,
        "software_estimate_ex_tax_jpy":subtotal_before_tax,
        "software_estimate_ex_tax_jpy_per_m2":est_m2,
        "benchmark_jpy_per_m2":benchmark.get("benchmark_jpy_per_m2"),
        "benchmark_total_for_same_gfa_jpy":bm*gfa if bm>0 and gfa>0 else None,
        "shortfall_to_benchmark_jpy":gap_jpy,
        "gap_vs_benchmark_percent":gap_pct,
        "benchmark_ratio":ratio,
        "severity":severity,
        "judgment_ja":judgment_ja,
        "judgment_en":judgment_en,
        "direct_cost_group_total_jpy":group_total,
        "direct_cost_group_breakdown":groups,
        "priority_checks":checks,
        "benchmark_reference":benchmark,
        "source_scope_warning_ja":"国税庁の構造別工事費指標は外部妥当性監査用。今回建物の契約見積ではないため、総額を自動補正する係数には使用しない。",
        "source_scope_warning_en":"Japan NTA structure-cost indicators are used only for external validity audit. They are not a contract estimate for this project and are not used as an automatic total-cost correction factor.",
    }



def _activated_mep_detail_costs(module1: dict[str,Any], location: dict[str,Any], settings: dict[str,Any]) -> dict[str,Any]:
    """PATCH 405: bridge explicitly approved Module 1 MEP detail prices into Module 5.

    Safety invariants:
      * only rows whose derived downstream_direct_cost_eligible flag is true are used;
      * a named Module 5 package scope must be explicitly replaced;
      * quantity and defensible mapped unit price must both be positive;
      * price currency must be convertible without guessing;
      * a replaced package is removed before its detail rows are added.
    """
    rows=((module1.get("quantity_takeoff") or {}).get("rows") or [])
    local_currency=str(location.get("currency") or "JPY").upper()
    details=[]; blocked=[]; replaced=set()

    def _price_in_local(price, currency):
        cur=str(currency or "").strip().upper()
        val=_f(price)
        if val<=0 or not cur:
            return None,"missing_price_or_currency"
        if cur==local_currency:
            return val,"same_currency"
        if cur=="JPY" and local_currency!="JPY":
            return None,"jpy_to_foreign_conversion_prohibited_use_local_price"
        if local_currency=="JPY" and cur!="JPY":
            # The available setting is JPY per selected local currency only.
            # It is valid for this conversion only when the source currency is
            # the selected location currency. Since local is JPY here, there is
            # no trustworthy cross-currency identity to infer.
            return None,"unsupported_foreign_to_jpy_without_source_fx"
        return None,"unsupported_cross_currency"

    for idx,row in enumerate(rows):
        if not isinstance(row,dict) or not row.get("mep_trade"):
            continue
        if not bool(row.get("downstream_direct_cost_eligible")):
            continue
        scope=str(row.get("mep_replaced_package_scope_id") or "").strip().lower()
        if not scope or not bool(row.get("mep_scope_transfer_approved")):
            blocked.append({"row_index":idx,"item":row.get("item"),"reason":"scope_transfer_not_fully_approved"})
            continue
        qty=_f(row.get("accepted_quantity",row.get("quantity")))
        unit_price=row.get("mep_unit_price_value")
        price_class=str(row.get("mep_price_source_class") or "unknown").lower()
        if qty<=0 or _f(unit_price)<=0 or price_class=="unknown":
            blocked.append({"row_index":idx,"item":row.get("item"),"reason":"quantity_or_defensible_price_missing"})
            continue
        local_price,conversion=_price_in_local(unit_price,row.get("mep_unit_price_currency"))
        if local_price is None:
            blocked.append({"row_index":idx,"item":row.get("item"),"reason":conversion,"source_currency":row.get("mep_unit_price_currency")})
            continue
        amount=qty*local_price
        replaced.add(scope)
        details.append({
            "row_index":idx,"item":row.get("item"),"mep_trade":row.get("mep_trade"),
            "replaced_package_scope_id":scope,"quantity":qty,"unit":row.get("unit"),
            "unit_price_local_currency":local_price,"currency":local_currency,"amount":amount,
            "source_price_value":_f(unit_price),"source_price_currency":row.get("mep_unit_price_currency"),
            "currency_conversion":conversion,"price_source_class":price_class,
            "price_source_type":row.get("mep_price_source_type"),
            "price_source_reference":row.get("mep_price_source_reference"),
            "price_effective_date":row.get("mep_price_effective_date"),
            "price_region":row.get("mep_price_region"),
            "monetary_ownership":"detail_replaces_named_package_scope",
        })
    return {
        "schema":"AZRAS_MEP_MODULE5_DETAIL_BRIDGE_V1",
        "detail_rows":details,"blocked_rows":blocked,
        "replaced_package_scopes":sorted(replaced),
        "detail_cost_total":sum(_f(x.get("amount")) for x in details),
        "currency":local_currency,
        "double_count_guard":"activated detail costs replace their named Module 5 package scopes; package and detail are never summed for the same scope",
    }




def _quantity_cost_parent_scope(row: dict[str,Any]) -> str | None:
    """PATCH 437: identify a parent monetary scope without creating cost.

    Used only to explain double-count ownership.  Returning a parent here never
    changes quantities or prices.
    """
    item=str(row.get("item") or "")
    low=item.lower()
    cat=str(row.get("category") or "")
    unit=str(row.get("unit") or "").lower()
    if any(x in item for x in ("AW-","Low-E","ガラス仕様未確定","窓面積")) or ("窓" in item and unit in {"m2","m²"}):
        return "glass"
    if any(x in item for x in ("AD-","SD-")) or "外部ドア等面積 合計" in item \
       or (unit in {"m2","m²"} and ("外部ドア" in item or "external door" in low)):
        return "doors"
    if any(x in item for x in (
        "断熱二重折板","ガルバリウム鋼板 上弦材","ガルバリウム鋼板 下弦材",
        "屋根実面積","屋根 area","Roof area","roof area"
    )) or (unit in {"m2","m²"} and ("屋根" in item or "roof" in low) and ("area" in low or "面積" in item)):
        # PATCH 473: any explicit roof-area control row belongs to the single
        # roofing/waterproofing monetary scope.  Keeping it unmapped would
        # falsely report an additional missing cost scope after the roofing
        # line itself is already monetized.
        return "roofing"
    # PATCH_039: English/architecture-category rows produced by the AI takeoff
    # review carried no parent, so a layer that is already inside a priced
    # control area was reported as an independent unpriced monetary gap.  These
    # rules only EXPLAIN ownership; they never create a quantity or a price.
    if unit in {"m2","m²"} and (
        "spandrel" in low
        or ("cladding" in low and ("facade" in low or "wall" in low))
    ):
        return "external_finish"
    if unit in {"m2","m²"} and (
        "ビニル床シート" in item or "vinyl sheet" in low
        or "acoustic ceiling" in low or "ceiling board" in low
        or cat.strip().lower() in {"floor finish","ceiling finish","wall finish","interior finish"}
    ):
        return "interior_finish"
    if ("シャッター" in item or "shutter" in low) and unit not in {"m2","m²"}:
        # A count-basis shutter row has no area of its own; the door/opening
        # area control already carries the shutter leaves.
        return "doors"
    if "steel partition" in low or "スチールパーティション" in item or item.startswith("PT-"):
        return "doors"
    if ("竪樋" in item or "downpipe" in low or "downspout" in low) and unit not in {"m","ｍ"}:
        return "rainwater_gutter"

    if unit in {"m2","m²"} and (
        any(x in item for x in (
            "サイディング","スパンドレル","外壁正味面積 合計","外壁仕上面積 合計",
            "外壁 area 合計","Exterior wall area total","exterior wall area total"
        ))
        or (("外壁" in item or "exterior wall" in low) and ("area" in low or "面積" in item))
    ):
        return "external_finish"
    if (
        "内装仕上数量" in cat or item.startswith("内装仕上数量")
        or any(x in item for x in ("壁仕上げ対象面積","床仕上げ対象面積","天井仕上げ対象面積"))
        or any(x in low for x in (
            "tile carpet","vinyl floor","epoxy floor coating","j-tone","j tone",
            "interior finish quantity","interior finish qty"
        ))
    ) and unit in {"m2","m²"}:
        # OA floor is substrate and explicitly not included in the current
        # interior-final-finish unit rate.
        if "OAフロア" not in item:
            return "interior_finish"
    if ("PHC杭" in item or "phc pile" in low): return "phc_pile"
    if ("シャッター" in item or "shutter" in low): return "shutter"
    if ("ガラリ" in item or "louver" in low or item.startswith("AG-1")): return "louver"
    material_key=str(row.get("material_key") or "").strip().lower()
    steel_component=str(row.get("steel_connection_component") or "").strip()
    rebar_component=str(row.get("rebar_component") or "").strip()
    if (any(x in cat for x in ("鉄骨部材","鉄骨二次部材","鉄骨接合","鉄骨集計"))
        or material_key=="structural_steel" or bool(steel_component)
        or any(x in item for x in (
            "柱脚","ベースプレート","アンカーボルト","ガセット","継手",
            "高力ボルト","ウェブ補強","スチフナ","胴縁","胴縁取付","胴縁接合",
            "代表梁標準桁","鉄骨重量","steelwork weight",
            "P1 BPL","P1 A.BOLT","P1 A.BOLT","BPL-","A.BOLT"
        ))):
        return "structural_steel"
    if ("鉄筋" in cat or "配筋" in item or material_key=="reinforcing_steel" or bool(rebar_component)):
        return "reinforcing_steel"
    if unit in {"m2","m²"} and any(x in item for x in (
        "壁仕上げ対象面積","床仕上げ対象面積","天井仕上げ対象面積",
        "wall finish target area","floor finish target area","ceiling finish target area"
    )):
        return "interior_finish"
    # AD-1 door glazing is part of the door/opening assembly; do not add it as
    # a second monetary owner when its row explicitly identifies the door.
    if unit in {"m2","m²"} and ("透明強化ガラス" in item or "tempered glass" in low):
        blob=" ".join(str(row.get(k) or "") for k in ("item","evidence","formula","reference_source","source"))
        if "AD-1" in blob:
            return "doors"
    return None



def _quantity_cost_is_supporting_evidence(row: dict[str,Any]) -> tuple[bool,str]:
    """PATCH 439: separate cost-bearing quantities from calculation/support evidence.

    This is intentionally conservative.  It only suppresses a monetary-gap flag
    when the row clearly describes geometry, orientation, spacing, a derived
    reinforcement/member-detail calculation, or another intermediate quantity.
    The row remains visible in the audit table.
    """
    item=str(row.get("item") or "").strip()
    low=item.lower()
    cat=str(row.get("category") or "").strip()
    unit=str(row.get("unit") or "").strip().lower()
    # PATCH 479: normalize harmless display separators/whitespace before semantic
    # classification. Saved Project JSONs can carry visually identical labels
    # with spaces or punctuation, which must not turn structural grid evidence
    # into a monetary gap.
    semantic_item="".join(ch for ch in item if not ch.isspace() and ch not in "・･:：/\\()（）[]【】")
    if (("代表梁" in semantic_item or "代表柱" in semantic_item or "代表部材" in semantic_item)
            and any(token in semantic_item for token in ("通り芯","通芯","軸通り","グリッド"))):
        return True,"Representative structural grid/axis evidence; structural-steel parent scope owns cost"

    geometry_tokens=(
        "faces 外壁正味 area","faces 開口方向換算延長","外周長","周長",
        "外周軸組スパン","方向 外周芯々寸法","外周芯々寸法",
        "代表梁部材間の通り芯","代表梁部材軸の通り芯","代表梁部材の通り芯",
        "代表梁標準桁の通り芯","代表梁軸の通り芯","代表梁の通り芯",
        "軸組図 x方向","軸組図 y方向",
        "外周軸組スパン","外周軸組ペア","外周軸組",
        "方向換算延長","対象通り","軸組図",
    )
    if any(x in item for x in geometry_tokens):
        return True,"Drawing geometry/orientation evidence; used to derive a parent quantity, not separately priced"

    # PATCH 476: representative-member grid/axis/count rows are structural
    # layout evidence even when Module 1 wording varies (e.g. 部材軸/標準桁/
    # 通り芯).  They must not create a separate monetary gap beside the
    # structural-steel parent line.  Restrict this rule to geometric/count
    # units so actual mass or explicitly priced material quantities remain
    # eligible for cost ownership.
    if ("代表梁" in item or "代表柱" in item or "代表部材" in item) and unit in {
        "通り","軸","本","区間","span","spans","grid","grids","line","lines"
    }:
        return True,"Representative structural-member layout/count evidence; structural-steel parent scope owns cost"

    if "基礎梁" in item and (
        any(x in item for x in (
            "図形追加延長","図形追加正味延長","正味延長","延長","芯長",
            "クリアスパン","スパン数","区間","通り芯"
        ))
        or unit in {"m","mm","本","区間","通り","span","spans"}
    ):
        # PATCH 473: foundation-beam length/count rows are derivation evidence
        # for concrete, reinforcing steel and formwork.  They are not an extra
        # trade to monetize independently.
        return True,"Foundation-beam geometry evidence; used to derive concrete/rebar/formwork quantities, not separately priced"

    if unit in {"m2","m²"} and any(x in item for x in (
        "壁仕上げ対象面積","床仕上げ対象面積","天井仕上げ対象面積",
        "仕上げ対象面積","対象面積"
    )):
        return True,"Finish target-area geometry; material finish rows or the parent finish scope own cost"

    if any(x in item for x in (
        "代表梁標準桁の通り芯","代表梁","胴縁取付 中ボルト","胴縁取付中ボルト",
        "外周胴縁","胴縁","軸組通り","方向換算鋼材重量","単位重量"
    )):
        return True,"Structural/detail layout evidence; final monetary owner is the structural-steel parent scope"

    if any(x in low for x in (
        "interior finish room-specific quantification complete",
        "interior finish room-specific quantification pending"
    )):
        return True,"Interior-finish audit/control flag; not a physical monetary owner"

    if (item.startswith(("AD-","SD-","AG-")) or any(x in item for x in ("シャッター等 数量","建具 数量"))) and unit in {
        "箇所","ヶ所","か所","個","台","pcs","pc","locations","location"
    }:
        return True,"Opening/fixture symbol count supports the area/package quantity; not separately priced"

    # Reinforcement calculation ingredients (lengths, counts, spacing-derived
    # bars/stirrups) are not separate monetary owners when final rebar is governed
    # by the reinforcement contract.
    if ("鉄筋" in cat or "配筋" in item or any(x in item for x in ("D10","D13","D22","STP"))) and unit in {
        "m","mm","本","箇所","ヶ所","か所","set","sets"
    }:
        return True,"Reinforcement calculation evidence; final monetary owner is the reinforcing-steel contract"

    # Steel member geometry/theoretical-mass ingredients remain evidence while
    # the structural-steel parent contract is held.
    material_key=str(row.get("material_key") or "").strip().lower()
    steel_component=str(row.get("steel_connection_component") or "").strip()
    if (any(x in cat for x in ("鉄骨部材","鉄骨二次部材","鉄骨接合","鉄骨集計"))
        or material_key=="structural_steel" or bool(steel_component)) and unit not in {"t","ton","tonne","kg"}:
        return True,"Structural-steel member/connection evidence; final monetary owner is the structural-steel contract"

    return False,""

def _quantity_cost_unpriced_scope_id(row: dict[str,Any]) -> str | None:
    item=str(row.get("item") or "").strip()
    low=item.lower()
    if "PHC杭" in item or "phc pile" in low: return "phc_pile"
    if "シャッター" in item or "shutter" in low: return "shutter"
    if "ガラリ" in item or "louver" in low: return "louver"
    if "屋根グラスウール" in item or ("glass wool" in low and "roof" in low): return "roof_glass_wool"
    if "透明強化ガラス" in item or "tempered glass" in low: return "tempered_glass"
    if "OAフロア" in item or "oa floor" in low: return "oa_floor"
    if "防湿" in item or "vapor barrier" in low or "vapour barrier" in low: return "vapor_barrier"
    if ("天井下地" in item and "LGS" in item.upper()) or "ceiling lgs" in low: return "ceiling_lgs"
    return None


def _canonical_unpriced_scope_row_indices(rows: list[dict[str,Any]]) -> dict[str,int]:
    """PATCH 443: choose one monetary-owner representation per unpriced scope.

    A physical trade can appear in several useful units (e.g. PHC pile count and
    installed length; shutter count and area).  Only one representation should
    remain an unpriced monetary gap; the others stay visible as supporting
    evidence.  No conversion or price is invented.
    """
    preferred_units={
        "phc_pile":("m","ｍ"),
        "shutter":("m2","m²"),
        "louver":("m2","m²"),
        "roof_glass_wool":("m3","m³"),
        "ceiling_glass_wool":("m3","m³"),
        "oa_floor":("m2","m²"),
        "vapor_barrier":("m2","m²"),
        "ground_preparation":("m3","m³"),
        "tempered_glass":("m2","m²"),
        "ceiling_lgs":("m2","m²"),
    }
    candidates={}
    for idx,row in enumerate(rows or []):
        if not isinstance(row,dict):
            continue
        scope=_quantity_cost_unpriced_scope_id(row)
        if not scope:
            key=_takeoff_cost_key(row)
            if key in {"ground_preparation"}:
                scope=key
        if not scope:
            continue
        qty=_f(row.get("accepted_quantity",row.get("quantity")))
        if qty<=0:
            continue
        unit=str(row.get("unit") or "").strip().lower()
        pref=preferred_units.get(scope,())
        rank=0 if unit in pref else 1
        # Prefer confirmed over estimated when the preferred physical unit ties.
        ev=str(row.get("evidence_status") or row.get("status") or "").strip().lower()
        conf_rank=0 if ev=="confirmed" else 1
        cand=(rank,conf_rank,idx)
        if scope not in candidates or cand<candidates[scope][0]:
            candidates[scope]=(cand,idx)
    return {scope:idx for scope,(_,idx) in candidates.items()}

def _price_basis_fingerprint(location: dict[str,Any], lines: list[dict[str,Any]], project: dict[str,Any] | None=None) -> dict[str,Any]:
    """PATCH_040: describe where this Project's unit prices came from.

    Audit only.  No price, quantity or total is changed here.  ``basis_token``
    is the field a comparison should group on: two Projects that do not share
    it were not priced on the same basis, however similar their totals look.
    """
    sources: dict[str,int] = {}
    statuses: dict[str,int] = {}
    structures: dict[str,int] = {}
    for line in lines or []:
        if not isinstance(line, dict):
            continue
        sources[str(line.get("unit_price_source") or "unresolved")]=sources.get(str(line.get("unit_price_source") or "unresolved"),0)+1
        statuses[str(line.get("pricing_status") or "unresolved")]=statuses.get(str(line.get("pricing_status") or "unresolved"),0)+1
        structures[str(line.get("pricing_structure") or "unresolved")]=structures.get(str(line.get("pricing_structure") or "unresolved"),0)+1
    mode=str(location.get("pricing_mode") or "unresolved")
    ai_lines=sum(c for k,c in statuses.items() if k.startswith("ai_"))
    # PATCH_043: prices written by 03 Compare from a comparison premise book.
    cg_lines=sum(c for k,c in statuses.items() if k.startswith("comparison_group"))
    # PATCH_052: prices taken from the fixed regional unit-price table.
    rt_lines=sum(c for k,c in statuses.items() if k.startswith("regional_price_table"))
    total_lines=sum(statuses.values())
    _cc=(project or {}).get("comparison_copy") if isinstance(project,dict) else None
    _cc=_cc if isinstance(_cc,dict) else {}
    _rt=location.get("regional_unit_price_table") if isinstance(location.get("regional_unit_price_table"),dict) else None
    if total_lines<=0:
        basis="no_priced_lines"
    elif cg_lines>0 and cg_lines+ai_lines+rt_lines>=total_lines:
        # Shared items from the premise book; method-specific items keep this
        # Project's own AI (or regional-table) price by design.
        basis="comparison_group_premise_book"
    elif cg_lines>0:
        basis="mixed_comparison_group_and_regional_database"
    elif rt_lines>=total_lines:
        basis="regional_unit_price_table"
    elif rt_lines>0 and rt_lines+ai_lines>=total_lines:
        # Items not yet in the table were priced by this Project's AI session.
        basis="regional_unit_price_table_with_ai_items"
    elif rt_lines>0:
        basis="mixed_regional_unit_price_table_and_regional_database"
    elif ai_lines>=total_lines:
        basis="ai_approximate_cost_session"
    elif ai_lines>0:
        basis="mixed_ai_and_regional_database"
    else:
        basis="regional_cost_database"
    return {
        "patch":"PATCH_040",
        "audit_only":True,
        "basis_token":basis,
        "location_pricing_mode":mode,
        "priced_line_count":total_lines,
        "ai_priced_line_count":ai_lines,
        "comparison_group_priced_line_count":cg_lines,
        "regional_price_table_priced_line_count":rt_lines,
        "regional_unit_price_table":({k:_rt.get(k) for k in ("table_file","region_key","currency","version","sha256","scale_class","gross_floor_area_m2","construction_method")} if _rt else None),
        "comparison_group_id":_cc.get("group_id"),
        "premise_book_file":_cc.get("premise_book_file"),
        "premise_book_version":_cc.get("premise_book_version"),
        "unit_price_source_counts":sources,
        "pricing_status_counts":statuses,
        "pricing_structure_counts":structures,
        "component_split_available":bool(structures.get("component_split")),
        "comparison_note_ja":(
            "単価の出所を示す監査情報。basis_token が異なるProject同士を同じ表で比較すると、"
            "工法差ではなく価格根拠差を読み違える。AI概算単価は施工込み一本値のため労務・機械が0表示になるが、"
            "これは欠落ではなく一本値に内包されている。"
        ),
        "comparison_note_en":(
            "Audit information about where unit prices came from. Comparing Projects whose basis_token differs "
            "reads a price-origin difference as a construction-method difference. An AI approximate-cost session "
            "returns installed all-in rates, so labor and equipment display as 0; that is containment in the "
            "combined rate, not a missing cost."
        ),
    }


def _quantity_cost_coverage_audit(module1: dict[str,Any], quantities: dict[str,float],
                                  excluded_quantities: list[dict[str,Any]],
                                  lines: list[dict[str,Any]]) -> dict[str,Any]:
    """Classify every Module 1 takeoff row for Module 5 visibility.

    Five user-facing classes are preserved: monetary/included, unpriced,
    unresolved/blocked, audit-only, and included-in-parent (double-count guard).
    No unit price or quantity is invented by this audit.
    """
    rows=((module1.get("quantity_takeoff") or {}).get("rows") or [])
    line_by_key={str(x.get("cost_item_key") or ""):x for x in (lines or [])}
    excluded_by_item={}
    excluded_keys=set()
    for x in excluded_quantities or []:
        excluded_by_item.setdefault(str(x.get("item") or ""),[]).append(x)
        if x.get("cost_item_key"):
            excluded_keys.add(str(x.get("cost_item_key")))
    out=[]
    seen=set()
    money_relevant_gap=0
    canonical_unpriced_row=_canonical_unpriced_scope_row_indices(rows)
    for idx,row in enumerate(rows):
        if not isinstance(row,dict):
            continue
        item=str(row.get("item") or "").strip()
        if not item:
            continue
        qty_raw=row.get("accepted_quantity",row.get("quantity"))
        qty=_f(qty_raw)
        unit=str(row.get("unit") or "")
        down=str(row.get("downstream_use") or "").strip().lower()
        cat=str(row.get("category") or "")
        cat_low=cat.strip().lower()
        semantic_role=str(row.get("semantic_role") or "").strip().lower()
        ev=str(row.get("evidence_status") or row.get("status") or "").strip().lower()
        key=_takeoff_cost_key(row)
        eligible,elig_reason=_quantity_row_cost_eligibility(row)
        parent=_quantity_cost_parent_scope(row)
        unit_low=unit.lower()
        nonphysical=unit_low in {"仕様","spec","spec.","種類","type","-","—",""}

        if (semantic_role in {"audit_only","supporting_evidence","scope_evidence_only"}
                or down.startswith("audit") or down in {"scope_evidence_only","supporting_evidence"}
                or "監査" in cat or cat=="建物規模"
                or cat_low.endswith(" audit") or cat_low in {"secondary steel member audit","steel connection audit"}):
            # PATCH 480: classify by the row's semantic/category role, not its
            # display label.  Existing Project JSONs already carry the English
            # audit category/downstream_use even when the Japanese item wording
            # varies, so representative grid/axis rows cannot become monetary gaps.
            status="audit_only"; reason="Audit/geometry evidence quantity; not a direct monetary owner"
            monetary=False
        elif nonphysical or qty_raw in (None,"") or (ev in {"unresolved","unreadable"} and qty<=0):
            status="missing_quantity"; reason="Specification/evidence exists but no adopted physical quantity"
            monetary=False
        elif ((key in {"structural_steel","reinforcing_steel"} and key in excluded_keys)
              or (parent in {"structural_steel","reinforcing_steel"} and parent in excluded_keys)):
            status="blocked_by_parent"; reason=f"Final quantity contract blocks parent scope {key or parent}"
            monetary=False
        elif bool(row.get("mep_trade")) and not bool(row.get("downstream_direct_cost_eligible")):
            # PATCH 442: MEP detail quantities remain visible, but the default
            # monetary owner is Module 5's selected lump-sum equipment package.
            # A detail becomes a direct monetary owner only through the guarded
            # MEP scope-transfer bridge (_activated_mep_detail_costs).  Treating
            # every non-transferred fixture/equipment/route row as a monetary
            # gap falsely inflated the completeness warning.
            status="supporting_evidence"
            reason="MEP physical quantity is supporting evidence; Module 5 package owns cost unless guarded detail-price scope transfer is approved"
            monetary=False
        elif _quantity_cost_is_supporting_evidence(row)[0]:
            # PATCH 477: semantic role is evaluated before the direct-cost
            # eligibility gate.  A row can be intentionally ineligible for direct
            # costing because it is geometry/audit/control evidence; that must not
            # be misreported as a monetary gap merely because a legacy Project JSON
            # carries an explicit downstream block.
            _supporting,_support_reason=_quantity_cost_is_supporting_evidence(row)
            status="supporting_evidence"
            reason=_support_reason
            monetary=False
        elif not eligible:
            if parent in {"structural_steel","reinforcing_steel"}:
                status="blocked_by_parent"; reason=f"Parent scope {parent} is held; detail is not a separate monetary owner"; monetary=False
            else:
                status="blocked"; reason=elig_reason; monetary=True
        elif key and key in line_by_key:
            status="included_in_cost_line"
            reason=f"Included in Module 5 cost line: {key}"
            monetary=False
        elif key:
            supporting,support_reason=_quantity_cost_is_supporting_evidence(row)
            if supporting:
                status="supporting_evidence"
                reason=support_reason
                monetary=False
            else:
                # A safe cost mapping exists but a priced line was not generated.
                status="unpriced"
                reason=f"Physical quantity maps to {key}, but no monetary line/unit price is available"
                monetary=True
        elif parent and parent in line_by_key:
            status="included_in_parent"
            reason=f"Included in parent package {parent}; separate addition would double count"
            monetary=False
        elif parent:
            # Parent itself may be held by a final quantity contract.
            parent_ex=[x for x in (excluded_quantities or []) if str(x.get("cost_item_key") or "")==parent]
            supporting,support_reason=_quantity_cost_is_supporting_evidence(row)
            if parent_ex:
                status="blocked_by_parent"; reason=f"Parent scope {parent} is blocked/held"; monetary=False
            elif supporting:
                status="supporting_evidence"; reason=support_reason; monetary=False
            else:
                status="unpriced"; reason=f"Parent scope {parent} has no monetary line"; monetary=True
        elif qty>0:
            supporting,support_reason=_quantity_cost_is_supporting_evidence(row)
            if supporting:
                status="supporting_evidence"
                reason=support_reason
                monetary=False
            else:
                status="unpriced_unmapped"
                reason="Physical cost-bearing quantity is available but no defensible Module 5 unit-cost mapping is registered"
                monetary=True
        else:
            status="missing_quantity"; reason="No adopted physical quantity"
            monetary=False

        # PATCH 443: when several physical representations describe the same
        # still-unpriced trade, only the canonical representation remains a
        # monetary gap.  Count/length/area evidence stays visible.
        _scope_candidate=_quantity_cost_unpriced_scope_id(row) or (key if key=="ground_preparation" else None)
        if monetary and _scope_candidate and canonical_unpriced_row.get(_scope_candidate)!=idx:
            status="supporting_evidence"
            reason=f"Supporting representation for unpriced scope {_scope_candidate}; canonical quantity row owns future unit-cost mapping"
            monetary=False

        # Deduplicate exact repeated audit representations, not distinct drawing rows.
        sig=(item,round(qty,9),unit,status,parent,key)
        if sig in seen:
            continue
        seen.add(sig)
        gap=bool(monetary and status in {"unpriced","unpriced_unmapped","blocked","blocked_by_parent"})
        scope_id=(_quantity_cost_unpriced_scope_id(row) or key or parent or f"row:{idx}") if gap else None
        out.append({
            "row_index":idx,"item":item,"quantity":qty_raw,"unit":unit,"category":cat,
            "evidence_status":ev,"downstream_use":down,"cost_item_key":key,
            "parent_cost_item_key":parent,"status":status,"reason":reason,
            "monetary_gap":gap,"monetary_scope_id":scope_id,
        })
    gap_scope_ids=sorted({str(x.get("monetary_scope_id")) for x in out if x.get("monetary_gap") and x.get("monetary_scope_id")})
    money_relevant_gap=sum(1 for x in out if x.get("monetary_gap"))
    gap_items=[]
    _seen_gap_scopes=set()
    for x in out:
        if not x.get("monetary_gap"):
            continue
        _sid=str(x.get("monetary_scope_id") or "")
        if not _sid or _sid in _seen_gap_scopes:
            continue
        _seen_gap_scopes.add(_sid)
        gap_items.append({
            "scope_id":_sid,
            "item":x.get("item"),
            "quantity":x.get("quantity"),
            "unit":x.get("unit"),
            "status":x.get("status"),
            "reason":x.get("reason"),
        })
    return {
        "schema":"AZRAS_MODULE1_TO_MODULE5_QUANTITY_COVERAGE_V8",
        "rows":out,
        "row_count":len(out),
        "monetary_gap_row_count":money_relevant_gap,
        "monetary_gap_count":len(gap_scope_ids),
        "monetary_gap_scope_ids":gap_scope_ids,
        "monetary_gap_items":gap_items,
        "policy":"Every Module 1 quantity remains visible. Monetary completeness counts unique cost scopes, not duplicate physical representations.",
    }

def _principal_cost_scope_audit(project: dict[str,Any], module1: dict[str,Any], quantities: dict[str,float], excluded_quantities: list[dict[str,Any]], lines: list[dict[str,Any]]) -> dict[str,Any]:
    """PATCH 435: make principal construction-scope completeness explicit.

    Cost totals must never look complete merely because every *displayed* line
    happens to have a price.  For each structural system, principal scopes are
    classified as priced, unpriced, blocked/excluded, or missing quantity.
    No quantity or cost is invented here.
    """
    common=project.get("common",{}) or {}
    module1_profile=module1.get("profile",{}) or {}
    construction=module1_profile.get("construction",{}) or {}
    drawing_profile=((module1.get("drawing_analysis",{}) or {}).get("profile",{}) or {})
    drawing_construction=drawing_profile.get("construction",{}) or {}
    cfg=common.get("detailed_configuration",{}) or {}
    general=cfg.get("general",{}) or {}
    joined=" ".join(str(x or "").lower() for x in (
        common.get("construction_method_id"), common.get("construction_method_detail_id"),
        construction.get("structural_system"), drawing_construction.get("structural_system"),
        general.get("structure"), general.get("method"),
        ((drawing_profile.get("structure_override") or {}).get("selected")),
    ))
    method=_construction_method(project)
    if any(x in joined for x in ("steel_frame","steel structure","s造","重量鉄骨","鉄骨")):
        system="steel_frame"
        required=["structural_steel","concrete","reinforcing_steel","formwork"]
    elif method=="rc_frame":
        system="rc_frame"; required=["concrete","reinforcing_steel","formwork"]
    elif method=="wood_frame":
        system="wood_frame"; required=["dimension_lumber","concrete","reinforcing_steel","formwork"]
    elif method=="azras":
        system="azras"; required=["concrete","reinforcing_steel","formwork","dimension_lumber"]
    else:
        system=method or "general"; required=[]

    line_by_key={str(x.get("cost_item_key")):x for x in (lines or [])}
    excluded_by_key={}
    for x in excluded_quantities or []:
        excluded_by_key.setdefault(str(x.get("cost_item_key") or ""),[]).append(x)

    items=[]
    for key in required:
        line=line_by_key.get(key)
        qty=_f(quantities.get(key))
        ex=excluded_by_key.get(key) or []
        if line:
            ps=str(line.get("pricing_display_status") or "priced").lower()
            status="unpriced" if ps=="unpriced" else "priced"
            reason=("Unit price is not registered" if status=="unpriced" else "Quantity and price are included in the cost total")
            unit=line.get("unit")
            qty=_f(line.get("quantity"))
        elif ex:
            status="blocked"
            reason="; ".join(str(x.get("reason") or "excluded by downstream quantity gate") for x in ex)
            unit=ex[0].get("unit")
            qty=max([_f(x.get("quantity")) for x in ex] or [qty])
        elif qty>0:
            status="missing_unit_cost_definition"
            reason="Quantity exists but no Module 5 cost line was produced"
            unit=None
        else:
            status="missing_quantity"
            reason="Principal construction scope has no adopted quantity ready for Module 5"
            unit=None
        items.append({"cost_item_key":key,"status":status,"quantity":qty if qty>0 else None,"unit":unit,"reason":reason})

    # Foundation preparation is a principal scope group for all structural systems.
    foundation_keys=["excavation","backfill","imported_fill","soil_disposal","blinding_concrete","ground_preparation"]
    if required:
        present=[k for k in foundation_keys if k in line_by_key]
        excluded=[k for k in foundation_keys if k in excluded_by_key]
        quantity_present=[k for k in foundation_keys if _f(quantities.get(k))>0]
        if present:
            statuses=[str(line_by_key[k].get("pricing_display_status") or "priced").lower() for k in present]
            group_status="unpriced" if any(x=="unpriced" for x in statuses) else "priced"
            reason="Foundation preparation quantities are present" + (" but one or more unit prices are unregistered" if group_status=="unpriced" else " and priced")
        elif excluded:
            group_status="blocked"; reason="Foundation preparation quantity evidence exists but is blocked/excluded"
        elif quantity_present:
            group_status="missing_unit_cost_definition"; reason="Foundation preparation quantities exist but no cost lines were produced"
        else:
            group_status="missing_quantity"; reason="Foundation earthwork/groundwork quantities are not resolved for Module 5"
        items.append({"cost_item_key":"foundation_preparation_group","status":group_status,"quantity":None,"unit":None,"reason":reason,"component_keys":foundation_keys})

    incomplete=[x for x in items if x.get("status")!="priced"]
    return {
        "schema":"AZRAS_MODULE5_SCOPE_COMPLETENESS_V1",
        "structural_system":system,
        "items":items,
        "is_complete":not incomplete,
        "incomplete_scope_count":len(incomplete),
        "blocking_or_missing_scope_count":sum(1 for x in incomplete if x.get("status") in {"blocked","missing_quantity","missing_unit_cost_definition"}),
        "unpriced_scope_count":sum(1 for x in incomplete if x.get("status")=="unpriced"),
        "policy":"Completeness is independent of whether all currently displayed cost lines are priced; missing/blocked principal scopes make the total provisional.",
    }

def _equipment_price_is_current_market(key, cost, cost_basis, database) -> bool:
    """PATCH_041: is this JPY equipment package price already a 2026 market price?

    Only the common-database default (``default_cost_jpy``) is a legacy price
    that the 2026 market calibration is meant to lift.  Anything else is a price
    somebody supplied for the current market and must be used as given:

    * ``ai_approximate_cost_session_local_currency`` - an imported AI session.
    * ``ui_local_currency`` whose value differs from the database default - the
      user (or an AI import that filled the entry widgets) replaced the default
      with a current figure.  The Module 5 UI pre-fills JPY projects with the
      database default and tags it ``ui_local_currency``, so the value itself is
      the only reliable discriminator; an untouched default keeps being
      calibrated exactly as before.
    """
    basis=str(cost_basis or "").strip().lower()
    if basis.startswith("ai_approximate_cost_session"):
        return True
    if basis=="database_default_jpy":
        return False
    default=_f(((database.get("equipment_packages",{}) or {}).get(key,{}) or {}).get("default_cost_jpy"))
    if default<=0:
        return _f(cost)>0
    return abs(_f(cost)-default)>0.5


def _apply_session_ai_equipment_overlay(equipment_selection, session_overlay):
    """Overlay session-only AI local-currency equipment package prices.

    PATCH 469: equipment prices imported by Module 5 must reach the calculation
    engine even if the UI entry widgets still contain zero.  The overlay is the
    authoritative session data path; no global database is modified.
    """
    selection={k:dict(v or {}) for k,v in (equipment_selection or {}).items()}
    if not isinstance(session_overlay,dict):
        return selection
    raw=session_overlay.get("equipment_packages") or []
    if isinstance(raw,dict):
        records=list(raw.values())
    elif isinstance(raw,list):
        records=raw
    else:
        records=[]
    for rec in records:
        if not isinstance(rec,dict):
            continue
        key=str(rec.get("package_key") or "").strip()
        cost=_f(rec.get("cost"))
        if not key or cost<=0:
            continue
        item=selection.setdefault(key,{})
        item["include"]=True
        item["cost"]=cost
        item["cost_basis"]="ai_approximate_cost_session_local_currency"
        item["ai_pricing_mode"]=rec.get("pricing_mode")
        item["ai_unit_rate"]=rec.get("unit_rate")
        item["ai_currency"]=rec.get("currency")
        item["ai_certainty"]=rec.get("certainty")
        item["ai_display_color"]=rec.get("display_color")
        item["ai_agreement_count"]=rec.get("ai_agreement_count")
        item["ai_reviewer"]=rec.get("reviewer")
        item["ai_source_json"]=rec.get("source_json")
        item["ai_source"]=rec.get("source")
    return selection


def calculate_construction_cost(project: dict[str, Any], database: dict[str, Any],
                                location_key: str, settings: dict[str, Any],
                                equipment_selection: dict[str, dict[str, Any]]) -> dict[str, Any]:
    # PATCH 423: construction cost must never consume an explicitly stale
    # Module 1 output retained only for audit/history.
    module1=require_current_module_output(project,"module1","Module 1")
    _base_location=database["locations"][location_key]
    _session_overlay=_base_location.get("_session_ai_unit_cost_overlay") if isinstance(_base_location,dict) else None
    # PATCH_038: an in-memory AI overlay is Project-specific even when two
    # Projects share the same regional profile. Never leak Project A prices
    # into Project B merely because both use the same location key.
    if isinstance(_session_overlay,dict):
        _binding=_session_overlay.get("project_binding") or {}
        _bound_id=str(_binding.get("project_id") or "").strip() if isinstance(_binding,dict) else ""
        _project_id=str(project.get("project_id") or "").strip()
        if _bound_id and _project_id and _bound_id!=_project_id:
            _session_overlay=None
    location=load_external_regional_cost_dataset(_base_location)
    # PATCH 464: current AI research is session-only and overlays static data
    # after file resolution. No regional-cost DB file is modified.
    if isinstance(_session_overlay,dict):
        location=dict(location)
        merged=dict(location.get("unit_costs") or {})
        for _k,_v in ((_session_overlay.get("unit_costs") or {}).items()):
            if isinstance(_v,dict): merged[str(_k)]=dict(_v)
        location["unit_costs"]=merged
        if isinstance(_session_overlay.get("unit_cost_dataset"),dict):
            location["unit_cost_dataset"]=dict(_session_overlay["unit_cost_dataset"])
        location["pricing_mode"]="ai_approximate_cost_session_local_currency"
        location["pricing_status"]="estimated"
        location["session_ai_cost_overlay_applied"]=True
        # PATCH_052: reference of the regional unit-price table, audit only.
        if isinstance(_session_overlay.get("regional_unit_price_table"),dict):
            location["regional_unit_price_table"]={k:v for k,v in _session_overlay["regional_unit_price_table"].items() if k!="replaced_ai_records"}
    base_costs=database["base_unit_costs_jpy"]
    quantities,quantity_provenance,excluded_quantities=extract_quantities(project,module1,settings)
    common_2004_enabled,common_escalation,common_market_calibration=_common_2004_price_settings(settings)
    # PATCH 469: consume AI equipment-package prices from the session overlay
    # before residential-scope normalization and before the foreign-price gate.
    # This prevents the engine from seeing stale/zero UI widget values after a
    # successful multi-AI import.
    equipment_selection=_apply_session_ai_equipment_overlay(equipment_selection,_session_overlay)
    equipment_selection,equipment_scope_policy=_normalize_residential_equipment_selection(
        project,database,equipment_selection,location
    )
    mep_detail_bridge=_activated_mep_detail_costs(module1,location,settings)
    replaced_mep_packages=set(mep_detail_bridge.get("replaced_package_scopes") or [])

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
        expected_unit=COST_KEY_CANONICAL_UNIT.get(key)
        database_unit=_normalize_physical_unit(unit.get("unit"))
        if expected_unit and database_unit!=expected_unit:
            raise ValueError(
                f"Unit-dimension contract mismatch for {key}: quantity expects {expected_unit}, "
                f"but unit-cost database uses {unit.get('unit')!r}."
            )
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
                unit,location,key,material_index,labor_index,0.0
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
                if override_applied else str((((location.get("unit_costs") or {}).get(key) or {}).get("pricing_status") or unit.get("pricing_status","priced")))
            ),
            # PATCH 419: keep a UI-safe, explicit line pricing state.  A row
            # whose database unit-cost components are all zero because a real
            # unit price has not been registered must never look like a true
            # zero-cost construction item in Module 5.
            "pricing_display_status": (
                "unpriced"
                if (not override_applied
                    and (
                        str(unit_price_source or "").startswith("foreign_local_unit_unpriced_")
                        or (
                            str(unit.get("pricing_status") or "").strip().lower() in {"unit_price_required","unpriced","price_required"}
                            and all(abs(_f(x)) < 1e-12 for x in (material_unit,labor_unit,equipment_unit))
                        )
                    ))
                else ("confirmed_override" if (override_applied or str((((location.get("unit_costs") or {}).get(key) or {}).get("pricing_status") or "")).lower() in {"user_manual_current_project_override","user_manual_detail_rollup"}) else
                      ("estimated_price" if (
                          str((((location.get("unit_costs") or {}).get(key) or {}).get("pricing_status") or "")).lower() in {"ai_rational_estimate_provisional","ai_multi_disagreement_provisional","ai_single_source_provisional","ai_post_review_rechecked_provisional","ai_primary_basis_provisional","ai_research_provisional","regional_price_table_fixed","estimated","provisional"}
                          or str((quantity_provenance.get(key) or {}).get("source_type") or "").lower() in {"module1_blocked_contract_planning_estimate","method_fallback_estimate","planning_estimate"}
                          or str((quantity_provenance.get(key) or {}).get("certainty") or "").lower() in {"estimated","provisional"}
                      ) else "confirmed_price"))
            ),
            "scope_note_ja": unit.get("scope_note_ja"),
            "unit_price_override_current_year_local_currency":override_current_rate if override_applied else None,
            "unit_price_override_current_year_jpy":override_current_rate if override_applied else None,
            "unit_price_override_bypasses_2004_basis":True if override_applied else False
            ,"unit_price_source":unit_price_source
            ,"pricing_structure":("installed_all_in" if unit_price_source=="local_installed_all_in" else "component_split")
            ,"installed_all_in_unit_cost":(material_unit if unit_price_source=="local_installed_all_in" else None)
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
        if str(key).lower() in replaced_mep_packages:
            continue
        cost=_f(item.get("cost"))
        equipment_cost_basis=str(item.get("cost_basis") or "ui_local_currency")
        _equipment_currency=str(location.get("currency") or "JPY").upper()
        if _equipment_currency!="JPY":
            if equipment_cost_basis=="database_default_jpy":
                raise ValueError(
                    "Foreign equipment cost requires a local-currency package price. "
                    "AZRAS does not convert the Japanese JPY default package price by FX."
                )
            if cost<=0:
                # PATCH 482: an unresolved foreign equipment package is a valid
                # planning state, not a fatal calculation error.  Keep it explicit
                # as an unpriced package and continue; never substitute the JPY
                # default or an FX-converted value.
                db_pkg=(database.get("equipment_packages",{}) or {}).get(key,{})
                equipment_packages.append({
                    "package_key":key,"name_ja":db_pkg.get("ja",key),
                    "name_en":db_pkg.get("en",key),"cost":None,
                    "cost_basis":equipment_cost_basis,
                    "pricing_status":"unpriced",
                    "certainty":"unknown",
                    "display_color":"red",
                    "ai_pricing_mode":item.get("ai_pricing_mode"),
                    "ai_unit_rate":item.get("ai_unit_rate"),
                    "ai_agreement_count":item.get("ai_agreement_count"),
                    "ai_reviewer":item.get("ai_reviewer"),
                    "ai_source_json":item.get("ai_source_json"),
                    "ai_source_url":None,
                    "market_cost_group":"building_services_equipment",
                    "market_calibration_factor_2026":1.0,
                    "market_calibration_source_2026":"foreign_local_currency_price_unresolved_no_japan_fallback",
                    "unpriced_reason":"local_currency_equipment_price_unresolved",
                })
                continue
            # A foreign local-currency package price is already a current local
            # market input. Never apply the Aichi/Japan market-calibration factor.
            equipment_market_factor=1.0
            equipment_market_source="foreign_local_currency_price_no_japan_calibration"
        elif common_2004_enabled and _equipment_price_is_current_market(key,cost,equipment_cost_basis,database):
            # PATCH_041: a current-market package price is not recalibrated.
            #
            # The 2026 market calibration exists to bring the common-database
            # package defaults (default_cost_jpy) up to the Aichi 2026 market.
            # It was also being applied to prices that are ALREADY 2026 market
            # figures - an imported AI approximate-cost package, or a price the
            # user entered in place of the default - which cut them to 61%
            # (wood/AZRAS) or 85% (RC).  Two consequences followed:
            #   * every such Project's equipment total was understated, and
            #   * the SAME package price produced different totals purely
            #     because of the construction method, so a multi-Project
            #     comparison read a calibration artefact as a building
            #     difference (identical MEP scope, 2.4M JPY apart).
            # Unit-cost lines already follow this rule (PATCH 072: verified local
            # components bypass calibration) and foreign packages already do too
            # (PATCH 463); JPY equipment packages were the one path left over.
            equipment_market_factor=1.0
            equipment_market_source="current_market_package_price_no_recalibration"
        elif common_2004_enabled:
            equipment_market_factor,equipment_market_source=_market_calibration_factor_2026(
                _construction_method(project),"building_services_equipment",settings
            )
            cost*=equipment_market_factor
        else:
            equipment_market_factor=1.0
            equipment_market_source="market_calibration_disabled"
        additional_equipment+=cost
        db_pkg=(database.get("equipment_packages",{}) or {}).get(key,{})
        _ai_source=item.get("ai_source") if isinstance(item.get("ai_source"),dict) else {}
        equipment_packages.append({"package_key":key,"name_ja":db_pkg.get("ja",key),
                                   "name_en":db_pkg.get("en",key),"cost":cost,
                                   "cost_basis":equipment_cost_basis,
                                   "pricing_status": ("estimated_price" if str(item.get("ai_certainty") or "").lower()=="estimated" else ("confirmed_price" if str(item.get("ai_certainty") or "").lower()=="confirmed" else None)),
                                   "certainty":item.get("ai_certainty"),
                                   "display_color":item.get("ai_display_color"),
                                   "ai_pricing_mode":item.get("ai_pricing_mode"),
                                   "ai_unit_rate":item.get("ai_unit_rate"),
                                   "ai_agreement_count":item.get("ai_agreement_count"),
                                   "ai_reviewer":item.get("ai_reviewer"),
                                   "ai_source_json":item.get("ai_source_json"),
                                   "ai_source_url":_ai_source.get("source_url"),
                                   "market_cost_group":"building_services_equipment",
                                   "market_calibration_factor_2026":equipment_market_factor,
                                   "market_calibration_source_2026":equipment_market_source})

    # PATCH 405: approved detail rows are all-in MEP item prices. They replace,
    # rather than stack on top of, the named package scope. They are kept
    # separate from structural material/labor/equipment component totals.
    mep_detail_cost=_f(mep_detail_bridge.get("detail_cost_total"))
    additional_equipment+=mep_detail_cost

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
        "current_year_rate_overrides_local_currency_per_unit":rc_foundation_unit_price_overrides,
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
    # PATCH 432: the built-in whole-building benchmark is explicitly Aichi/Japan
    # and denominated in JPY.  It must not be compared numerically with a USD,
    # GBP, EUR, etc. project estimate.  Overseas projects keep the diagnostic
    # breakdown but have no applicable external benchmark until a regional
    # benchmark/provider is supplied.
    _result_currency=str(location.get("currency") or "JPY").upper()
    if _result_currency != "JPY":
        benchmark={**benchmark,
                   "benchmark_jpy_per_m2":None,
                   "benchmark_jpy_per_tsubo":None,
                   "not_applicable_reason":"Japan/Aichi JPY benchmark is not applicable to a non-JPY regional project."}
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
        _result_currency,
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

    scope_completeness_audit=_principal_cost_scope_audit(project,module1,quantities,excluded_quantities,lines)
    quantity_cost_coverage_audit=_quantity_cost_coverage_audit(module1,quantities,excluded_quantities,lines)
    _line_by_key={str(x.get("cost_item_key") or ""):x for x in lines}
    quantity_to_cost_line_integrity=[]
    for _key,_qty in sorted(quantities.items()):
        _line=_line_by_key.get(_key)
        _expected=COST_KEY_CANONICAL_UNIT.get(_key)
        _line_unit=_normalize_physical_unit((_line or {}).get("unit"))
        _status=(
            "priced_or_explicit_unpriced_line"
            if _line is not None and (_line_unit==_expected or _expected is None)
            else "missing_cost_line"
        )
        quantity_to_cost_line_integrity.append({
            "cost_item_key":_key,
            "quantity":_qty,
            "expected_unit":_expected,
            "cost_line_unit":(_line or {}).get("unit"),
            "pricing_display_status":(_line or {}).get("pricing_display_status"),
            "status":_status,
        })
    quantity_to_cost_line_integrity_audit={
        "schema":"AZRAS_QUANTITY_TO_COST_LINE_INTEGRITY_V1",
        "status":(
            "pass"
            if all(x.get("status")=="priced_or_explicit_unpriced_line" for x in quantity_to_cost_line_integrity)
            else "fail"
        ),
        "items":quantity_to_cost_line_integrity,
        "missing_cost_line_keys":[
            x.get("cost_item_key") for x in quantity_to_cost_line_integrity
            if x.get("status")!="priced_or_explicit_unpriced_line"
        ],
        "policy":"Every adopted Module 5 quantity must produce one matching-dimension cost line, priced or explicitly unpriced.",
    }
    # PATCH 482: unresolved included equipment packages are part of the same
    # provisional-total policy as unpriced construction lines.  Their presence
    # must keep the result explicitly partial even though calculation continues.
    _unpriced_equipment_packages=[
        x for x in equipment_packages
        if str(x.get("pricing_status") or "").lower()=="unpriced" or x.get("cost") is None
    ]
    construction_cost_is_partial=(
        (not bool(scope_completeness_audit.get("is_complete")))
        or any(x.get("pricing_display_status")=="unpriced" for x in lines)
        or bool(_unpriced_equipment_packages)
        or int(quantity_cost_coverage_audit.get("monetary_gap_count") or 0)>0
    )

    return {
        "version":"9.4",
        "module":"module5",
        "upstream_module1_fingerprint":module1_cost_dependency_fingerprint(project),
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
        # PATCH_040: make the price ORIGIN comparable between Projects.
        #
        # Two Projects of the same building can be priced from completely
        # different bases - an imported AI approximate-cost session of
        # installed all-in rates, or the built-in regional city estimate with a
        # material/labor/equipment split - and the saved result gave no single
        # field that said which.  A multi-Project comparison then reads a pure
        # price-origin difference as a construction-method difference.  This
        # block states the origin explicitly so any consumer can refuse, or at
        # least annotate, a mixed-basis comparison.  It changes no cost.
        "price_basis_fingerprint":_price_basis_fingerprint(location,lines,project),
        "construction_cost_fx_policy":"no_jpy_to_foreign_conversion_local_market_prices_required",
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
                all(
                    k in [x.get("package_key") for x in equipment_packages] or k in replaced_mep_packages
                    for k in equipment_scope_policy.get("standard_packages",[])
                )
            ) else "check_scope",
            "replaced_packages_by_mep_detail":sorted(replaced_mep_packages),
            "mep_detail_cost":mep_detail_cost,
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
        "cost_scope_completeness_audit":scope_completeness_audit,
        "quantity_cost_coverage_audit":quantity_cost_coverage_audit,
        "quantity_to_cost_line_integrity_audit":quantity_to_cost_line_integrity_audit,
        "construction_cost_is_partial":construction_cost_is_partial,
        # PATCH 419: explicit list of quantities whose cost is intentionally
        # absent because no defensible unit rate has been registered.  These
        # quantities remain in scope, but their zero numeric line total must
        # never be interpreted as a true zero-cost item.
        "unpriced_cost_lines":[
            {
                "cost_item_key":x.get("cost_item_key"),
                "quantity":x.get("quantity"),
                "unit":x.get("unit"),
                "quantity_source":x.get("quantity_source"),
                "pricing_status":x.get("pricing_status"),
            }
            for x in lines if x.get("pricing_display_status")=="unpriced"
        ],
        "priced_total_excludes_unpriced_items":True,
        "cost_lines":lines,
        "equipment_packages":equipment_packages,
        "unpriced_equipment_packages":_unpriced_equipment_packages,
        "unpriced_equipment_package_count":len(_unpriced_equipment_packages),
        "mep_detail_cost_bridge":mep_detail_bridge,
        "summary":{
            "direct_construction_cost":adjusted_direct,
            "direct_cost_breakdown_policy":"all_in_rates_are_not_forced_into_material_labor_equipment_components",
            "direct_material_cost":material_total*condition_factor,
            "direct_labor_cost":labor_total*condition_factor,
            "direct_equipment_cost":equipment_total*condition_factor,
            "direct_cost_before_conditions":direct_before_conditions,
            "condition_adjustment":condition_adjustment,
            "adjusted_direct_cost":adjusted_direct,
            "additional_equipment_cost":additional_equipment,
            "mep_detail_replacement_cost":mep_detail_cost,
            "overhead_cost":overhead,
            "contingency_cost":contingency,
            "design_supervision_cost":design,
            "subtotal_before_tax":subtotal_before_tax,
            "tax_amount":tax,
            "total_construction_cost":total,
            "cost_per_m2":total/gfa,
            "estimated_construction_duration_months":duration
        },
        "status":"provisional_planning_comparison",
        "disclaimer":"Planning comparison only; replace unit costs with current verified regional quotations."
    }
