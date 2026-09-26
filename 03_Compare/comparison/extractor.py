from __future__ import annotations
import json
from pathlib import Path
# PATCH_006: Japanese display names (presentation only; stored values untouched).
from comparison import display_ja as DJ

MONTHS_JA=["1月","2月","3月","4月","5月","6月","7月","8月","9月","10月","11月","12月"]

def _num(v):
    try:return float(v)
    except (TypeError,ValueError):return None

def _walk(obj,path=()):
    if isinstance(obj,dict):
        for k,v in obj.items():
            yield path+(str(k),),v;yield from _walk(v,path+(str(k),))
    elif isinstance(obj,list):
        for i,v in enumerate(obj):yield path+(str(i),),v;yield from _walk(v,path+(str(i),))

def _find_number(obj,aliases):
    wanted={x.lower() for x in aliases}
    for path,v in _walk(obj):
        if path[-1].lower() in wanted:
            n=_num(v)
            if n is not None:return n
    return None

def _method(project):
    c=project.get('common') or {};d=c.get('detailed_configuration') or {}
    if d.get('building_system')=='azras' or c.get('construction_method_id')=='azras':return str(c.get('construction_method_name_en') or c.get('construction_method_name') or 'AZRAS')
    g=d.get('general') or {}
    return str(c.get('construction_method_detail_name_en') or c.get('construction_method_name_en') or c.get('construction_method_name') or g.get('method') or g.get('structure') or 'Unknown')

def _method_ja(project):
    """PATCH_006: Japanese display name of the same method _method() returns.

    01 Planning saves construction_method_(detail_)name_ja beside the _en
    names; Compare used only the _en names, so the Japanese screen showed
    e.g. "[Conventional RC]".  Older Projects without *_ja fall back to the
    Planning method registry, then to the English name (never guessed).
    """
    c=project.get('common') or {};d=c.get('detailed_configuration') or {}
    if d.get('building_system')=='azras' or c.get('construction_method_id')=='azras':
        return str(c.get('construction_method_name_ja') or DJ.structure_ja('azras'))
    g=d.get('general') or {}
    if c.get('construction_method_detail_name_ja') or c.get('construction_method_detail_id') or c.get('construction_method_detail_name_en'):
        return DJ.method_ja(c.get('construction_method_detail_id'),c.get('construction_method_detail_name_ja'),c.get('construction_method_detail_name_en'))
    if c.get('construction_method_name_ja') or c.get('construction_method_name_en'):
        return DJ.structure_ja(c.get('construction_method_id'),c.get('construction_method_name_ja'),c.get('construction_method_name_en'))
    return DJ.method_ja(g.get('method') or '', '', '') or DJ.structure_ja(c.get('construction_method_id') or g.get('structure') or '') or _method(project)

def _module2_settings(project):
    m2=((project.get('module_outputs') or {}).get('module2') or {})
    for cand in (((m2.get('_input_snapshot') or {}).get('settings') or {}), m2.get('settings') or {}):
        if isinstance(cand,dict) and cand:return cand
    return {}

# PATCH_004: envelope terms that the Module 10 snapshot and Module 2 must agree
# on.  (snapshot model_config key, Module 2 breakdown key) pairs for U-value and
# area; they are compared as a conductance U x A so a zero-area component can
# never raise a false alarm.
_ENVELOPE_PAIRS=(
    ('rc_wall',   'u_rc_wall_W_m2K',    'rc_exterior_area_m2',    'rc_wall_u_W_m2K_used',    'rc_wall_area_m2_used'),
    ('light_wall','u_light_wall_W_m2K', 'light_exterior_area_m2', 'light_wall_u_W_m2K_used', 'light_wall_area_m2_used'),
)
_ENVELOPE_ABS_TOL_W_K=1.0
_ENVELOPE_REL_TOL=0.02

