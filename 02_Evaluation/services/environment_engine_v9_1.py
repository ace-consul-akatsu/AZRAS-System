
from __future__ import annotations
from dataclasses import asdict
from pathlib import Path
from typing import Any
import json

from services.dynamic_thermal_model_v9 import ModelConfig, read_weather, simulate
from services.pv_energy_engine_v9_4_1 import calculate_pv_energy
from services.envelope_insulation_model_v1 import (
    lambda_for, scenario_u_from_baseline, mass_coupling, normalize_position, insulation_r
)

def _f(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default



def _resolve_module1(project: dict[str, Any]) -> dict[str, Any]:
    """Return the sole current Planning Module 1 authority.

    PATCH_213 data-responsibility rule:
    Evaluation consumes only ``module_outputs.module1``.  Legacy root-level
    ``module1`` / ``modules.module1`` branches must never outrank or replace the
    formal Planning result.
    """
    if not isinstance(project, dict):
        return {}
    outputs = project.get("module_outputs")
    if not isinstance(outputs, dict):
        return {}
    module1 = outputs.get("module1")
    return module1 if isinstance(module1, dict) else {}

def _accepted_quantity_rows(module1: dict[str, Any]) -> list[dict[str, Any]]:
    """Return ONLY the current canonical Planning quantity_takeoff rows.

    PATCH_208 responsibility boundary:
    Planning owns drawing/AI/human quantity resolution and persists the adopted
    quantity table. Evaluation must not recover, append, or reconstruct missing
    quantities from ``ai_takeoff_import_payload`` or provider-review evidence.
    Missing canonical rows remain missing and must be corrected in Planning.
    """
    takeoff = module1.get("quantity_takeoff") or {}
    if not isinstance(takeoff, dict):
        return []
    return [dict(r) for r in (takeoff.get("rows") or []) if isinstance(r, dict)]

def _accepted_quantities(module1: dict[str, Any]) -> dict[str, float]:
    return {
        str(r.get("item")): _f(r.get("accepted_quantity", r.get("quantity")))
        for r in _accepted_quantity_rows(module1)
    }

def _component_concrete_quantities(module1: dict[str, Any]) -> dict[str, Any]:
    """PATCH_527: classify accepted Module 1 concrete takeoff by physical component.

    The bridge is bilingual and rejects summary/candidate duplication. Exact
    component rows win over range/location candidates. No quantity is invented:
    every adopted volume comes from an accepted Module 1 m3/m³ row.
    """
    out = {
        "exterior_rc_m3": 0.0,
        "partition_rc_m3": 0.0,
        "generic_rc_wall_m3": 0.0,
        "frame_rc_m3": 0.0,
        "ground_slab_m3": 0.0,
        "upper_slab_m3": 0.0,
        "foundation_rc_m3": 0.0,
        "matched_rows": [],
    }
    rows=[r for r in _accepted_quantity_rows(module1) if isinstance(r,dict)]
    selected=str(module1.get("selected_building_profile") or "").strip().lower()
    candidates={k:[] for k in (
        "exterior_rc_m3","partition_rc_m3","generic_rc_wall_m3","frame_rc_m3",
        "ground_slab_m3","upper_slab_m3","foundation_rc_m3"
    )}

    def norm(v: Any) -> str:
        return str(v or "").strip().lower().replace("　"," ")

    def add_candidate(bucket: str, row: dict[str, Any], reason: str, priority: int=50) -> None:
        q=max(0.0,_f(row.get("accepted_quantity",row.get("quantity"))))
        if q<=0.0:
            return
        candidates[bucket].append((priority,q,row,reason))

    for row in rows:
        unit=norm(row.get("unit")).replace(" ","")
        if unit not in {"m3","m³","㎥"}:
            continue
        item=norm(row.get("item"))
        cat=norm(row.get("category"))
        text=f"{cat} {item}"
        # Concrete bridge must never classify insulation merely because its
        # label contains "RC exterior wall".
        if not ("structure" in cat or "構造" in cat or "concrete" in text or "コンクリート" in text or item in {"rc wall","rc壁"}):
            continue
        if any(t in item for t in ("合計","小計","total concrete","total rc concrete","concrete total","subtotal")):
            continue

        if any(k in text for k in (
            "外周rc壁","rc外壁","外壁rc","外周壁コンクリート",
            "rc exterior wall concrete","exterior rc wall concrete","azras exterior rc wall"
        )):
            add_candidate("exterior_rc_m3",row,"exterior_rc_keyword",90)
            continue
        if any(k in text for k in (
            "内部rc壁","rc隔壁","隔壁rc","戸境rc","間仕切rc","内部壁コンクリート",
            "internal rc wall concrete","rc partition wall concrete","dwelling-separation rc wall"
        )):
            add_candidate("partition_rc_m3",row,"partition_rc_keyword",90)
            continue

        if item in {"rc wall concrete","rc壁コンクリート","rc wall"}:
            add_candidate("generic_rc_wall_m3",row,"generic_rc_wall_exact",100)
            continue
        if "rc wall concrete location-specific candidate" in item:
            add_candidate("generic_rc_wall_m3",row,"generic_rc_wall_location_candidate",80)
            continue
        if "rc wall concrete-range candidate" in item or "rc wall concrete range candidate" in item:
            add_candidate("generic_rc_wall_m3",row,"generic_rc_wall_range_candidate",60)
            continue

        if selected=="azras" and any(k in text for k in ("ベタ基礎コンクリート","mat foundation concrete","foundation / slab-on-grade concrete")):
            add_candidate("ground_slab_m3",row,"azras_mat_foundation_thermal_mass",100 if "ベタ基礎" in text else 80)
            continue
        if any(k in text for k in (
            "土間コンクリート","床土間","土間rc","slab-on-grade concrete","slab on grade concrete",
            "ground slab concrete","基礎・土間コンクリート"
        )):
            add_candidate("ground_slab_m3",row,"ground_slab_keyword",90)
            continue
        if any(k in text for k in (
            "上階・屋根スラブ","上階スラブ","屋根スラブ","床スラブ",
            "upper slab","roof slab","upper-floor slab","upper floor slab"
        )):
            add_candidate("upper_slab_m3",row,"upper_slab_keyword",90)
            continue
        if any(k in text for k in (
            "基礎梁","地中梁","杭頭基礎","独立基礎","フーチング","耐圧盤","基礎コンクリート",
            "isolated footing","grade beam concrete","underground foundation","footing concrete"
        )):
            _pri=100 if any(k in text for k in ("独立基礎・地中梁","underground foundation")) else 60
            add_candidate("foundation_rc_m3",row,"foundation_keyword",_pri)
            continue
        if (("柱" in text and "コンクリート" in text) or
            ("梁" in text and "コンクリート" in text) or
            ("column concrete" in text) or ("beam concrete" in text)):
            add_candidate("frame_rc_m3",row,"frame_rc_keyword",90)
            continue

    for bucket, vals in candidates.items():
        if not vals:
            continue
        if bucket in {"generic_rc_wall_m3","ground_slab_m3","foundation_rc_m3"}:
            pr,q,row,reason=max(vals,key=lambda x:(x[0],x[1]))
            out[bucket]=q
            chosen=[(pr,q,row,reason)]
        else:
            seen=set(); chosen=[]
            for rec in sorted(vals,key=lambda x:-x[0]):
                pr,q,row,reason=rec
                sig=(norm(row.get("item")),round(q,9))
                if sig in seen:
                    continue
                seen.add(sig); chosen.append(rec)
                out[bucket]+=q
        for pr,q,row,reason in chosen:
            out["matched_rows"].append({
                "bucket":bucket,
                "category":str(row.get("category") or ""),
                "item":str(row.get("item") or ""),
                "quantity_m3":q,
                "reason":reason,
                "priority":pr,
            })
    return out

def _assembly_u_value(assembly: dict[str, Any], default: float) -> float:
    """Return a planning U-value from an explicit Module 1 insulation assembly.

    PATCH_384: Module 1 often knows insulation material/thickness before the
    legacy performance.envelope.insulation_details contract has a numeric U.
    Use the shared material lambda vocabulary (or an explicit lambda) rather
    than discarding that drawing evidence and falling back to a generic U.
    The 0.17 m2K/W term is the existing reduced-model non-insulation resistance.
    """
    material = str(assembly.get("material", ""))
    conductivity = lambda_for(material, assembly.get("lambda_W_mK"))
    if conductivity is None:
        aliases = {
            "Glass wool": 0.038,
            "Rock wool": 0.038,
        }
        conductivity = aliases.get(material)
    thickness_m = _f(assembly.get("thickness_mm")) / 1000.0
    if thickness_m <= 0 or not conductivity or conductivity <= 0:
        return default
    return 1.0 / max(0.10, 0.17 + thickness_m / float(conductivity))

def _other_equipment_kwh(module1: dict[str, Any]) -> float:
    """Recalculate non-HVAC equipment from the saved per-dwelling input.

    This avoids stale Module 1 totals and prevents nominal air-conditioning
    energy from being counted again on top of the dynamic HVAC result.
    """
    snapshot = module1.get("_input_snapshot") or {}
    items = snapshot.get("equipment") or []
    if not items:
        items = (module1.get("building_performance", {}).get("equipment", {}).get("items") or [])
    total = 0.0
    for item in items:
        if str(item.get("name", "")) == "air_conditioning":
            continue
        rated_kw = _f(item.get("rated_kw"))
        quantity = _f(item.get("quantity"), 1.0)
        hours = _f(item.get("annual_hours"))
        load_factor = _f(item.get("load_factor"), 1.0)
        efficiency = max(_f(item.get("efficiency"), 1.0), 0.01)
        total += rated_kw * quantity * hours * load_factor / efficiency
    if total > 0:
        return total
    equipment = module1.get("building_performance", {}).get("equipment", {})
    return _f(equipment.get("annual_other_equipment_electricity_kwh"),
              _f(equipment.get("annual_electricity_kwh")))

def _build_config_with_breakdown(module1: dict[str, Any], common: dict[str, Any],
                                 settings: dict[str, Any]) -> tuple[ModelConfig, dict[str, Any]]:
    profile = module1.get("profile", {})
    perf = module1.get("building_performance", {})
    geometry = profile.get("geometry", {})
    construction = profile.get("construction", {})
    surfaces = profile.get("surfaces", [])

    # PATCH_208: facade/orientation evidence used by Evaluation must already
    # have been adopted and saved by Planning into the formal Module 1 profile.
    # Raw AI payloads/provider snapshots are evidence, not Evaluation inputs.
    # If formal surfaces are absent, the existing downstream unresolved/fallback
    # handling applies; Evaluation does not reconstruct them from AI history.

    envelope = perf.get("envelope", {})
    quantities = _accepted_quantities(module1)
    concrete_components = _component_concrete_quantities(module1)

    floor_area = _f(common.get("scale_gfa_m2"))
    if floor_area <= 0:
        floor_area = _f(geometry.get("conditioned_floor_area_m2"),
                        _f(geometry.get("footprint_area_m2")) * 2.0)
    footprint = _f(geometry.get("footprint_area_m2"), floor_area / 2.0)
    volume = _f(geometry.get("conditioned_volume_m3"), floor_area * 2.5)

    # PATCH_403: resolve envelope RC-wall area from the strongest exterior-only
    # surface evidence.  The legacy rc_wall_area_m2 field may be absent even
    # when Module 1 already resolved exterior RC volume/surface.  Using zero
    # here makes an RC-wall insulation comparison numerically inert.
    rc_area = _f(construction.get("exterior_rc_interior_surface_m2"), 0.0)
    rc_area_source = "construction.exterior_rc_interior_surface_m2" if rc_area > 0.0 else "unresolved"
    if rc_area <= 0.0:
        rc_area = _f(construction.get("rc_wall_area_m2"), 0.0)
        if rc_area > 0.0:
            rc_area_source = "construction.rc_wall_area_m2"
    light_area = _f(construction.get("light_wall_area_m2"))

    # PATCH_402: facade geometry can be fully resolved while the legacy
    # construction block still omits light_wall_area_m2. In that state an
    # alternative light-wall insulation scenario previously changed U-value
    # but multiplied it by 0 m2, so the 8760 result did not move at all.
    # Recover the actual opaque facade area from Module 1 surfaces. Only use
    # this fallback when the explicit light-wall area is absent; never replace
    # a resolved construction quantity.
    # If only exterior RC volume is available, derive one-sided envelope area
    # only when an explicit RC wall thickness exists.  This is a physical
    # conversion (volume / thickness), not an assumed facade split.
    if rc_area <= 0.0:
        _ext_rc_v = _f(construction.get("exterior_rc_volume_m3"), 0.0)
        _rc_asm = ((profile.get("assemblies") or {}).get("rc_wall") or {})
        _rc_th_mm = _f(_rc_asm.get("structural_thickness_mm"), _f(_rc_asm.get("wall_thickness_mm"), _f(construction.get("rc_wall_thickness_mm"), 0.0)))
        if _ext_rc_v > 0.0 and _rc_th_mm > 0.0:
            rc_area = _ext_rc_v / (_rc_th_mm / 1000.0)
            rc_area_source = "exterior_rc_volume_divided_by_explicit_wall_thickness"

    facade_opaque_area = 0.0
    for _s in surfaces if isinstance(surfaces, list) else []:
        if not isinstance(_s, dict):
            continue
        _opaque = _f(_s.get("opaque_area_m2"), 0.0)
        if _opaque <= 0.0:
            _gross = _f(_s.get("gross_wall_area_m2"), 0.0)
            _opaque = max(0.0, _gross - _f(_s.get("window_area_m2"), 0.0) - _f(_s.get("door_area_m2"), 0.0))
        facade_opaque_area += max(0.0, _opaque)
    light_area_source = "construction.light_wall_area_m2" if light_area > 0.0 else "unresolved"
    if light_area <= 0.0 and facade_opaque_area > 0.0:
        # If an explicit RC exterior-wall area exists, reserve it first and use
        # the remaining opaque facade for the light wall. Otherwise the whole
        # resolved opaque facade is the light-wall envelope.
        light_area = max(0.0, facade_opaque_area - max(0.0, rc_area))
        light_area_source = "surface_opaque_area_fallback"

    roof_area = _f(geometry.get("roof_area_m2"), footprint)
    slab_area = _f(geometry.get("slab_area_m2"), footprint)
    raw_surface_window_area = sum(_f(s.get("window_area_m2")) for s in surfaces)
    door_area = sum(_f(s.get("door_area_m2")) for s in surfaces)

    # PATCH_387: the aggregate Module 1 window quantity is authoritative for the
    # total opening quantity. AI facade records are supplemental orientation
    # evidence and can internally disagree with their own aggregate geometry
    # (actual Gemini example: 35.940 m2 facade sum vs 32.7632 m2 aggregate).
    # Preserve the aggregate total and use facade values only to distribute that
    # total by orientation. This also protects deterministic Module 1 quantities
    # from being overwritten by an AI surface subtotal.
    aggregate_window_area = _f(geometry.get("window_area_m2"), _f(common.get("window_area_m2"), 0.0))
    if aggregate_window_area > 0.0:
        window_area = aggregate_window_area
    else:
        window_area = raw_surface_window_area

    if window_area <= 0.0:
        window_area = _f(common.get("window_area_m2"), 0.0)
    if door_area <= 0.0:
        door_area = _f(geometry.get("door_area_m2"), _f(common.get("door_area_m2"), 0.0))

    # Build a reconciled orientation set. Canonical north rotation controls true
    # azimuth; reviewer-supplied true azimuth is not allowed to override a project
    # north value. If the facade subtotal disagrees with the authoritative total,
    # scale each facade proportionally so directional solar gains still sum to the
    # protected Module 1 window quantity.
    north_rotation = geometry.get("north_rotation_deg")
    if north_rotation in (None, ""):
        north_rotation = common.get("north_rotation_deg")
    if north_rotation in (None, ""):
        north_rotation = (common.get("building") or {}).get("north_rotation_deg")
    try:
        north_rotation = float(north_rotation) if north_rotation not in (None, "") else None
    except Exception:
        north_rotation = None

    scale = 1.0
    if raw_surface_window_area > 0.0 and window_area > 0.0:
        scale = window_area / raw_surface_window_area
    reconciled_surfaces = []
    for source_surface in surfaces or []:
        if not isinstance(source_surface, dict):
            continue
        win = max(0.0, _f(source_surface.get("window_area_m2"), 0.0))
        if win <= 0.0:
            continue
        surface = dict(source_surface)
        surface["window_area_m2_raw"] = win
        surface["window_area_m2"] = win * scale
        local = source_surface.get("local_azimuth_deg")
        if local not in (None, "") and north_rotation is not None:
            try:
                surface["true_azimuth_deg"] = (float(local) + north_rotation) % 360.0
                surface["azimuth_basis"] = "canonical_north_plus_local_azimuth"
            except Exception:
                pass
        elif source_surface.get("true_azimuth_deg") not in (None, ""):
            surface["azimuth_basis"] = "reviewer_true_azimuth_fallback"
        else:
            continue
        surface["window_area_reconciliation_factor"] = scale
        reconciled_surfaces.append(surface)

    insulation = {
        str(x.get("part")): x
        for x in envelope.get("insulation_details", [])
        if isinstance(x, dict)
    }
    assemblies = profile.get("assemblies") or {}

    def u(part: str, default: float) -> float:
        """Resolve baseline U from the strongest available Module 1 evidence.

        Order: explicit numeric insulation_detail U -> explicit assembly
        material/thickness/lambda -> legacy planning default.  For compatibility,
        an old ``exterior_wall`` detail aliases to ``light_wall``.
        """
        detail = insulation.get(part) or (insulation.get("exterior_wall") if part == "light_wall" else {}) or {}
        explicit = _f(detail.get("u_value_W_m2K"), 0.0)
        if explicit > 0:
            return explicit
        asm = assemblies.get(part) or {}
        if isinstance(asm, dict) and _f(asm.get("thickness_mm"), 0.0) > 0:
            return _assembly_u_value(asm, default)
        if isinstance(detail, dict) and _f(detail.get("thickness_mm"), 0.0) > 0:
            return _assembly_u_value(detail, default)
        return default

    method_id = str(common.get("construction_method_id", profile.get("construction_method_id", "")))
    rc_u = u("rc_wall", 0.20)
    # Correct legacy JSON where the external-insulation flag/profile existed but
    # the RC-wall thickness was overwritten to 0 mm, producing U=5.882 W/m2K.
    if rc_area > 0 and rc_u > 1.0 and method_id in {"azras", "rc_frame"}:
        rc_assembly = (profile.get("assemblies") or {}).get("rc_wall", {})
        if _f(rc_assembly.get("thickness_mm")) <= 0:
            rc_assembly = dict(rc_assembly)
            rc_assembly["material"] = rc_assembly.get("material") or "Phenolic foam"
            rc_assembly["thickness_mm"] = 150.0
        rc_u = _assembly_u_value(rc_assembly, 0.20)

    # PATCH_193: common envelope insulation scenario.  The scenario replaces
    # only the insulation-layer resistance while preserving the baseline
    # assembly's unresolved structural/finish resistance.  If a baseline U is
    # unknown we do not invent one.
    envelope_scenario = settings.get("envelope_thermal_scenario") or {}

    def _scenario_component(part: str, baseline_u: float) -> tuple[float, dict[str, Any]]:
        sc = envelope_scenario.get(part) or {}
        if not sc.get("enabled"):
            return baseline_u, {"enabled": False}
        base = assemblies.get(part) or {}
        base_mat = str(base.get("material") or "")
        base_lam = lambda_for(base_mat, base.get("lambda_W_mK"))
        sc_mat = str(sc.get("material") or base_mat or "Custom")
        sc_lam = lambda_for(sc_mat, sc.get("lambda_W_mK"))
        new_u = scenario_u_from_baseline(
            baseline_u, base.get("thickness_mm"), base_lam,
            sc.get("thickness_mm"), sc_lam,
        )
        if new_u is None:
            new_u = baseline_u
            status = "unresolved_baseline_u"
        else:
            status = "calculated"
        return float(new_u), {
            "enabled": True, "material": sc_mat, "lambda_W_mK": sc_lam,
            "thickness_mm": _f(sc.get("thickness_mm")),
            "insulation_position": normalize_position(sc.get("insulation_position")),
            "mass_coupling_factor": mass_coupling(normalize_position(sc.get("insulation_position"))),
            "baseline_u_W_m2K": baseline_u, "scenario_u_W_m2K": float(new_u),
            "status": status,
        }

    light_u, sc_light = _scenario_component("light_wall", u("light_wall", 0.20))
    roof_u, sc_roof = _scenario_component("roof", u("roof", 0.18))
    rc_u, sc_rc = _scenario_component("rc_wall", rc_u)

    # PATCH_389: attic/ceiling insulation is an additional series layer over
    # only the area where it is actually installed.  It must not be mistaken
    # for exterior-wall insulation or collapsed into the metal roof sandwich.
    ceiling_base = assemblies.get("ceiling_attic") or {}
    ceiling_sc = envelope_scenario.get("ceiling_attic") or {}
    ceiling_area = max(0.0, _f(ceiling_base.get("area_m2"), 0.0))
    ceiling_area_source = "assembly_area_m2" if ceiling_area > 0 else "unresolved"
    # PATCH_401: legacy/current Module 1 takeoff stores GW16K t100 as m3
    # (area × thickness). If area_m2 is absent, recover the actual room-mapped
    # coverage instead of silently dropping the second ceiling insulation layer.
    if ceiling_area <= 0.0:
        qtake = module1.get("quantity_takeoff") or {}
        a11 = qtake.get("a11_finish_schedule_geometry") or {}
        ceiling_area = max(0.0, _f((a11.get("totals") or {}).get("ceiling_gw16k_t100_area_m2"), 0.0))
        if ceiling_area > 0:
            ceiling_area_source = "a11_finish_schedule_geometry"
    if ceiling_area <= 0.0:
        base_th = max(0.0, _f(ceiling_base.get("thickness_mm"), 0.0))
        for rec in _accepted_quantity_rows(module1):
            text = " ".join(str(rec.get(k) or "") for k in ("item","specification","source_text_original","formula","evidence","calculation_basis")).lower()
            if not (("ceiling" in text or "天井" in text) and ("glass wool" in text or "グラスウール" in text or "gw16" in text)):
                continue
            qty = max(0.0, _f(rec.get("accepted_quantity", rec.get("quantity")), 0.0))
            unit = str(rec.get("unit") or "").strip().lower()
            if qty > 0 and unit in {"m2","m²","㎡"}:
                ceiling_area = qty
                ceiling_area_source = "takeoff_area_row"
                break
            if qty > 0 and unit in {"m3","m³","㎥"} and base_th > 0:
                ceiling_area = qty / (base_th / 1000.0)
                ceiling_area_source = "takeoff_volume_divided_by_thickness"
                break
    if ceiling_area > roof_area:
        ceiling_area = roof_area
        ceiling_area_source += "_clamped_to_roof"
    base_ct = _f(ceiling_base.get("thickness_mm"), 0.0)
    base_cl = lambda_for(str(ceiling_base.get("material") or ""), ceiling_base.get("lambda_W_mK"))
    use_ct, use_cl = base_ct, base_cl
    if ceiling_sc.get("enabled"):
        use_ct = _f(ceiling_sc.get("thickness_mm"), 0.0)
        use_cl = lambda_for(str(ceiling_sc.get("material") or ceiling_base.get("material") or "Custom"), ceiling_sc.get("lambda_W_mK"))
    ceiling_u = roof_u
    if ceiling_area > 0 and use_ct > 0 and use_cl and use_cl > 0 and roof_u > 0:
        combined_u = 1.0 / ((1.0 / roof_u) + (use_ct / 1000.0) / use_cl)
        roof_u = (roof_u * max(0.0, roof_area - ceiling_area) + combined_u * ceiling_area) / max(roof_area, 1e-9)
        ceiling_u = combined_u
    sc_ceiling = {
        "enabled": bool(ceiling_sc.get("enabled")),
        "material": str(ceiling_sc.get("material") or ceiling_base.get("material") or ""),
        "lambda_W_mK": use_cl, "thickness_mm": use_ct,
        "area_m2": ceiling_area, "area_source": ceiling_area_source,
        "combined_roof_ceiling_u_W_m2K": ceiling_u,
        "status": "calculated" if ceiling_area > 0 and use_ct > 0 and use_cl else "unresolved_area_or_layer",
    }

    concrete_m3 = quantities.get("コンクリート合計", 0.0)
    if concrete_m3 <= 0:
        concrete_m3 = _f(construction.get("concrete_volume_m3"))

    floor_cfg = settings.get("floor_thermal") or {}
    floor_type = str(floor_cfg.get("ground_floor_type") or "")
    if not floor_type:
        raise ValueError("Ground-floor type is not selected in Module 2.")
    legacy_floor_types = {
        "compacted_earth": "compacted_earth_finish",
        "slab_on_ground": "slab_on_ground_finish",
        "direct_concrete": "slab_on_ground_finish",
        "mat_foundation": "mat_foundation_finish",
        "raised_timber_300": "mat_foundation_airspace_timber",
        "crawlspace_timber_500": "compacted_earth_airspace_timber",
        "airspace_timber": "mat_foundation_airspace_timber",
        "mat_airspace_timber": "mat_foundation_airspace_timber",
    }
    floor_type = legacy_floor_types.get(floor_type, floor_type)

    # Use explicit Module 1 component quantities instead of splitting the total
    # concrete volume mechanically between wall and slab. User-entered values
    # override the automatic quantity takeoff.
    # PATCH_201: accept drawing-specific Module 1 AI takeoff labels instead of
    # requiring a few legacy fixed item names.  Explicit Module 2 overrides
    # still have priority.  The legacy generic RC-wall row retains its existing
    # 50/50 split only when separate exterior/partition rows are absent.
    rc_wall_total = concrete_components.get("generic_rc_wall_m3", 0.0)
    ext_override = floor_cfg.get("exterior_rc_volume_m3")
    part_override = floor_cfg.get("partition_rc_volume_m3")
    exterior_rc_m3 = _f(ext_override, -1.0)
    partition_rc_m3 = _f(part_override, -1.0)
    detected_ext = _f(concrete_components.get("exterior_rc_m3"), 0.0)
    detected_part = _f(concrete_components.get("partition_rc_m3"), 0.0)
    # PATCH_527: legacy auto-populated zero values must not override newly
    # resolved Module 1 RC components. Positive stored values remain valid.
    if exterior_rc_m3 <= 0.0 and detected_ext > 0.0:
        exterior_rc_m3 = detected_ext
    elif exterior_rc_m3 < 0.0:
        exterior_rc_m3 = detected_ext
    if partition_rc_m3 <= 0.0 and detected_part > 0.0:
        partition_rc_m3 = detected_part
    elif partition_rc_m3 < 0.0:
        partition_rc_m3 = detected_part
    if detected_ext <= 0.0 and detected_part <= 0.0 and rc_wall_total > 0.0:
        # PATCH_527: for RC frame, derive exterior RC-wall volume from resolved
        # exterior surface area × explicit structural thickness when available.
        # The remaining wall concrete is internal RC. Legacy 50/50 is last resort.
        _th_mm=_f(construction.get("rc_wall_thickness_mm"),0.0)
        if _th_mm<=0.0:
            _asm=(assemblies.get("rc_wall") or {})
            _th_mm=_f(_asm.get("structural_thickness_mm"),_f(_asm.get("wall_thickness_mm"),0.0))
        _ext_area=_f(construction.get("rc_wall_area_m2"),0.0)
        _physical_ext=min(rc_wall_total,_ext_area*(_th_mm/1000.0)) if _ext_area>0 and _th_mm>0 else 0.0
        if ext_override in (None, "", 0, 0.0) and part_override in (None, "", 0, 0.0):
            if _physical_ext>0.0:
                exterior_rc_m3=_physical_ext
                partition_rc_m3=max(0.0,rc_wall_total-_physical_ext)
            else:
                exterior_rc_m3 = rc_wall_total * 0.50
                partition_rc_m3 = rc_wall_total - exterior_rc_m3
        elif ext_override in (None, "", 0, 0.0):
            exterior_rc_m3 = max(0.0, rc_wall_total - max(partition_rc_m3, 0.0))
        elif part_override in (None, "", 0, 0.0):
            partition_rc_m3 = max(0.0, rc_wall_total - max(exterior_rc_m3, 0.0))

    frame_rc_m3 = _f(concrete_components.get("frame_rc_m3"), 0.0)
    ground_slab_m3 = _f(concrete_components.get("ground_slab_m3"), 0.0)
    upper_slab_m3 = _f(concrete_components.get("upper_slab_m3"), 0.0)
    foundation_rc_m3 = _f(concrete_components.get("foundation_rc_m3"), 0.0)

    ext_fraction = max(0.0, min(1.0, _f(floor_cfg.get("exterior_rc_active_fraction"), 0.35)))
    part_fraction = max(0.0, min(1.0, _f(floor_cfg.get("partition_rc_active_fraction"), 0.60)))
    frame_fraction = max(0.0, min(1.0, _f(floor_cfg.get("frame_rc_active_fraction"), 0.35)))
    direct_fraction = max(0.0, min(1.0, _f(floor_cfg.get("slab_active_fraction_direct"), 0.35)))
    raised_fraction = max(0.0, min(1.0, _f(floor_cfg.get("slab_active_fraction_raised"), 0.10)))

    if floor_type in {
        "compacted_earth_finish",
        "mat_foundation_finish",
        "slab_on_ground_finish",
    }:
        ground_fraction = direct_fraction
    elif floor_type in {
        "compacted_earth_airspace_timber",
        "mat_foundation_airspace_timber",
        "slab_on_ground_airspace_timber",
    }:
        ground_fraction = raised_fraction
    elif floor_type == "other":
        ground_slab_m3 = _f(floor_cfg.get("other_slab_concrete_m3"), ground_slab_m3)
        ground_fraction = max(0.0, min(1.0, _f(floor_cfg.get("other_effective_fraction"), 0.20)))
    else:
        ground_fraction = direct_fraction

    # Convert component-specific active fractions to equivalent fully-active
    # volumes. The existing three-node model then uses active_fraction=1.0,
    # preserving its equations while allowing different exterior/partition/
    # frame/floor effectiveness.
    wall_m3 = (exterior_rc_m3 * ext_fraction
               + partition_rc_m3 * part_fraction
               + frame_rc_m3 * frame_fraction)
    slab_m3 = ground_slab_m3 * ground_fraction + upper_slab_m3 * direct_fraction

    # Insulation position changes how much heavy structure participates in the
    # indoor dynamic node.  External insulation keeps the heavy mass inside;
    # internal insulation decouples most of it.  The factors are explicit
    # reduced-order AZRAS assumptions and are exported in the evidence.
    rc_mass_position_factor = sc_rc.get("mass_coupling_factor", 1.0) if sc_rc.get("enabled") else 1.0
    wall_m3 *= rc_mass_position_factor

    slab_under_insulation = bool(floor_cfg.get("slab_under_insulation", False))
    slab_sc = envelope_scenario.get("slab") or {}
    foundation_sc = envelope_scenario.get("foundation") or {}
    slab_mass_position_factor = 1.0
    if slab_sc.get("enabled"):
        slab_mass_position_factor = mass_coupling(normalize_position(slab_sc.get("insulation_position")))
        slab_m3 *= slab_mass_position_factor

    # PATCH_192: geometry-aware whole-floor ground coupling.  The previous
    # planning model used a fixed U=0.45 W/m2K over the complete footprint.
    # That cannot represent the strong area/perimeter dependence of slab-on-
    # ground heat transfer and does not scale correctly between small and large
    # buildings.  Use the ISO 13370 slab characteristic dimension B'=A/(0.5P)
    # and its uninsulated-slab form as a reduced-model equivalent conductance.
    # This remains a planning approximation (not a full multidimensional ground
    # solver), but it is geometry based and contains no hemisphere/month rule.
    import math
    perimeter_candidates = [
        geometry.get("building_perimeter_m"), geometry.get("perimeter_m"),
        construction.get("building_perimeter_m"), construction.get("exterior_perimeter_m"),
        common.get("building_perimeter_m"), common.get("perimeter_m"),
    ]
    perimeter_m = next((_f(v) for v in perimeter_candidates if _f(v) > 0.0), 0.0)
    if perimeter_m <= 0.0 and slab_area > 0.0:
        # Only a fallback when the drawing did not resolve perimeter.  A square
        # of equal area avoids silently retaining a location-specific fixed U.
        perimeter_m = 4.0 * math.sqrt(slab_area)
    soil_lambda = max(0.5, _f(floor_cfg.get("ground_soil_conductivity_W_mK"), 2.0))
    Bp = slab_area / max(0.5 * perimeter_m, 1e-9) if slab_area > 0.0 else 0.0
    # Equivalent thickness: ground surface resistances plus floor/insulation.
    R_fixed = 0.17
    R_ins = 0.0
    ground_insulation_source = "none"
    if slab_sc.get("enabled"):
        sc_lam = lambda_for(str(slab_sc.get("material") or "Custom"), slab_sc.get("lambda_W_mK"))
        R_ins = insulation_r(slab_sc.get("thickness_mm"), sc_lam)
        slab_under_insulation = R_ins > 0
        ground_insulation_source = "envelope_scenario_slab"
    elif foundation_sc.get("enabled"):
        sc_lam = lambda_for(str(foundation_sc.get("material") or "Custom"), foundation_sc.get("lambda_W_mK"))
        R_ins = insulation_r(foundation_sc.get("thickness_mm"), sc_lam)
        ground_insulation_source = "envelope_scenario_foundation_reduced"
    elif slab_under_insulation:
        thick_m = max(0.0, _f(floor_cfg.get("slab_insulation_thickness_mm"), 100.0)) / 1000.0
        conductivity = max(0.005, _f(floor_cfg.get("slab_insulation_conductivity_W_mK"), 0.028))
        R_ins = thick_m / conductivity
        ground_insulation_source = "floor_thermal"
    else:
        # PATCH_384: a drawing-confirmed Module 1 slab/foundation insulation
        # assembly must affect the baseline 8760 model even before Module 2 has
        # a saved floor_thermal snapshot.  User/saved Module 2 settings above
        # still have priority and are never overwritten.
        slab_base = assemblies.get("slab") or {}
        foundation_base = assemblies.get("foundation") or {}
        base = slab_base if _f(slab_base.get("thickness_mm"), 0.0) > 0 else foundation_base
        if isinstance(base, dict) and _f(base.get("thickness_mm"), 0.0) > 0:
            base_lam = lambda_for(str(base.get("material") or "Custom"), base.get("lambda_W_mK"))
            R_ins = insulation_r(base.get("thickness_mm"), base_lam)
            if R_ins > 0:
                slab_under_insulation = True
                ground_insulation_source = "module1_profile_assembly"
    dt_equiv = max(0.05, soil_lambda * (R_fixed + R_ins))
    if Bp > 0.0:
        slab_u_geom = (2.0 * soil_lambda / (math.pi * Bp + dt_equiv)) * math.log(1.0 + math.pi * Bp / dt_equiv)
    else:
        slab_u_geom = 0.45

    if floor_type == "other":
        slab_u = max(0.03, _f(floor_cfg.get("other_ground_u_W_m2K"), slab_u_geom))
        ground_u_method = "user_other_floor"
    elif floor_type.endswith("_airspace_timber"):
        # Raised timber floor is not a direct slab-on-ground boundary. Keep the
        # reduced coupling conservative until the underfloor-air model is split.
        slab_u = min(0.45, slab_u_geom)
        ground_u_method = "geometry_reduced_raised_floor"
    else:
        slab_u = max(0.03, slab_u_geom)
        ground_u_method = "ISO13370_characteristic_dimension_reduced"

    # PATCH_171: Module 1 may provide an explicit effective heat capacity
    # (including the clearly-labelled AI planning fallback).  The legacy model
    # otherwise derives mass only from RC volumes; for S-frame AI takeoff this
    # can collapse to ~0.20 MJ/K and make the explicit solver diverge.  Convert
    # the supplied capacity to an equivalent active slab volume so the solver
    # uses the same Module 1 thermal-mass interface without inventing RC takeoff.
    # PATCH_197: retain component-level active thermal mass before any legacy
    # Module 1 capacity fallback is added.  This lets the comparison UI show
    # the RC-wall and slab contributions separately instead of only a single
    # solver-wide capacity value.
    concrete_volumetric_capacity_MJ_m3K = 2300.0 * 880.0 / 1_000_000.0
    rc_wall_active_capacity_MJ_K = max(0.0, wall_m3) * concrete_volumetric_capacity_MJ_m3K
    slab_active_capacity_MJ_K = max(0.0, slab_m3) * concrete_volumetric_capacity_MJ_m3K

    explicit_capacity_MJ_K = max(0.0, _f(settings.get("module1_effective_heat_capacity_MJ_K"), 0.0))
    derived_capacity_MJ_K = (wall_m3 + slab_m3) * 2300.0 * 880.0 / 1_000_000.0
    component_bridge_available = any(v > 0.0 for v in (
        exterior_rc_m3, partition_rc_m3, frame_rc_m3,
        ground_slab_m3, upper_slab_m3, foundation_rc_m3
    ))
    fallback_added_MJ_K = 0.0
    # PATCH_527: component quantities with active fractions are authoritative.
    # Do not top them up to a legacy Module 1 material-capacity total.
    if (not component_bridge_available) and explicit_capacity_MJ_K > derived_capacity_MJ_K:
        fallback_added_MJ_K = explicit_capacity_MJ_K - derived_capacity_MJ_K
        extra_equiv_m3 = fallback_added_MJ_K * 1_000_000.0 / (2300.0 * 880.0)
        slab_m3 += max(0.0, extra_equiv_m3)

    cfg = ModelConfig(
        conditioned_floor_area_m2=max(floor_area, 1.0),
        footprint_area_m2=max(footprint, 1.0),
        conditioned_volume_m3=max(volume, 1.0),
        rc_exterior_area_m2=max(rc_area, 0.0),
        light_exterior_area_m2=max(light_area, 0.0),
        roof_area_m2=max(roof_area, 1.0),
        slab_area_m2=max(slab_area, 1.0),
        window_area_m2=max(window_area, 0.0),
        door_area_m2=max(door_area, 0.0),

        u_rc_wall_W_m2K=rc_u,
        u_light_wall_W_m2K=light_u,
        u_roof_W_m2K=roof_u,
        u_window_W_m2K=_f(envelope.get("window_u_W_m2K"), 1.4),
        u_door_W_m2K=1.8,
        u_slab_to_ground_W_m2K=slab_u,
        thermal_bridge_W_K=max(0.05 * max(floor_area, 1.0), 5.0),

        concrete_density_kg_m3=2300.0,
        concrete_cp_J_kgK=880.0,
        total_concrete_volume_m3=max(concrete_m3, 0.1),
        rc_wall_mass_volume_m3=max(wall_m3, 0.05),
        slab_mass_volume_m3=max(slab_m3, 0.05),
        active_fraction_wall=1.0,
        active_fraction_slab=1.0,
        air_capacitance_multiplier=5.0,

        h_inside_wall_W_m2K=3.0,
        h_inside_slab_W_m2K=2.5,

        ach_1_h=_f(settings.get("ach"), 0.5),
        heat_recovery_efficiency=_f(settings.get("heat_recovery"), 0.70),
        window_shgc=_f(settings.get("window_shgc"), 0.45),
        solar_shading_factor=_f(settings.get("solar_shading"), 0.75),
        solar_to_air_fraction=0.30,
        solar_to_wall_fraction=0.30,
        solar_to_slab_fraction=0.40,
        internal_gain_W_m2_day=_f(settings.get("internal_gain_day"), 5.0),
        internal_gain_W_m2_night=_f(settings.get("internal_gain_night"), 2.0),

        heating_setpoint_C=_f(settings.get("heating_setpoint"), 20.0),
        cooling_setpoint_C=_f(settings.get("cooling_setpoint"), 27.0),
        heating_cop=max(_f(settings.get("heating_cop"), 3.5), 0.1),
        cooling_cop=max(_f(settings.get("cooling_cop"), 3.2), 0.1),
        primary_energy_factor_MJ_per_kWh=_f(settings.get("primary_energy_factor"), 9.76),
        electricity_co2_kg_per_kWh=_f(settings.get("electricity_co2"), 0.43),

        ground_annual_mean_C=_f(settings.get("ground_mean"), 15.0),
        ground_amplitude_C=_f(settings.get("ground_amplitude"), 5.0),
        ground_phase_day=_f(settings.get("ground_phase_day"), 45.0),

        # PATCH_182: carry Module 1 AI-resolved facade/window surfaces into the
        # thermal solver for true-azimuth solar gains.  Unresolved projects retain
        # the legacy total-window fallback without inventing orientations.
        orientation_surfaces=tuple(reconciled_surfaces),

        # PATCH_189: reduced-model opaque roof solar gain.  0.55 is the
        # existing AZRAS planning default used by roof_plan_defaults_v6_2.json;
        # callers may override it in settings when a project-specific value is
        # available.
        roof_solar_absorptance=max(0.0, min(1.0, _f(settings.get("roof_solar_absorptance"), 0.55))),
        outside_surface_h_W_m2K=max(1.0, _f(settings.get("outside_surface_h_W_m2K"), 20.0)),

        # PATCH_527: preserve Module 2 passive-strategy inputs through
        # Module 9/10 and Compare's regional 8760 calculation path.
        thermal_mass_enabled=bool(settings.get("thermal_mass_enabled", True)),
        external_insulation_enabled=bool(settings.get("external_insulation_enabled", True)),
        external_insulation_reference_u_multiplier=max(
            1.0, _f(settings.get("external_insulation_reference_u_multiplier"), 3.0)
        ),
        night_heat_release_enabled=bool(settings.get("night_heat_release_enabled", False)),
        night_release_start_hour=int(_f(settings.get("night_release_start_hour"), 22)),
        night_release_end_hour=int(_f(settings.get("night_release_end_hour"), 6)),
        night_release_conductance_W_K=max(
            0.0, _f(settings.get("night_release_conductance_W_K"), 0.0)
        ),
        natural_night_ventilation_enabled=bool(
            settings.get("natural_night_ventilation_enabled", False)
        ),
        night_ventilation_ach=max(0.0, _f(settings.get("night_ventilation_ach"), 3.0)),
        night_ventilation_delta_C=max(
            0.0, _f(settings.get("night_ventilation_delta_C"), 2.0)
        ),

        timestep_minutes=5
    )
    breakdown = {
        "schema_version": "1.1",
        "method_id": method_id,
        "orientation_window_reconciliation": {
            "raw_surface_window_area_m2": raw_surface_window_area,
            "authoritative_window_area_m2": window_area,
            "scale_factor": scale,
            "surface_count": len(reconciled_surfaces),
            "north_rotation_deg": north_rotation,
            "rule": "canonical Module 1 aggregate window area + canonical north; drawing-derived Module 1 facade surfaces are primary, AI facade records are fallback only",
            "directional_solar_enabled": bool(reconciled_surfaces),
            "directional_window_area_m2": sum(_f(x.get("window_area_m2")) for x in reconciled_surfaces),
        },
        "ground_floor_type": floor_type,
        "air_gap_mm": _f(floor_cfg.get("air_gap_mm"), 0.0),
        "exterior_rc_volume_m3": exterior_rc_m3,
        "partition_rc_volume_m3": partition_rc_m3,
        "frame_rc_volume_m3": frame_rc_m3,
        "ground_slab_volume_m3": ground_slab_m3,
        "upper_slab_volume_m3": upper_slab_m3,
        "foundation_rc_volume_m3": foundation_rc_m3,
        "quantity_bridge_schema": "PATCH_208_planning_canonical_quantity_bridge_v1",
        "quantity_bridge_matched_rows": concrete_components.get("matched_rows", []),
        "quantity_bridge_module1_resolved": bool(module1),
        "quantity_bridge_module1_version": str(module1.get("version") or ""),
        "quantity_bridge_upstream_structural_quantity_status": (
            "available" if any(
                str(r.get("unit") or "").strip().lower().replace(" ", "") in {"m3", "m³", "㎥"}
                and max(0.0, _f(r.get("accepted_quantity", r.get("quantity")))) > 0.0
                for r in _accepted_quantity_rows(module1)
            ) else "missing_from_planning_canonical_takeoff"
        ),
        "quantity_bridge_takeoff_row_count": len(_accepted_quantity_rows(module1)),
        "quantity_bridge_concrete_m3_row_count": sum(
            1 for r in _accepted_quantity_rows(module1)
            if str(r.get("unit") or "").strip().lower().replace(" ", "") in {"m3", "m³", "㎥"}
        ),
        "quantity_bridge_has_concrete_m3": any(
            str(r.get("unit") or "").strip().lower().replace(" ", "") in {"m3", "m³", "㎥"}
            and max(0.0, _f(r.get("accepted_quantity", r.get("quantity")))) > 0.0
            for r in _accepted_quantity_rows(module1)
        ),
        "module1_explicit_heat_capacity_status": str(settings.get("module1_effective_heat_capacity_status") or ""),
        "planning_quantity_source": "module_outputs.module1.quantity_takeoff.rows",
        "exterior_rc_active_fraction": ext_fraction,
        "partition_rc_active_fraction": part_fraction,
        "frame_rc_active_fraction": frame_fraction,
        "ground_slab_active_fraction": ground_fraction,
        "upper_slab_active_fraction": direct_fraction,
        "equivalent_active_wall_volume_m3": wall_m3,
        "equivalent_active_slab_volume_m3": slab_m3,
        "rc_wall_active_heat_capacity_MJ_K": rc_wall_active_capacity_MJ_K,
        "slab_active_heat_capacity_MJ_K": slab_active_capacity_MJ_K,
        "structural_active_heat_capacity_MJ_K": rc_wall_active_capacity_MJ_K + slab_active_capacity_MJ_K,
        # PATCH_198: keep the Module 1 explicit/fallback capacity separate from
        # the component-derived structural mass.  This prevents the legacy
        # planning value from being mistaken for measured RC/slab capacity.
        "module1_explicit_heat_capacity_MJ_K": explicit_capacity_MJ_K,
        "component_derived_heat_capacity_before_fallback_MJ_K": derived_capacity_MJ_K,
        "module1_fallback_added_heat_capacity_MJ_K": fallback_added_MJ_K,
        "component_bridge_available": component_bridge_available,
        "thermal_mass_source_policy": (
            "component_quantities_with_active_fractions"
            if component_bridge_available else "module1_explicit_capacity_fallback"
        ),
        "concrete_volumetric_heat_capacity_MJ_m3K": concrete_volumetric_capacity_MJ_m3K,
        "slab_under_insulation": slab_under_insulation,
        "foundation_bottom_insulation": bool(
            floor_cfg.get("foundation_bottom_insulation", False)
        ),
        "slab_insulation_thickness_mm": _f(
            floor_cfg.get("slab_insulation_thickness_mm"), 100.0
        ),
        "slab_insulation_conductivity_W_mK": _f(
            floor_cfg.get("slab_insulation_conductivity_W_mK"), 0.028
        ),
        "u_slab_to_ground_W_m2K": slab_u,
        "ground_u_method": ground_u_method,
        "ground_floor_perimeter_m": perimeter_m,
        "ground_characteristic_dimension_Bp_m": Bp,
        "ground_soil_conductivity_W_mK": soil_lambda,
        "ground_equivalent_thickness_m": dt_equiv,
        "roof_solar_absorptance": max(0.0, min(1.0, _f(settings.get("roof_solar_absorptance"), 0.55))),
        "outside_surface_h_W_m2K": max(1.0, _f(settings.get("outside_surface_h_W_m2K"), 20.0)),
        "ground_to_slab_direct_zone_load": False,
        "light_wall_area_m2_used": light_area,
        "light_wall_area_source": light_area_source,
        "light_wall_u_W_m2K_used": light_u,
        "rc_wall_area_m2_used": rc_area,
        "rc_wall_area_source": rc_area_source,
        "rc_wall_u_W_m2K_used": rc_u,
        # PATCH_403: expose all comparable envelope/ground paths so a checked
        # scenario can be verified on-screen instead of inferred from totals.
        "slab_area_m2_used": slab_area,
        "slab_ground_u_W_m2K_used": slab_u,
        "attic_ceiling_area_m2_used": ceiling_area,
        "attic_ceiling_area_source": ceiling_area_source,
        "effective_roof_u_W_m2K_used": roof_u,
        "ground_insulation_source": ground_insulation_source,
        "ground_added_insulation_R_m2K_W": R_ins,
        "envelope_thermal_scenario": {
            "roof": sc_roof, "ceiling_attic": sc_ceiling, "light_wall": sc_light, "rc_wall": sc_rc,
            "slab": dict(slab_sc), "foundation": dict(foundation_sc),
            "rc_mass_position_factor": rc_mass_position_factor,
            "slab_mass_position_factor": slab_mass_position_factor,
            "ground_insulation_source": ground_insulation_source,
            "ground_added_insulation_R_m2K_W": R_ins,
        },
        "other_floor_name": str(floor_cfg.get("other_floor_name") or ""),
        "other_floor_detail": str(floor_cfg.get("other_floor_detail") or ""),
    }
    return cfg, breakdown

def build_config(module1: dict[str, Any], common: dict[str, Any],
                 settings: dict[str, Any]) -> ModelConfig:
    """Backward-compatible configuration builder.

    Regional analysis and existing callers expect a ModelConfig object.
    Floor/foundation details are still calculated by the internal helper and
    are exposed in Module 2 summaries by run_environment.
    """
    cfg, _ = _build_config_with_breakdown(module1, common, settings)
    return cfg

def run_environment(project: dict[str, Any], weather_path: str | Path,
                    settings: dict[str, Any]) -> tuple[Any, dict[str, Any]]:
    module1 = _resolve_module1(project)
    if not module1:
        raise ValueError("Module 1 output is required.")
    cfg, floor_breakdown = _build_config_with_breakdown(
        module1, project.get("common", {}), settings
    )
    weather = read_weather(weather_path)
    hourly, thermal_summary = simulate(weather, cfg)

    equipment_kwh = _other_equipment_kwh(module1)

    # PATCH_174: preserve the heating/cooling electricity values already
    # calculated by the dynamic thermal model.  Module 2's result table
    # displays these keys separately; environment_engine previously copied
    # only the combined HVAC value, so the UI fell back to 0.00 even though
    # the load and total HVAC electricity were valid.
    heating_elec_kwh = _f(thermal_summary.get("heating_electricity_kWh_per_year"))
    cooling_elec_kwh = _f(thermal_summary.get("cooling_electricity_kWh_per_year"))
    hvac_kwh = _f(thermal_summary.get("hvac_electricity_kWh_per_year"))

    # Defensive reconciliation: the simulator should already provide the
    # combined value, but derive it from the two components if an older or
    # alternate engine omits it.
    if hvac_kwh <= 0.0 and (heating_elec_kwh > 0.0 or cooling_elec_kwh > 0.0):
        hvac_kwh = heating_elec_kwh + cooling_elec_kwh

    total_kwh = hvac_kwh + equipment_kwh
    co2_factor = cfg.electricity_co2_kg_per_kWh
    primary_factor = cfg.primary_energy_factor_MJ_per_kWh
    floor_area = max(cfg.conditioned_floor_area_m2, 1.0)

    # PATCH_175: retain a 12-month thermal-load breakdown so Module 2 can
    # verify whether summer cooling and winter heating occur in plausible
    # months.  The dynamic model already returns one row per weather hour.
    monthly_thermal = []
    try:
        h = hourly.copy()
        h["datetime"] = __import__("pandas").to_datetime(h["datetime"], errors="coerce")
        h = h[h["datetime"].notna()].copy()
        h["month"] = h["datetime"].dt.month
        for month in range(1, 13):
            g = h[h["month"] == month]
            heat = float(__import__("pandas").to_numeric(g.get("heating_load_kWh", 0.0), errors="coerce").fillna(0.0).sum()) if len(g) else 0.0
            cool = float(__import__("pandas").to_numeric(g.get("cooling_load_kWh", 0.0), errors="coerce").fillna(0.0).sum()) if len(g) else 0.0
            heat_peak = float(__import__("pandas").to_numeric(g.get("heating_load_kWh", 0.0), errors="coerce").fillna(0.0).max()) if len(g) else 0.0
            cool_peak = float(__import__("pandas").to_numeric(g.get("cooling_load_kWh", 0.0), errors="coerce").fillna(0.0).max()) if len(g) else 0.0
            monthly_thermal.append({
                "month": month,
                "heating_load_kWh": heat,
                "cooling_load_kWh": cool,
                "heating_electricity_kWh": heat / max(cfg.heating_cop, 0.1),
                "cooling_electricity_kWh": cool / max(cfg.cooling_cop, 0.1),
                "peak_heating_kW": heat_peak,
                "peak_cooling_kW": cool_peak,
            })
    except Exception:
        monthly_thermal = []

    summary = {
        "version": "9.4.1",
        "module": "module2",
        "model": "Three-node reduced dynamic thermal model",
        "weather_file": str(weather_path),
        "settings": settings,
        "thermal_model_config": asdict(cfg),
        "floor_thermal_schema_version": "1.1",
        "floor_thermal_settings": dict(settings.get("floor_thermal") or {}),
        "floor_thermal_breakdown": floor_breakdown,
        "heating_load_kWh_per_year": _f(thermal_summary.get("heating_load_kWh_per_year")),
        "cooling_load_kWh_per_year": _f(thermal_summary.get("cooling_load_kWh_per_year")),
        "heating_electricity_kWh_per_year": heating_elec_kwh,
        "cooling_electricity_kWh_per_year": cooling_elec_kwh,
        "hvac_electricity_kWh_per_year": hvac_kwh,
        "other_equipment_electricity_kWh_per_year": equipment_kwh,
        "total_building_electricity_kWh_per_year": total_kwh,
        "primary_energy_MJ_per_year": total_kwh * primary_factor,
        "operational_CO2_kg_per_year": total_kwh * co2_factor,
        "peak_heating_kW": _f(thermal_summary.get("peak_heating_kW")),
        "peak_cooling_kW": _f(thermal_summary.get("peak_cooling_kW")),
        "peak_heating_datetime": thermal_summary.get("peak_heating_datetime"),
        "peak_cooling_datetime": thermal_summary.get("peak_cooling_datetime"),
        "peak_heating_duration_hours_90pct": _f(thermal_summary.get("peak_heating_duration_hours_90pct")),
        "peak_cooling_duration_hours_90pct": _f(thermal_summary.get("peak_cooling_duration_hours_90pct")),
        "monthly_thermal": monthly_thermal,
        "electricity_intensity_kWh_m2_year": total_kwh / floor_area,
        "operational_CO2_intensity_kg_m2_year": total_kwh * co2_factor / floor_area,
        "effective_dynamic_heat_capacity_MJ_per_K":
            _f(thermal_summary.get("effective_dynamic_heat_capacity_MJ_per_K")),
        # PATCH_198: explicit audit fields for the capacity actually used by
        # the 8760-hour solver versus the Module 1 planning/fallback value.
        "solver_used_effective_heat_capacity_MJ_K":
            _f(thermal_summary.get("effective_dynamic_heat_capacity_MJ_per_K")),
        "module1_input_effective_heat_capacity_MJ_K":
            _f(floor_breakdown.get("module1_explicit_heat_capacity_MJ_K")),
        "module1_fallback_added_heat_capacity_MJ_K":
            _f(floor_breakdown.get("module1_fallback_added_heat_capacity_MJ_K")),
        # Stable-interface alias used by project_store and Integrated Comparison.
        "effective_thermal_capacity_MJ_K":
            _f(thermal_summary.get("effective_dynamic_heat_capacity_MJ_per_K")),
        "average_u_value_W_m2K": (
            cfg.u_rc_wall_W_m2K * cfg.rc_exterior_area_m2
            + cfg.u_light_wall_W_m2K * cfg.light_exterior_area_m2
            + cfg.u_roof_W_m2K * cfg.roof_area_m2
            + cfg.u_window_W_m2K * cfg.window_area_m2
            + cfg.u_door_W_m2K * cfg.door_area_m2
            + cfg.u_slab_to_ground_W_m2K * cfg.slab_area_m2
        ) / max(
            cfg.rc_exterior_area_m2 + cfg.light_exterior_area_m2
            + cfg.roof_area_m2 + cfg.window_area_m2
            + cfg.door_area_m2 + cfg.slab_area_m2, 1.0
        ),
        "status": "provisional_planning_comparison",
        "disclaimer": (
            "This reduced model is for planning comparison and does not replace "
            "EnergyPlus, BEST, THERB or formal engineering verification."
        )
    }

    common = project.get("common", {})
    renewable = common.get("renewable_energy") or {}
    pv_settings = dict(renewable)
    pv_settings.update(settings.get("pv") or {})
    pv_settings["electricity_co2_kg_per_kWh"] = co2_factor

    building_common = common.get("building") or {}
    roof_area = _f(
        common.get("roof_area_m2"),
        _f(building_common.get("roof_area_m2"), cfg.roof_area_m2),
    )

    hourly, pv_summary = calculate_pv_energy(
        hourly=hourly,
        annual_building_electricity_kwh=total_kwh,
        annual_other_equipment_kwh=equipment_kwh,
        heating_cop=cfg.heating_cop,
        cooling_cop=cfg.cooling_cop,
        roof_area_m2=roof_area,
        settings=pv_settings,
    )

    summary["pv"] = pv_summary
    summary.update({
        "pv_area_m2": pv_summary["pv_area_m2"],
        "annual_pv_generation_kWh": pv_summary["annual_generation_kWh"],
        "annual_pv_self_consumption_kWh": pv_summary["annual_self_consumption_kWh"],
        "annual_pv_export_kWh": pv_summary["annual_export_kWh"],
        "annual_grid_import_kWh": pv_summary["annual_grid_import_kWh"],
        "electricity_self_sufficiency_percent":
            pv_summary["electricity_self_sufficiency_percent"],
        "pv_currency": pv_summary.get("currency","UNSET"),
        "annual_electricity_cost_saving_local_currency":
            pv_summary.get("annual_cost_saving_local_currency",0.0),
        "annual_export_revenue_local_currency":
            pv_summary.get("annual_export_revenue_local_currency",0.0),
        "annual_pv_economic_benefit_local_currency":
            pv_summary.get("annual_total_economic_benefit_local_currency",0.0),
        "annual_electricity_cost_saving_JPY":
            pv_summary.get("annual_cost_saving_JPY"),
        "annual_export_revenue_JPY":
            pv_summary.get("annual_export_revenue_JPY"),
        "annual_pv_economic_benefit_JPY":
            pv_summary.get("annual_total_economic_benefit_JPY"),
        "annual_pv_co2_reduction_kg":
            pv_summary["annual_co2_reduction_kg"],
        "net_operational_CO2_kg_per_year":
            pv_summary["net_operational_CO2_kg_per_year"],
    })
    return hourly, summary
