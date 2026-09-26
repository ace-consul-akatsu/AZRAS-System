
from __future__ import annotations
from copy import deepcopy
from typing import Any
from services.future_climate_8760 import calculate_future_climate_8760
from services.grid_decarbonization_scenarios import resolve_grid_decarbonization_scenario, scenario_metadata
import hashlib
import json
from services.lca_module_crosswalk import build_lca_module_crosswalk

TAKEOFF_MAP = {
    "コンクリート合計": "concrete",
    "コンクリート": "concrete",
    "鉄筋": "reinforcing_steel",
    "構造用鉄骨": "structural_steel",
    "2×6・一般構造木材": "dimension_lumber",
    "2×6・一般木材": "dimension_lumber",
    "2×6構造木材量（部位別暫定合計）": "dimension_lumber",
    "AZRAS timber framing total (method-specific provisional total)": "dimension_lumber",
    "RC internal partition LGS steel total (provisional general specification)": "structural_steel",
    "CLT・Mass Timber": "clt",
    "フェノールフォーム": "phenolic_foam",
    "XPS": "xps",
    "外壁窓ガラス": "glass",
    "ガラス": "glass",
    "石膏ボード13mm": "gypsum_board",
    "石膏ボード": "gypsum_board"
}

EQUIPMENT_COMPONENTS = {
    "equipment_lighting", "equipment_outlets", "equipment_hvac",
    "equipment_ventilation", "equipment_refrigerator"
}