def snapshot_envelope_mismatches(project):
    """PATCH_004: list envelope terms where the saved 8760 snapshot and the saved
    Module 2 result disagree.

    The Module 10 snapshot is a separate saved artefact.  When Module 2 is
    re-calculated (for example after an envelope correction) and the regional
    analysis is not regenerated, the snapshot keeps the OLD envelope while the
    Project looks up to date.  Compare prefers the snapshot for energy, so it then
    presents the old energy as current.  On 260918_RC_Rahmen_Sample the snapshot
    still modelled the light wall at U = 5.88 W/m2K after Module 2 had been
    corrected to 0.13, i.e. 488 W/K against 11 W/K, and Compare kept showing the
    uncorrected 23,207 kWh.  Returns [] when the snapshot is consistent or when
    either side lacks the data needed to compare.
    """
    snap=(project.get('regional_analysis') or {}).get('module10_snapshot') or {}
    model=snap.get('model_config') if isinstance(snap,dict) else None
    m2=((project.get('module_outputs') or {}).get('module2') or {})
    br=m2.get('floor_thermal_breakdown') if isinstance(m2,dict) else None
    if not isinstance(model,dict) or not isinstance(br,dict) or not model or not br:
        return []
    out=[]
    for part,su,sa,mu,ma in _ENVELOPE_PAIRS:
        vals=[_num(model.get(su)),_num(model.get(sa)),_num(br.get(mu)),_num(br.get(ma))]
        if any(v is None for v in vals):
            continue
        g_snap=vals[0]*vals[1]; g_m2=vals[2]*vals[3]
        diff=abs(g_snap-g_m2)
        if diff>max(_ENVELOPE_ABS_TOL_W_K,_ENVELOPE_REL_TOL*max(abs(g_snap),abs(g_m2))):
            out.append({'component':part,
                        'snapshot_u_W_m2K':vals[0],'snapshot_area_m2':vals[1],'snapshot_conductance_W_K':g_snap,
                        'module2_u_W_m2K':vals[2],'module2_area_m2':vals[3],'module2_conductance_W_K':g_m2})
    return out

def _snapshot(project):
    """PATCH 044: reject a regional snapshot that lost Module 2 thermal inputs.

    Planning PATCH_527 now writes the same passive-strategy values into the
    actual Module10 model_config.  Older snapshots can be detected when saved
    Module 2 says night release/ventilation is enabled but model_config fell
    back to disabled defaults.  Compare must not present such a snapshot as a
    valid apples-to-apples 8760 result.
    """
    snap=(project.get('regional_analysis') or {}).get('module10_snapshot') or {}
    if not isinstance(snap,dict) or not snap:return {}
    settings=_module2_settings(project); model=snap.get('model_config') or {}
    if settings and isinstance(model,dict) and model:
        bool_keys=('thermal_mass_enabled','external_insulation_enabled','night_heat_release_enabled','natural_night_ventilation_enabled')
        num_keys=('night_release_conductance_W_K','night_ventilation_ach','night_ventilation_delta_C')
        for key in bool_keys:
            if key in settings and key in model and bool(settings.get(key)) != bool(model.get(key)):
                return {}
        for key in num_keys:
            if key in settings and key in model:
                a=_num(settings.get(key));b=_num(model.get(key))
                if a is not None and b is not None and abs(a-b)>1e-9:return {}
    # PATCH_004: same rule for the envelope itself.  A snapshot built on an
    # envelope that Module 2 no longer uses is not a valid 8760 result for this
    # Project; fall back exactly as PATCH 044 does for passive settings.
    if snapshot_envelope_mismatches(project):
        return {}
    return snap

def _monthly(project, prefer_regional_snapshot=True):
    """Return the saved EPW 8760-hour monthly result for every region.

    PATCH 095:
    All regions, including the base/Kasugai project, use the same calculation
    basis: regional_analysis.module10_snapshot generated by the common EPW
    8760-hour dynamic-orientation model.  Module 2 reduced-model annual values
    are no longer substituted into Compare's regional/energy comparison.
    """
    s=_snapshot(project);rows=s.get('monthly')
    if not isinstance(rows,list) or len(rows)<12:return None

    def col(k):
        vals=[]
        for r in rows[:12]:
            n=_num(r.get(k)) if isinstance(r,dict) else None
            if n is None:return None
            vals.append(n)
        return vals

    return {
        'energy':col('total_use_kWh'),
        'pv':col('pv_generation_kWh'),
        'net':col('net_energy_kWh'),
        'heating':col('heating_electricity_kWh'),
        'cooling':col('cooling_electricity_kWh'),
        'source':'module10_snapshot_8760_uniform',
        'scale_factor':1.0
    }

def _get_path(obj, path):
    cur=obj
    for key in path:
        if not isinstance(cur,dict) or key not in cur:return None
        cur=cur[key]
    return cur

def _parse_explicit_timeline(value, value_aliases):
    """Parse a formally stored timeline without interpolation or inference."""
    rows=[]
    if isinstance(value,dict):
        for y,v in value.items():
            yn=_num(y);vn=_num(v)
            if yn is not None and vn is not None:rows.append((int(yn),vn))
    elif isinstance(value,list):
        for row in value:
            if not isinstance(row,dict):continue
            y=next((_num(v) for k,v in row.items() if str(k).lower() in ('year','年')),None)
            # Respect alias priority rather than JSON key insertion order.
            lower_map={str(k).lower():v for k,v in row.items()}
            val=next((_num(lower_map.get(alias.lower())) for alias in value_aliases
                      if _num(lower_map.get(alias.lower())) is not None),None)
            if y is not None and val is not None:rows.append((int(y),val))
    rows=sorted(rows)
    if len(rows)<2:return []
    years=[y for y,_ in rows]
    if len(years)!=len(set(years)) or any(b<=a for a,b in zip(years,years[1:])):return []
    return rows

def _formal_timeline(project, specs, aliases, required_flag):
    """Read only explicitly approved, calculation-saved annual timelines.

    A series is accepted only when its parent object declares the required
    construction-event flag and identifies itself as calculated/saved/final.
    """
    for path in specs:
        parent=_get_path(project,path[:-1]);value=_get_path(project,path)
        if not isinstance(parent,dict):continue
        flag=parent.get(required_flag)
        status=str(parent.get('status') or parent.get('calculation_status') or parent.get('data_status') or '').lower()
        if flag is not True or status not in ('calculated','saved','final','complete','completed'):continue
        rows=_parse_explicit_timeline(value,aliases)
        if rows:
            return rows,'.'.join(path),status
    return [],'', 'missing_or_unverified'

# PATCH_004: Evaluation results that are derived from Planning inputs.
_DOWNSTREAM_OF={
    'module2':('module3','module4','module6','module7'),
    'module5':('module6','module7'),
}

def stale_downstream_results(project):
    """PATCH_004: Evaluation results saved BEFORE the Planning input they use.

    Each module records its own save time in module_status.  If Module 2
    (energy) or Module 5 (construction cost) was saved after the Evaluation
    module that consumes it, that Evaluation result was calculated from the
    previous input and is stale.  Compare only reports this; it never
    recalculates, hides or rewrites a result.
    """
    ms=project.get('module_status') or {}
    def ts(key):
        v=ms.get(key)
        return str(v.get('updated_at') or '') if isinstance(v,dict) else ''
    out=[]
    for src,dsts in _DOWNSTREAM_OF.items():
        t_src=ts(src)
        if not t_src:
            continue
        for dst in dsts:
            t_dst=ts(dst)
            if t_dst and t_dst<t_src:
                out.append({'input_module':src,'input_saved_at':t_src,
                            'result_module':dst,'result_saved_at':t_dst})
    return out

def _saved_module(project, module_key):
    module=(project.get('module_outputs') or {}).get(module_key)
    if not isinstance(module,dict) or not module:
        return None
    meta=module.get('_meta') or {}
    status=str(meta.get('status') or '').lower()
    # PATCH 19 current-only contract: a populated legacy module without _meta
    # is not proof of a current saved result.  Compare must never revive it.
    return module if status in ('saved','calculated','final','complete','completed','auto_updated') else None