def _f(v: Any, default: float=0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default

def _stable_hash(value: Any) -> str:
    raw=json.dumps(value,ensure_ascii=False,sort_keys=True,default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]

def extract_material_quantities_from_module5(module5: dict[str, Any]) -> dict[str, float]:
    """Use Module 5's method-screened material quantities for lifecycle CO2.

    Formwork is intentionally excluded because it is a construction temporary
    work item rather than material remaining in the completed building.
    """
    quantities: dict[str, float] = {}
    rows=(module5 or {}).get("trade_material_breakdown") or (module5 or {}).get("cost_lines") or []
    for row in rows:
        key=str(row.get("cost_item_key") or "")
        if not key or key=="formwork":
            continue
        qty=_f(row.get("quantity"))
        if qty>0:
            quantities[key]=quantities.get(key,0.0)+qty
    return quantities

def extract_material_quantities(module1: dict[str, Any]) -> dict[str, float]:
    quantities: dict[str, float] = {}
    for row in module1.get("quantity_takeoff", {}).get("rows", []):
        item = str(row.get("item", ""))
        key = TAKEOFF_MAP.get(item)
        if not key:
            continue
        qty = _f(row.get("accepted_quantity", row.get("quantity")))
        quantities[key] = quantities.get(key, 0.0) + qty
    return quantities

def material_inventory(quantities: dict[str, float], factors: dict[str, Any]) -> list[dict[str, Any]]:
    result=[]
    ratio=_f(
        factors.get("biogenic_carbon_method", {}).get(
            "co2_to_carbon_molecular_ratio"
        ),
        44.0 / 12.0,
    )
    for key, qty in quantities.items():
        factor=factors["materials"].get(key)
        if not factor or qty <= 0:
            continue
        mass_kg=qty * _f(factor["density_kg_per_unit"])
        dry_density=_f(
            factor.get("dry_density_kg_per_m3"),
            factor.get("density_kg_per_unit"),
        )
        wood_fraction=max(0.0, min(1.0, _f(factor.get("wood_fraction"))))
        carbon_fraction=max(
            0.0,
            min(1.0, _f(factor.get("carbon_fraction_of_dry_wood"))),
        )
        is_wood=(
            factor.get("unit") == "m3"
            and dry_density > 0
            and wood_fraction > 0
            and carbon_fraction > 0
        )
        dry_wood_mass_kg=qty * dry_density * wood_fraction if is_wood else 0.0
        carbon_mass_kgC=dry_wood_mass_kg * carbon_fraction
        calculated_storage_kgCO2=carbon_mass_kgC * ratio
        biogenic_storage=(
            calculated_storage_kgCO2
            if factor.get("biogenic_storage_calculation") == "formula"
            else qty * _f(factor.get("biogenic_storage_kgCO2_per_unit"))
        )
        result.append({
            "material_key": key,
            "material_name_ja": factor.get("ja", key),
            "material_name_en": factor.get("en", key),
            "product_type_ja": factor.get("product_type_ja", factor.get("ja", key)),
            "product_type_en": factor.get("product_type_en", factor.get("en", key)),
            "quantity": qty,
            "unit": factor["unit"],
            "mass_kg": mass_kg,
            "embodied_co2_kg": qty * _f(factor["embodied_co2_kg_per_unit"]),
            "embodied_energy_MJ": qty * _f(factor["embodied_energy_MJ_per_unit"]),
            "dry_density_kg_per_m3": dry_density if is_wood else 0.0,
            "wood_fraction": wood_fraction if is_wood else 0.0,
            "dry_wood_mass_kg": dry_wood_mass_kg,
            "carbon_fraction_of_dry_wood": carbon_fraction if is_wood else 0.0,
            "biogenic_carbon_mass_kgC": carbon_mass_kgC,
            "biogenic_storage_kgCO2": biogenic_storage,
            "storage_duration_years": int(_f(factor.get("storage_duration_years"))),
            "is_wood_product": bool(is_wood),
        })
    return result

def _inventory_totals(inventory: list[dict[str, Any]]) -> dict[str, float]:
    keys=[
        "mass_kg","embodied_co2_kg","embodied_energy_MJ",
        "dry_wood_mass_kg","biogenic_carbon_mass_kgC",
        "biogenic_storage_kgCO2",
    ]
    totals={k:sum(_f(x.get(k)) for x in inventory) for k in keys}
    totals["wood_volume_m3"]=sum(
        _f(x.get("quantity"))
        for x in inventory
        if x.get("is_wood_product") and x.get("unit") == "m3"
    )
    return totals

def _inventory_mass_map(initial_inventory: list[dict[str, Any]]) -> dict[str,float]:
    return {str(x.get("material_key")):max(_f(x.get("mass_kg")),0.0) for x in initial_inventory}


def _component_material_masses(component_key: str, project: dict[str,Any],
                               initial_inventory: list[dict[str,Any]]) -> dict[str,float]:
    """Allocate the actual Module 5 material inventory to lifecycle components.

    The allocation is intentionally mass-based and auditable. It replaces the old
    fixed percentages of total building mass (roof=4%, exterior=8%, etc.).
    """
    masses=_inventory_mass_map(initial_inventory)
    comp=str(component_key or "")
    if not masses:
        return {}

    if comp=="whole_building":
        return dict(masses)

    if comp.startswith("structure_"):
        if "timber" in comp or "clt" in comp:
            keys={"dimension_lumber","clt","structural_plywood"}
        elif "steel" in comp:
            keys={"structural_steel"}
        else:
            keys={"concrete","reinforcing_steel","structural_steel"}
        return {k:v for k,v in masses.items() if k in keys and v>0}

    if comp=="windows":
        # Module 3 component name is "窓・ガラス・建具"; include exterior doors
        # as well as glazing so the component definition and LCA scope match.
        return {k:v for k,v in masses.items() if k in {"glass","doors"} and v>0}

    if comp=="insulation":
        # Above-grade insulation is replaceable. Foundation XPS remains with the
        # foundation/core and is not cyclically replaced in Evaluation.
        return {k:v for k,v in masses.items() if k in {"phenolic_foam"} and v>0}

    if comp=="infill_layout":
        # Interior partitions/substrates + finish.
        return {k:v for k,v in masses.items() if k in {"gypsum_board","interior_finish"} and v>0}

    # Split timber/plywood between wall and roof according to actual Module 1 areas.
    m1=(project.get("module_outputs",{}) or {}).get("module1") or {}
    profile=m1.get("profile",{}) or {}
    geom=profile.get("geometry",{}) or {}
    construction=profile.get("construction",{}) or {}
    light_area=max(_f(construction.get("light_wall_area_m2")),0.0)
    roof_area=max(_f(geom.get("roof_area_m2")),0.0)
    denom=light_area+roof_area
    light_share=(light_area/denom) if denom>0 else 0.0
    roof_share=(roof_area/denom) if denom>0 else 0.0

    if comp=="infill_exterior":
        result={}
        for k in ("external_finish_timber","external_finish_rc"):
            if masses.get(k,0)>0: result[k]=masses[k]
        for k in ("dimension_lumber","structural_plywood"):
            if masses.get(k,0)>0 and light_share>0: result[k]=masses[k]*light_share
        return result

    if comp=="roof":
        result={}
        if masses.get("roofing",0)>0:
            result["roofing"]=masses["roofing"]
        common=(project.get("common",{}) or {})
        method=str(common.get("construction_method_id") or "").lower()
        # Timber roof framing/sheathing belongs to 2x6 and AZRAS timber outfill,
        # not to a conventional RC roof slab.
        if method!="rc_frame":
            for k in ("dimension_lumber","structural_plywood"):
                if masses.get(k,0)>0 and roof_share>0:
                    result[k]=masses[k]*roof_share
        return result

    if comp=="all_infill":
        # Everything replaceable without demolishing the retained structural core.
        # Foundation XPS is excluded because it cannot be renewed without major
        # foundation intervention.
        structural={"concrete","reinforcing_steel","structural_steel","xps"}
        return {k:v for k,v in masses.items() if k not in structural and v>0}

    if comp in EQUIPMENT_COMPONENTS:
        return {}

    # Unknown non-structural component: do not silently assign whole-building mass.
    return {}


def _component_mix(component_key: str, project: dict[str,Any],
                   initial_inventory: list[dict[str, Any]]) -> list[tuple[str,float]]:
    masses=_component_material_masses(component_key,project,initial_inventory)
    total=sum(masses.values())
    if total<=0:
        return []
    return [(k,v/total) for k,v in masses.items() if v>0]


def _event_reference_mass(event: dict[str, Any], project: dict[str,Any],
                          initial_inventory: list[dict[str,Any]], floor_area: float) -> float:
    comp=str(event.get("component_key", ""))
    if comp in EQUIPMENT_COMPONENTS:
        # Equipment BOM is not yet available in Evaluation.
        return max(floor_area*0.25,1.0)
    masses=_component_material_masses(comp,project,initial_inventory)
    return sum(masses.values())


def evaluate_long_term_environment(project: dict[str, Any], factors: dict[str, Any],
                                   period_years: int=200,
                                   operational_change_pct: float=0.0,
                                   grid_change_pct: float=0.0,
                                   include_recycling_credit: bool=True,
                                   include_biogenic: bool=True,
                                   future_climate_enabled: bool=False,
                                   future_warming_C_at_year_100: float=0.0,
                                   future_warming_C_at_year_200: float=0.0,
                                   future_climate_milestone_interval_years: int=20,
                                   grid_decarbonization_scenario: str="custom") -> dict[str, Any]:
    # Evaluation master environmental timeline is fixed at 200 years.
    period_years=200
    outputs=project.get("module_outputs", {})
    module1=outputs.get("module1")
    module2=outputs.get("module2")
    module3=outputs.get("module3")
    module5=outputs.get("module5") or {}
    if not module1 or not module2 or not module3:
        raise ValueError("Module 1, Module 2 and Module 3 outputs are required.")

    common=project.get("common", {})
    floor_area=max(_f(common.get("scale_gfa_m2")), 1.0)

    # PATCH 197: Module 4 is evaluated BEFORE Module 5 in the official workflow.
    # Therefore a previously saved Module 5 breakdown must never become the
    # authoritative LCA quantity source: it may be stale and, in old Projects,
    # may contain summary + detail double counting. Rebuild the material quantity
    # set directly from current Module 1 through the same canonical physical-
    # ownership bridge used by Module 5. Keep Module 5 only as an audit comparator.
    module5_breakdown=(module5 or {}).get("trade_material_breakdown") or (module5 or {}).get("cost_lines") or []
    module5_quantities_audit=extract_material_quantities_from_module5(module5)
    module5_breakdown_hash=_stable_hash(module5_breakdown) if module5_breakdown else None
    module5_breakdown_count=len(module5_breakdown)
    module5_method=(module5 or {}).get("construction_method")
    try:
        from services.construction_cost_engine_v9_4 import extract_quantities as _extract_canonical_quantities
        quantities, quantity_provenance, quantity_exclusions = _extract_canonical_quantities(project,module1,{})
        material_quantity_source="module1.quantity_takeoff via canonical physical ownership bridge"
    except Exception as exc:
        quantities=extract_material_quantities(module1)
        quantity_provenance={}
        quantity_exclusions=[]
        material_quantity_source="module1.quantity_takeoff legacy fallback: "+str(exc)

    quantity_mismatch_audit={}
    for _k in sorted(set(module5_quantities_audit)|set(quantities)):
        _m5=_f(module5_quantities_audit.get(_k)); _m1=_f(quantities.get(_k))
        if abs(_m5-_m1)>max(1e-9,1e-6*max(abs(_m5),abs(_m1),1.0)):
            quantity_mismatch_audit[_k]={"saved_module5_quantity":_m5,"canonical_module1_quantity":_m1}
    inventory=material_inventory(quantities, factors)
    inv_total=_inventory_totals(inventory)
    lca_mapped_keys={str(x.get("material_key")) for x in inventory}
    unmapped_module5_materials=sorted(k for k in quantities.keys() if k not in lca_mapped_keys and k!="formwork")
    component_mass_register={
        key:_component_material_masses(key,project,inventory)
        for key in ("infill_layout","infill_exterior","insulation","windows","roof","all_infill")
    }
    processes=factors["processes"]

    initial_mass_t=inv_total["mass_kg"]/1000.0
    initial_transport_co2=initial_mass_t * _f(processes["initial_transport_distance_km"]) * _f(processes["transport_co2_kg_per_tkm"])
    initial_construction_co2=floor_area * _f(processes["construction_co2_kg_per_m2"])
    initial_construction_energy=floor_area * _f(processes["construction_energy_MJ_per_m2"])
    initial_co2=inv_total["embodied_co2_kg"]+initial_transport_co2+initial_construction_co2
    initial_energy=inv_total["embodied_energy_MJ"]+initial_construction_energy

    base_operational_co2=_f(module2.get("operational_CO2_kg_per_year"))
    base_operational_energy=_f(module2.get("primary_energy_MJ_per_year"))
    base_electricity=_f(module2.get("total_building_electricity_kWh_per_year"))
    base_grid_factor=_f(module2.get("settings",{}).get("electricity_co2"),
                        base_operational_co2/max(base_electricity,1.0))

    annual=[{
        "year":0, "category":"initial_construction",
        "operational_co2_kg":0.0, "embodied_co2_kg":initial_co2,
        "demolition_co2_kg":0.0, "credit_co2_kg":0.0,
        "net_co2_kg":initial_co2,
        "operational_energy_MJ":0.0, "embodied_energy_MJ":initial_energy,
        "demolition_energy_MJ":0.0, "total_energy_MJ":initial_energy,
        "waste_kg":0.0, "reused_kg":0.0, "recycled_kg":0.0, "landfill_kg":0.0
    }]
    event_results=[]

    events_by_year={}
    for event in module3.get("events", []):
        year=int(_f(event.get("year")))
        if 0 < year <= period_years:
            events_by_year.setdefault(year,[]).append(event)

    operational_change=operational_change_pct/100.0
    grid_scenario_key, resolved_grid_change_pct = resolve_grid_decarbonization_scenario(
        grid_decarbonization_scenario, grid_change_pct
    )
    grid_change=resolved_grid_change_pct/100.0

    future_climate = calculate_future_climate_8760(
        project,
        module2,
        period_years,
        bool(future_climate_enabled),
        float(future_warming_C_at_year_100),
        float(future_warming_C_at_year_200),
        int(future_climate_milestone_interval_years),
    )
    climate_energy_factors = future_climate.get("annual_energy_factors") or [1.0] * (period_years + 1)
    climate_offsets = future_climate.get("annual_temperature_offsets_C") or [0.0] * (period_years + 1)

    for year in range(1,period_years+1):
        operational_factor=(1.0+operational_change)**(year-1)
        climate_factor=float(climate_energy_factors[year]) if year < len(climate_energy_factors) else 1.0
        energy_factor=operational_factor*climate_factor
        grid_factor=max(base_grid_factor*((1.0+grid_change)**(year-1)),0.0)
        operational_energy=base_operational_energy*energy_factor
        electricity=base_electricity*energy_factor
        operational_co2=electricity*grid_factor if base_electricity>0 else base_operational_co2*energy_factor

        embodied_co2=demolition_co2=credit=0.0
        embodied_energy=demolition_energy=0.0
        waste=reused=recycled=landfill=0.0

        for event in events_by_year.get(year,[]):
            action=str(event.get("action",""))
            if action=="inspection":
                continue
            ref_mass=_event_reference_mass(event,project,inventory,floor_area)
            removed_fraction=max(min(_f(event.get("removed_fraction")),1.0),0.0)
            retained_fraction=max(min(_f(event.get("retained_fraction")),1.0),0.0)
            reuse_fraction=max(min(_f(event.get("reused_fraction")),1.0),0.0)
            recycle_fraction=max(min(_f(event.get("recycled_fraction")),1.0),0.0)
            # Event semantics:
            # - retain_skeleton: the existing skeleton/core remains in place.
            #   No removal and no new-product manufacturing are counted.
            # - partial_demolition: removal/disposal only. Replacement, if any,
            #   must be represented by a separate replacement/rebuild event.
            # - repair / replacement / full_rebuild: removed material is replaced
            #   by new material and therefore carries new-product embodied impacts.
            if action == "retain_skeleton":
                removed_mass=0.0
                new_mass=0.0
            else:
                removed_mass=ref_mass*removed_fraction
                if action == "partial_demolition":
                    new_mass=0.0
                elif action in ("repair","skeleton_repair","replace_equipment",
                                "replace_infill","full_rebuild"):
                    new_mass=removed_mass
                else:
                    # Conservative default for unknown physical renewal actions.
                    new_mass=removed_mass

            reused_mass=removed_mass*reuse_fraction
            recycled_mass=max(removed_mass-reused_mass,0.0)*recycle_fraction
            landfill_mass=max(removed_mass-reused_mass-recycled_mass,0.0)

            mix=_component_mix(str(event.get("component_key","")),project,inventory)
            event_embodied_co2=event_embodied_energy=0.0
            for material_key,share in mix:
                mat=factors["materials"].get(material_key)
                if not mat:
                    continue
                density=max(_f(mat["density_kg_per_unit"]),0.001)
                qty=(new_mass*share)/density
                event_embodied_co2 += qty*_f(mat["embodied_co2_kg_per_unit"])
                event_embodied_energy += qty*_f(mat["embodied_energy_MJ_per_unit"])

            transport_co2=(new_mass/1000.0)*_f(processes["renewal_transport_distance_km"])*_f(processes["transport_co2_kg_per_tkm"])
            waste_transport_co2=(removed_mass/1000.0)*_f(processes["waste_transport_distance_km"])*_f(processes["transport_co2_kg_per_tkm"])
            event_demolition_co2=(removed_mass/1000.0)*_f(processes["demolition_co2_kg_per_t"])+waste_transport_co2
            event_demolition_energy=(removed_mass/1000.0)*_f(processes["demolition_energy_MJ_per_t"])

            event_credit=0.0
            if include_recycling_credit:
                event_credit += (recycled_mass/1000.0)*_f(processes["recycling_credit_co2_kg_per_t"])
                event_credit += event_embodied_co2*reuse_fraction*_f(processes["reuse_credit_fraction_of_new_product"])

            embodied_co2 += event_embodied_co2+transport_co2
            embodied_energy += event_embodied_energy
            demolition_co2 += event_demolition_co2
            demolition_energy += event_demolition_energy
            credit += event_credit
            waste += removed_mass
            reused += reused_mass
            recycled += recycled_mass
            landfill += landfill_mass
            event_results.append({
                "event_id":event.get("event_id",""),"year":year,"action":action,
                "co2_event_semantics":(
                    "retain_only_no_new_material" if action=="retain_skeleton" else
                    "demolition_only_no_new_material" if action=="partial_demolition" else
                    "renewal_with_new_material"
                ),
                "component_key":event.get("component_key",""),
                "component":event.get("component",""),
                "reference_mass_kg":ref_mass,"removed_mass_kg":removed_mass,
                "new_material_mass_kg":new_mass,"embodied_co2_kg":event_embodied_co2+transport_co2,
                "demolition_co2_kg":event_demolition_co2,"credit_co2_kg":event_credit,
                "embodied_energy_MJ":event_embodied_energy,
                "demolition_energy_MJ":event_demolition_energy,
                "reused_kg":reused_mass,"recycled_kg":recycled_mass,
                "landfill_kg":landfill_mass
            })

        net=operational_co2+embodied_co2+demolition_co2-credit
        total_energy=operational_energy+embodied_energy+demolition_energy
        annual.append({
            "year":year,"category":"annual",
            "operational_co2_kg":operational_co2,"embodied_co2_kg":embodied_co2,
            "demolition_co2_kg":demolition_co2,"credit_co2_kg":credit,
            "net_co2_kg":net,
            "operational_energy_MJ":operational_energy,
            "climate_temperature_offset_C":(
                float(climate_offsets[year]) if year < len(climate_offsets) else 0.0
            ),
            "climate_energy_factor":climate_factor,
            "operational_change_factor":operational_factor,
            "embodied_energy_MJ":embodied_energy,
            "demolition_energy_MJ":demolition_energy,
            "total_energy_MJ":total_energy,
            "waste_kg":waste,"reused_kg":reused,
            "recycled_kg":recycled,"landfill_kg":landfill
        })

    cumulative_co2=0.0
    cumulative_energy=0.0
    for row in annual:
        cumulative_co2 += row["net_co2_kg"]
        cumulative_energy += row["total_energy_MJ"]
        row["cumulative_co2_kg"]=cumulative_co2
        row["cumulative_energy_MJ"]=cumulative_energy

    def total(key:str)->float:
        return sum(_f(x.get(key)) for x in annual)

    wood_inventory=[
        {
            "material_key": item.get("material_key"),
            "material_name_ja": item.get("material_name_ja"),
            "material_name_en": item.get("material_name_en"),
            "product_type_ja": item.get("product_type_ja"),
            "product_type_en": item.get("product_type_en"),
            "wood_volume_m3": _f(item.get("quantity")),
            "dry_density_kg_per_m3": _f(item.get("dry_density_kg_per_m3")),
            "wood_fraction": _f(item.get("wood_fraction")),
            "dry_wood_mass_kg": _f(item.get("dry_wood_mass_kg")),
            "carbon_fraction": _f(item.get("carbon_fraction_of_dry_wood")),
            "biogenic_carbon_mass_kgC": _f(item.get("biogenic_carbon_mass_kgC")),
            "biogenic_storage_kgCO2": _f(item.get("biogenic_storage_kgCO2")),
            "biogenic_storage_tCO2": _f(item.get("biogenic_storage_kgCO2")) / 1000.0,
            "storage_duration_years": item.get("storage_duration_years", 0),
        }
        for item in inventory
        if item.get("is_wood_product")
    ]

    summary={
        "initial_embodied_co2_kg":initial_co2,
        "operational_co2_kg":total("operational_co2_kg"),
        "renewal_embodied_co2_kg":sum(x["embodied_co2_kg"] for x in annual[1:]),
        "demolition_co2_kg":total("demolition_co2_kg"),
        "reuse_recycling_credit_kg":total("credit_co2_kg"),
        "net_lifecycle_co2_kg":total("net_co2_kg"),
        "initial_embodied_energy_MJ":initial_energy,
        "operational_energy_MJ":total("operational_energy_MJ"),
        "renewal_embodied_energy_MJ":sum(x["embodied_energy_MJ"] for x in annual[1:]),
        "demolition_energy_MJ":total("demolition_energy_MJ"),
        "total_lifecycle_energy_MJ":total("total_energy_MJ"),
        "waste_generated_kg":total("waste_kg"),
        "reused_mass_kg":total("reused_kg"),
        "recycled_mass_kg":total("recycled_kg"),
        "landfill_mass_kg":total("landfill_kg"),
        "wood_volume_m3":inv_total["wood_volume_m3"],
        "dry_wood_mass_kg":inv_total["dry_wood_mass_kg"],
        "biogenic_carbon_mass_kgC":inv_total["biogenic_carbon_mass_kgC"],
        "biogenic_storage_kgCO2":inv_total["biogenic_storage_kgCO2"] if include_biogenic else 0.0,
        "biogenic_storage_tCO2":inv_total["biogenic_storage_kgCO2"]/1000.0 if include_biogenic else 0.0,
        "biogenic_storage_kgCO2_per_m2":inv_total["biogenic_storage_kgCO2"]/floor_area if include_biogenic else 0.0,
        "net_lifecycle_co2_after_biogenic_reference_kg":total("net_co2_kg")-(inv_total["biogenic_storage_kgCO2"] if include_biogenic else 0.0),
        "net_co2_intensity_kg_m2_year":total("net_co2_kg")/(floor_area*period_years),
        "energy_intensity_MJ_m2_year":total("total_energy_MJ")/(floor_area*period_years)
    }
    lca_module_crosswalk=build_lca_module_crosswalk(summary)

    return {
        "version":"9.4","module":"module4",
        "period_years":period_years,
        "settings":{
            "operational_change_pct_per_year":operational_change_pct,
            "grid_co2_change_pct_per_year":resolved_grid_change_pct,
            "grid_decarbonization_scenario":scenario_metadata(grid_scenario_key, resolved_grid_change_pct),
            "include_recycling_credit":bool(include_recycling_credit),
            "include_biogenic_storage":bool(include_biogenic),
            "future_climate_enabled":bool(future_climate_enabled),
            "future_warming_C_at_year_100":float(future_warming_C_at_year_100),
            "future_warming_C_at_year_200":float(future_warming_C_at_year_200),
            "future_climate_milestone_interval_years":int(future_climate_milestone_interval_years)
        },
        "future_climate_8760":future_climate,
        "material_quantity_source":material_quantity_source,
        "module5_breakdown_hash":module5_breakdown_hash,
        "module5_breakdown_count":module5_breakdown_count,
        "module5_construction_method":module5_method,
        "module5_quantity_mismatch_audit":quantity_mismatch_audit,
        "quantity_provenance":quantity_provenance,
        "quantity_exclusions":quantity_exclusions,
        "material_quantities_used":quantities,
        "component_mass_register":component_mass_register,
        "unmapped_module5_materials":unmapped_module5_materials,
        "initial_material_inventory":inventory,
        "wood_carbon_storage_inventory":wood_inventory,
        "biogenic_carbon_method":{
            "formula":"volume × dry density × wood fraction × carbon fraction × 44/12",
            "status":"planning_reference",
            "system_boundary_note":"Display separately from formal lifecycle emissions unless an applicable LCA method and end-of-life scenario permit deduction.",
        },
        "annual_timeline":annual,
        "event_impacts":event_results,
        "lca_module_crosswalk":lca_module_crosswalk,
        "summary":summary,
        "status":"provisional_planning_comparison",
        "disclaimer":"Planning comparison only; verified LCA data are required for formal use."
    }