def _co2(project):
    """Read the saved 02 Evaluation Module 4 cumulative CO2 timeline only.

    PATCH 16 responsibility boundary:
    Compare does not recalculate operational CO2, grid decarbonization, embodied
    events, demolition, credits, or any other Evaluation-owned result.
    """
    m4=_saved_module(project,'module4')
    if not m4:
        return [],'', 'missing_evaluation_module4'
    rows=_parse_explicit_timeline(
        m4.get('annual_timeline'),
        ('cumulative_co2_kg','cumulative_lifecycle_co2_kg','cumulative_net_co2_kg')
    )
    if rows:
        return rows,'module_outputs.module4.annual_timeline','saved_evaluation'
    return [],'', 'missing_evaluation_module4_timeline'

def _cashflow(project,json_path):
    """Read Evaluation-saved cumulative present-value holding-period CF only.

    PATCH 16: Compare never recalculates discounting or terminal-sale treatment.
    Evaluation v1.0.209+ persists
    `cumulative_discounted_unlevered_cash_flow_ex_terminal` per year.
    """
    m6=_saved_module(project,'module6')
    if not m6:
        return [],'', 'missing_evaluation_module6'
    raw=m6.get('cashflow')
    if not isinstance(raw,list):
        return [],'', 'missing_evaluation_cashflow'
    rows=[]
    # Evaluation cashflow starts at year 1; year 0 comes from the saved summary.
    summary=m6.get('summary') or {}
    initial=_num(summary.get('initial_total_investment'))
    if initial is not None:
        rows.append((0,-initial))
    expected=1
    for row in raw:
        if not isinstance(row,dict):
            return [],'', 'invalid_evaluation_cashflow'
        year=_num(row.get('year'))
        value=_num(row.get('cumulative_discounted_unlevered_cash_flow_ex_terminal'))
        if year is None or value is None or int(year)!=expected:
            return [],'', 'missing_saved_present_value_timeline'
        rows.append((int(year),value))
        expected+=1
    return (rows,'module_outputs.module6.cashflow.cumulative_discounted_unlevered_cash_flow_ex_terminal','saved_evaluation') if len(rows)>=2 else ([], '', 'missing_saved_present_value_timeline')

def _nominal_cashflow(project):
    """Read Evaluation-saved nominal holding-period cumulative CF only."""
    m6=_saved_module(project,'module6')
    if not m6:
        return [],'', 'missing_evaluation_module6'
    raw=m6.get('cashflow')
    summary=m6.get('summary') or {}
    initial=_num(summary.get('initial_total_investment'))
    if not isinstance(raw,list) or initial is None:
        return [],'', 'missing_nominal_cashflow'
    rows=[(0,-initial)]
    expected=1
    for row in raw:
        if not isinstance(row,dict):
            return [],'', 'invalid_nominal_cashflow'
        year=_num(row.get('year'))
        value=_num(row.get('cumulative_unlevered_cash_flow_ex_terminal'))
        if year is None or value is None or int(year)!=expected:
            return [],'', 'missing_saved_nominal_timeline'
        rows.append((int(year),value))
        expected+=1
    return rows,'module_outputs.module6.cashflow.cumulative_unlevered_cash_flow_ex_terminal','saved_evaluation'

def _annual_co2(project, prefer_regional_snapshot=True):
    """Read saved annual operational CO2 only; Compare performs no calculation."""
    annual=(_snapshot(project).get('annual') or {})
    for key in ('operational_co2_kg','net_operational_CO2_kg'):
        n=_num(annual.get(key))
        if n is not None:
            return n/1000.0
    m2=_saved_module(project,'module2') or {}
    for key in ('net_operational_CO2_kg_per_year','operational_CO2_kg_per_year','annual_operational_co2_kg'):
        n=_num(m2.get(key))
        if n is not None:
            return n/1000.0
    return None

def _first_present(key,*sources):
    """First value that is actually present (not None) - 0 and False count."""
    for src in sources:
        if isinstance(src,dict) and src.get(key) is not None:
            return src.get(key)
    return None

def _target_yield_state(m6,m6_summary,m6_settings,m6_snapshot_settings,rent_setting_method):
    """(active, effective target yield %, stored inactive yield %).

    Priority: the explicit target_gross_yield_active flag (02 Evaluation
    PATCH_009 and later) -> the rent method (gross_yield = active, any other
    known method = inactive) -> legacy JSON with no method at all, where the
    saved value is reported as before.  An inactive yield is never returned as
    the effective target; it is only reported as the stored memo value."""
    flag=_first_present('target_gross_yield_active',m6,m6_summary,m6_settings,m6_snapshot_settings)
    if isinstance(flag,bool):
        active=flag
    elif rent_setting_method:
        active=(rent_setting_method=='gross_yield')
    else:
        active=True
    raw=_num(_first_present('target_gross_yield_percent',m6,m6_summary,m6_settings,m6_snapshot_settings))
    stored=_num(_first_present('stored_target_gross_yield_percent',m6,m6_summary,m6_settings,m6_snapshot_settings))
    if active:
        return True,raw,stored
    # Pre-PATCH_009 market-rent JSON may still carry the old yield in
    # target_gross_yield_percent; report it as the stored memo, never as active.
    return False,None,(stored if stored is not None else raw)

def extract_core_project(path, prefer_regional_snapshot=True):
    path=Path(path)
    d=json.loads(path.read_text(encoding='utf-8-sig'))
    c=d.get('common') or {}
    mo=_monthly(d,prefer_regional_snapshot=prefer_regional_snapshot)
    snap=_snapshot(d)
    annual=(snap.get('annual') or {})
    identity=c.get('project_identity') or {}
    co2,co2_source,co2_status=_co2(d)
    cash,cash_source,cash_status=_cashflow(d,path)
    nominal_cash,nominal_cash_source,nominal_cash_status=_nominal_cashflow(d)
    m2=_saved_module(d,'module2') or {}
    m5=_saved_module(d,'module5') or {}
    m6=_saved_module(d,'module6') or {}
    # PATCH_003: two premises decide whether a cross-Project comparison is
    # meaningful at all, and neither was being carried out of the JSON.
    #
    # Revenue basis: when Module 6 derives rent from the construction cost at a
    # fixed target gross yield, every Project pays back at the same year by
    # construction, and a more expensive building silently receives a
    # proportionally higher rent. That is a legitimate single-Project study but
    # it is not a comparison between buildings.
    #
    # Price basis: a Project priced from an imported AI approximate-cost
    # session (installed all-in rates) and a Project priced from the built-in
    # regional city estimate (material/labor/equipment split) are not on the
    # same scale, so a cost difference between them is partly a price-origin
    # difference rather than a construction-method difference.
    m6_settings=m6.get('settings') or {}
    # PATCH_007: the settings Evaluation saved with the result are also kept in
    # _input_snapshot (premise_book reads them there); use them as the last
    # fallback so the same Project gives the same rent premise in both places.
    m6_snapshot_settings=(m6.get('_input_snapshot') or {}).get('settings') or {}
    rent_setting_method=str(
        m6.get('rent_setting_method')
        or (m6.get('revenue_basis_disclosure') or {}).get('rent_setting_method')
        or m6_settings.get('rent_setting_method')
        or m6_snapshot_settings.get('rent_setting_method')
        or ''
    )
    rent_derived_from_cost=(rent_setting_method=='gross_yield')
    # PATCH_007: 02 Evaluation PATCH_009 market-rent contract.  In market-rent
    # mode Evaluation saves summary.target_gross_yield_percent = null,
    # summary.stored_target_gross_yield_percent = the user's preference and
    # target_gross_yield_active = false (summary and settings); settings keep
    # the preference in target_gross_yield_percent so the UI can restore it.
    # The old read "m6.get(k) or settings.get(k)" never saw the flag and
    # returned that preference (8 %) as if it had driven the rent.
    target_gross_yield_active,target_gross_yield_percent,stored_target_gross_yield_percent=_target_yield_state(
        m6,m6.get('summary') or {},m6_settings,m6_snapshot_settings,rent_setting_method)
    price_basis_token=str((m5.get('price_basis_fingerprint') or {}).get('basis_token') or '')
    if not price_basis_token:
        # Project JSONs saved before 01 Planning PATCH_040 have no fingerprint.
        # Fall back to the pricing mode, which has always been persisted.
        mode=str(m5.get('location_pricing_mode') or '')
        if mode.startswith('ai_approximate_cost_session'):
            price_basis_token='ai_approximate_cost_session'
        elif mode:
            price_basis_token='regional_cost_database'
        else:
            price_basis_token='unknown'

    tax_treatment=m6.get('tax_treatment') or {}
    tax_excluded=(
        tax_treatment.get('land_and_building_related_taxes')=='excluded'
        and tax_treatment.get('included_in_cashflow') is False
    )

    annual_energy=_num(annual.get('total_use_kWh'))
    if annual_energy is None and mo and mo.get('energy'):
        annual_energy=sum(mo['energy'])
    if annual_energy is None:
        annual_energy=_num(m2.get('total_building_electricity_kWh_per_year'))
    energy_source='module10_snapshot_8760_uniform' if _snapshot(d) else 'module_outputs.module2_fallback'

    project_name=str(c.get('project_name') or path.stem)
    method_name=_method(d)
    building_use=str(c.get('building_use') or (c.get('building') or {}).get('use') or 'Unknown')
    general=((c.get('detailed_configuration') or {}).get('general') or {})
    # PATCH_006: prefer the saved structure NAME over the raw registry id
    # (general.structure is an id such as 'rc_frame').
    structure=str(c.get('construction_method_name_en') or general.get('structure') or method_name or 'Unknown')
    structure_ja=DJ.structure_ja(c.get('construction_method_id') or general.get('structure'),
                                 c.get('construction_method_name_ja'),c.get('construction_method_name_en') or structure)
    method_name_ja=_method_ja(d)
    gfa=_num(c.get('scale_gfa_m2'))
    if gfa is None:
        gfa=_num((c.get('building') or {}).get('gross_floor_area_m2'))
    construction_cost=_num((m5.get('summary') or {}).get('total_construction_cost'))
    lifecycle_co2_200=None
    if co2:
        lifecycle_co2_200=next((v for y,v in co2 if int(y)==200),None)
    annual_energy_per_m2=(annual_energy/gfa) if annual_energy is not None and gfa and gfa>0 else None
    construction_cost_per_m2=(construction_cost/gfa) if construction_cost is not None and gfa and gfa>0 else None
    lifecycle_co2_200_per_m2=(lifecycle_co2_200/gfa) if lifecycle_co2_200 is not None and gfa and gfa>0 else None
    label=f'{project_name} [{method_name}]'
    label_ja=f'{project_name} [{method_name_ja}]'

    # 02 Evaluation completion is judged only from saved calculation outputs.
    # Missing results are never converted to zero or inferred by Compare.
    evaluation_200_environment_done = lifecycle_co2_200 is not None
    evaluation_200_business_done = bool(cash) and next((v for y,v in cash if int(y)==200), None) is not None
    if evaluation_200_environment_done and evaluation_200_business_done:
        evaluation_status = 'complete'
    elif evaluation_200_environment_done or evaluation_200_business_done:
        evaluation_status = 'partial'
    else:
        evaluation_status = 'not_calculated'

    return {
        'source':str(path),
        'project':project_name,
        'method':method_name,
        'label':label,
        # PATCH_006: Japanese display variants; 'label' stays the comparison key.
        'method_ja':method_name_ja,
        'label_ja':label_ja,
        'building_use':building_use,
        'building_use_ja':DJ.use_ja(building_use),
        'structure':structure,
        'structure_ja':structure_ja,
        'gfa_m2':gfa,
        'construction_cost':construction_cost,
        'construction_cost_per_m2':construction_cost_per_m2,
        'annual_energy_per_m2':annual_energy_per_m2,
        'lifecycle_co2_200_kg':lifecycle_co2_200,
        'lifecycle_co2_200_per_m2_kg':lifecycle_co2_200_per_m2,
        'city':str(c.get('city') or snap.get('city') or ''),
        'country':str(c.get('country') or ''),
        # PATCH_004: the currency of a cost is the currency it was priced in.
        # Module 5/6 are the modules that priced it; project_identity is only a
        # Module 0 declaration and can lag behind a change of project region
        # (260919_S-Structure_Sample: identity JPY, Module 5/6 USD, so
        # $1,226,508 was presented as JPY 1,226,508).
        'currency':str(m5.get('currency') or m6.get('currency') or identity.get('currency') or c.get('currency') or 'JPY'),
        'declared_identity_currency':str(identity.get('currency') or c.get('currency') or ''),
        'currency_conflict':bool(
            (identity.get('currency') or c.get('currency'))
            and (m5.get('currency') or m6.get('currency'))
            and str(identity.get('currency') or c.get('currency')).upper()
                != str(m5.get('currency') or m6.get('currency')).upper()
        ),
        'snapshot_envelope_mismatches':snapshot_envelope_mismatches(d),
        'stale_downstream_results':stale_downstream_results(d),
        'monthly':mo or {},
        'energy_source':energy_source,
        'energy_scale_factor':(mo or {}).get('scale_factor',1.0),
        'annual_energy':annual_energy,
        'annual_co2_t':_annual_co2(d,prefer_regional_snapshot=True),
        'electricity_co2_factor_kg_per_kWh':_num(annual.get('electricity_co2_factor_kg_per_kWh')),
        'co2':co2,'cashflow':cash,'nominal_cashflow':nominal_cash,
        'co2_source':co2_source,'co2_status':co2_status,
        'cashflow_source':cash_source,'cashflow_status':cash_status,
        'nominal_cashflow_source':nominal_cash_source,'nominal_cashflow_status':nominal_cash_status,
        'rent_setting_method':rent_setting_method or 'unknown',
        'rent_derived_from_cost':rent_derived_from_cost,
        'target_gross_yield_percent':target_gross_yield_percent,
        'target_gross_yield_active':target_gross_yield_active,
        'stored_target_gross_yield_percent':stored_target_gross_yield_percent,
        'resolved_annual_rent_per_m2':_num(m6.get('resolved_annual_rent_per_m2') or m6_settings.get('resolved_annual_rent_per_m2')),
        'price_basis_token':price_basis_token,
        'location_pricing_mode':str(m5.get('location_pricing_mode') or ''),
        'tax_excluded_from_cashflow':tax_excluded,
        'tax_treatment':tax_treatment,
        'co2_lifecycle_available':bool(co2),
        'cashflow_available':bool(cash),
        'evaluation_200_environment_done':evaluation_200_environment_done,
        'evaluation_200_business_done':evaluation_200_business_done,
        'evaluation_status':evaluation_status,
        'regional_snapshot_preferred':True,
        'uniform_8760_basis':True,
        'raw':d
    }

def regional_projects(path):
    base=extract_core_project(path,prefer_regional_snapshot=True);result=[base];d=base['raw'];root=Path(path).parent
    seen={(base['city'].strip().lower(),base['country'].strip().lower())}
    for item in (d.get('regional_analysis') or {}).get('generated_region_files') or []:
        candidates=[]
        if item.get('path'):candidates.append(Path(item['path']))
        if item.get('file'):candidates.extend([root/item['file'],root/(d.get('regional_analysis') or {}).get('generated_region_folder','')/item['file']])
        p=next((x for x in candidates if x.exists()),None)
        if not p:continue
        try:r=extract_core_project(p,prefer_regional_snapshot=True)
        except Exception:continue
        k=(r['city'].strip().lower(),r['country'].strip().lower())
        if k not in seen:seen.add(k);result.append(r)
    return result
