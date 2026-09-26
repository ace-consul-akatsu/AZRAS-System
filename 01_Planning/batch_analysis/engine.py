from __future__ import annotations
import copy,csv,json,math,re
from datetime import datetime,timezone
from pathlib import Path
from core.project_coordinator import module_output_is_current
from typing import Any

def _now(): return datetime.now(timezone.utc).isoformat()
def _f(v,d=0.0):
    try:return float(v)
    except (TypeError,ValueError):return d
def _slug(s): return re.sub(r"[^0-9A-Za-z_\-]+","_",str(s)).strip("_") or "case"

# Representative planning values for the registered climate classes.
# These values deliberately avoid the old latitude-only rule, which produced
# zero cooling for New York/Sapporo and excessive heating for Dubai.
_CLIMATE_PROFILES = {
    "tropical_humid":       (27.5,   0.0, 3300.0, 1650.0),
    "hot_arid":             (28.5,  20.0, 3600.0, 2150.0),
    "hot_semi_arid":        (25.0, 180.0, 2700.0, 1950.0),
    "humid_subtropical":    (16.5, 1500.0, 750.0, 1450.0),
    "humid_continental":    (12.5, 3000.0, 650.0, 1350.0),
    "marine_temperate":     (11.5, 2850.0, 120.0, 1050.0),
    "mediterranean":        (18.0, 900.0, 850.0, 1750.0),
    "cold_snow":            (8.5, 4500.0, 180.0, 1250.0),
    "cool_temperate":       (9.5, 3500.0, 180.0, 1100.0),
    "cold":                 (6.5, 4800.0, 80.0, 950.0),
    "subtropical_highland": (16.0, 650.0, 220.0, 1900.0),
}

# City-specific planning values are used only for the registered comparison
# cities. They remain labelled as planning estimates and do not replace EPW.
_CITY_CLIMATE_OVERRIDES = {
    "tokyo":       (16.4, 1450.0, 780.0, 1450.0),
    "nagoya":      (16.1, 1650.0, 850.0, 1500.0),
    "sapporo":     (8.9, 4400.0, 170.0, 1250.0),
    "london":      (11.3, 2850.0, 120.0, 1050.0),
    "paris":       (12.3, 2600.0, 220.0, 1150.0),
    "new york":    (13.0, 3000.0, 720.0, 1400.0),
    "los angeles": (18.6, 700.0, 900.0, 1850.0),
    "dubai":       (28.7, 10.0, 3900.0, 2200.0),
    "singapore":   (27.8, 0.0, 3500.0, 1600.0),
    "bangkok":     (28.1, 0.0, 3600.0, 1750.0),
    "delhi":       (25.0, 220.0, 2850.0, 1900.0),
    "sydney":      (18.2, 850.0, 620.0, 1550.0),
    "berlin":      (10.0, 3400.0, 190.0, 1100.0),
    "oslo":        (6.8, 4700.0, 80.0, 950.0),
    "toronto":     (9.5, 3900.0, 560.0, 1350.0),
    "mexico city": (16.0, 600.0, 180.0, 1950.0),
}


_CITY_ALIASES = {
    "春日井市": "nagoya",
    "春日井": "nagoya",
    "kasugai": "nagoya",
    "愛知県春日井市": "nagoya",
    "名古屋市": "nagoya",
    "名古屋": "nagoya",
    "札幌市": "sapporo",
    "札幌": "sapporo",
    "ロンドン": "london",
    "ニューヨーク": "new york",
    "ドバイ": "dubai",
    "シンガポール": "singapore",
    "デリー": "delhi",
    "シドニー": "sydney",
}

def _normalise_city(city):
    raw = str(city or "").strip()
    lower = raw.lower()
    if raw in _CITY_ALIASES:
        return _CITY_ALIASES[raw]
    for key, value in _CITY_ALIASES.items():
        if key and (key.lower() in lower or key in raw):
            return value
    return lower




def _monthly_temperature_estimates(mean_t, climate_zone, latitude, city):
    zone=str(climate_zone or '').lower(); city_key=_normalise_city(city)
    seasonal_amp=10.0; half_daily_range=5.0
    if 'tropical' in zone: seasonal_amp,half_daily_range=1.8,3.5
    elif 'hot_arid' in zone or 'semi_arid' in zone: seasonal_amp,half_daily_range=8.5,7.0
    elif 'marine' in zone: seasonal_amp,half_daily_range=6.5,4.0
    elif 'mediterranean' in zone: seasonal_amp,half_daily_range=8.5,5.5
    elif 'cold' in zone or 'snow' in zone: seasonal_amp,half_daily_range=14.0,5.5
    elif 'continental' in zone: seasonal_amp,half_daily_range=13.0,5.5
    elif 'subtropical' in zone: seasonal_amp,half_daily_range=9.0,5.0
    city_overrides={
        'sapporo':(14.0,5.0),'london':(6.5,4.0),'new york':(13.0,5.5),
        'dubai':(8.5,6.0),'singapore':(1.2,3.5),'delhi':(10.5,6.5),
        'sydney':(5.8,4.5),'nagoya':(11.0,5.0),
    }
    if city_key in city_overrides: seasonal_amp,half_daily_range=city_overrides[city_key]
    peak_month=6 if _f(latitude)>=0 else 0
    rows=[]
    for month_index in range(12):
        angle=2.0*math.pi*(month_index-peak_month)/12.0
        monthly_mean=_f(mean_t)+seasonal_amp*math.cos(angle)
        rows.append({
            'month':month_index+1,
            'mean_C':round(monthly_mean,1),
            'mean_high_C':round(monthly_mean+half_daily_range,1),
            'mean_low_C':round(monthly_mean-half_daily_range,1),
            'source_type':'estimated_monthly_temperature_profile',
        })
    return rows


def _epw_climate(path):
    """Read EPW hourly observations and calculate A-level weather statistics.

    EPW fields used directly: dry bulb, dew point, relative humidity, horizontal
    infrared radiation intensity, GHI, DNI, DHI, wind direction/speed, total and
    opaque sky cover. HDD/CDD are calculated directly from EPW daily mean dry
    bulb temperatures. No climate-profile estimate is used.
    """
    epw_path=Path(path)
    if not epw_path.exists() or epw_path.suffix.lower() != '.epw':
        raise FileNotFoundError(f'EPW file not found: {epw_path}')

    def valid(value, low=None, high=None):
        try: x=float(value)
        except (TypeError,ValueError): return None
        if low is not None and x < low: return None
        if high is not None and x > high: return None
        return x

    monthly={m:{'rows':[],'daily':{},'ghi_Wh_m2':0.0,'dni_Wh_m2':0.0,'dhi_Wh_m2':0.0,
                'hir_W_m2':[],'rh_pct':[],'dew_C':[],'wind_m_s':[],'wind_dir_deg':[],
                'total_sky_tenths':[],'opaque_sky_tenths':[]} for m in range(1,13)}
    metadata={}
    with epw_path.open('r',encoding='utf-8',errors='replace') as f:
        first=f.readline().strip(); parts=[x.strip() for x in first.split(',')]
        if len(parts)>=10 and parts[0].upper()=='LOCATION':
            metadata={'city':parts[1],'state':parts[2],'country':parts[3],'source':parts[4],
                      'wmo':parts[5],'latitude':_f(parts[6]),'longitude':_f(parts[7]),
                      'timezone':_f(parts[8]),'elevation_m':_f(parts[9])}
        for _ in range(7): f.readline()
        for line in f:
            row=line.rstrip('\n').split(',')
            if len(row)<35: continue
            try: month=int(row[1]); day=int(row[2])
            except (ValueError,IndexError): continue
            if month not in monthly: continue
            temp=valid(row[6],-90,70)
            if temp is None: continue
            item=monthly[month]
            item['rows'].append(temp)
            item['daily'].setdefault(day,[]).append(temp)
            dew=valid(row[7],-100,70); rh=valid(row[8],0,110)
            hir=valid(row[12],0,1000); ghi=valid(row[13],0,2000)
            dni=valid(row[14],0,2000); dhi=valid(row[15],0,2000)
            wdir=valid(row[20],0,360); wspd=valid(row[21],0,100)
            sky=valid(row[22],0,10); osky=valid(row[23],0,10)
            if dew is not None:item['dew_C'].append(dew)
            if rh is not None:item['rh_pct'].append(rh)
            if hir is not None:item['hir_W_m2'].append(hir)
            if ghi is not None:item['ghi_Wh_m2']+=ghi
            if dni is not None:item['dni_Wh_m2']+=dni
            if dhi is not None:item['dhi_Wh_m2']+=dhi
            if wspd is not None:item['wind_m_s'].append(wspd)
            if wdir is not None and wspd is not None:
                item['wind_dir_deg'].append((wdir,wspd))
            if sky is not None:item['total_sky_tenths'].append(sky)
            if osky is not None:item['opaque_sky_tenths'].append(osky)

    profiles=[]; all_temps=[]; annual_hdd=0.0; annual_cdd=0.0
    annual_ghi=annual_dni=annual_dhi=0.0
    annual_rh=[]; annual_dew=[]; annual_hir=[]; annual_wind=[]; annual_sky=[]; annual_osky=[]
    for month in range(1,13):
        item=monthly[month]; temps=item['rows']; all_temps.extend(temps)
        daily=list(item['daily'].values())
        mean=sum(temps)/len(temps) if temps else 0.0
        highs=[max(x) for x in daily if x]; lows=[min(x) for x in daily if x]
        mean_high=sum(highs)/len(highs) if highs else mean
        mean_low=sum(lows)/len(lows) if lows else mean
        hdd=cdd=0.0
        for values in daily:
            if not values: continue
            daily_mean=sum(values)/len(values)
            hdd+=max(0.0,18.0-daily_mean)
            cdd+=max(0.0,daily_mean-24.0)
        annual_hdd+=hdd; annual_cdd+=cdd
        ghi=item['ghi_Wh_m2']/1000.0; dni=item['dni_Wh_m2']/1000.0; dhi=item['dhi_Wh_m2']/1000.0
        annual_ghi+=ghi; annual_dni+=dni; annual_dhi+=dhi
        annual_rh+=item['rh_pct']; annual_dew+=item['dew_C']; annual_hir+=item['hir_W_m2']
        annual_wind+=item['wind_m_s']; annual_sky+=item['total_sky_tenths']; annual_osky+=item['opaque_sky_tenths']
        pairs=item['wind_dir_deg']
        if pairs:
            sx=sum(math.sin(math.radians(d))*max(s,0.1) for d,s in pairs)
            sy=sum(math.cos(math.radians(d))*max(s,0.1) for d,s in pairs)
            prevailing=(math.degrees(math.atan2(sx,sy))+360.0)%360.0
        else: prevailing=0.0
        avg=lambda xs: sum(xs)/len(xs) if xs else 0.0
        profiles.append({
            'month':month,'mean_C':round(mean,1),'mean_high_C':round(mean_high,1),'mean_low_C':round(mean_low,1),
            'mean_dew_point_C':round(avg(item['dew_C']),1),'mean_relative_humidity_pct':round(avg(item['rh_pct']),1),
            'mean_wind_speed_m_s':round(avg(item['wind_m_s']),2),'prevailing_wind_direction_deg':round(prevailing,1),
            'global_horizontal_irradiation_kWh_m2':round(ghi,1),'direct_normal_irradiation_kWh_m2':round(dni,1),
            'diffuse_horizontal_irradiation_kWh_m2':round(dhi,1),'mean_horizontal_infrared_W_m2':round(avg(item['hir_W_m2']),1),
            'mean_total_sky_cover_tenths':round(avg(item['total_sky_tenths']),2),
            'mean_opaque_sky_cover_tenths':round(avg(item['opaque_sky_tenths']),2),
            'heating_degree_days_18C':round(hdd,1),'cooling_degree_days_24C':round(cdd,1),
            'source_type':'EPW_actual_hourly_data','data_quality':'A'
        })
    avg=lambda xs: sum(xs)/len(xs) if xs else 0.0
    annual_mean=sum(all_temps)/len(all_temps) if all_temps else 0.0
    return {
        'source_type':'EPW_actual_hourly_data','data_quality':'A','confidence':0.95,
        'basis':['registered_EPW_hourly_observations'],
        'annual_mean_temperature_C':round(annual_mean,2),
        'heating_degree_days_estimate':round(annual_hdd,1),'heating_degree_days_18C':round(annual_hdd,1),
        'cooling_degree_days_estimate':round(annual_cdd,1),'cooling_degree_days_24C':round(annual_cdd,1),
        'annual_solar_irradiation_kWh_m2_estimate':round(annual_ghi,1),
        'annual_global_horizontal_irradiation_kWh_m2':round(annual_ghi,1),
        'annual_direct_normal_irradiation_kWh_m2':round(annual_dni,1),
        'annual_diffuse_horizontal_irradiation_kWh_m2':round(annual_dhi,1),
        'annual_mean_relative_humidity_pct':round(avg(annual_rh),1),
        'annual_mean_dew_point_C':round(avg(annual_dew),1),
        'annual_mean_wind_speed_m_s':round(avg(annual_wind),2),
        'annual_mean_horizontal_infrared_W_m2':round(avg(annual_hir),1),
        'annual_mean_total_sky_cover_tenths':round(avg(annual_sky),2),
        'annual_mean_opaque_sky_cover_tenths':round(avg(annual_osky),2),
        'monthly_temperature_estimates':profiles,'monthly_epw_observations':profiles,
        'epw_path':str(epw_path),'epw_metadata':metadata,
        'notice':'A-level weather data read directly from the registered EPW hourly file. Heating/cooling loads and PV remain calculated results, not measured weather data.'
    }

def climate_estimate(lat, lon, climate=None, city=None, country=None):
    """Return a transparent planning climate estimate.

    Priority: registered city override -> registered climate class -> guarded
    latitude fallback. The fallback never forces cooling to zero solely because
    latitude exceeds 31 degrees.
    """
    a = abs(_f(lat))
    city_key = _normalise_city(city)
    climate_key = str(climate or "").strip().lower()

    if city_key in _CITY_CLIMATE_OVERRIDES:
        mean_t, hdd, cdd, solar = _CITY_CLIMATE_OVERRIDES[city_key]
        basis = ["registered_city_profile", city_key]
        confidence = 0.68
        zone = climate_key or "registered_city"
    elif climate_key in _CLIMATE_PROFILES:
        mean_t, hdd, cdd, solar = _CLIMATE_PROFILES[climate_key]
        basis = ["registered_climate_profile", climate_key]
        confidence = 0.62
        zone = climate_key
    else:
        zone = 'tropical' if a < 15 else 'subtropical' if a < 30 else 'temperate' if a < 45 else 'cool' if a < 60 else 'cold'
        mean_t = 27.5 - 0.28 * a
        hdd = max(0.0, (18.0 - mean_t) * 260.0)
        # Keep a modest non-zero summer allowance in temperate climates.
        cdd = max(40.0 if a < 55 else 0.0, (mean_t - 14.0) * 180.0)
        solar = max(850.0, 1850.0 - abs(a - 25.0) * 16.0)
        basis = ["latitude_guarded_fallback"]
        confidence = 0.42

    return {
        'source_type': 'registered_climate_planning_estimate',
        'confidence': confidence,
        'basis': basis,
        'climate_zone': zone,
        'annual_mean_temperature_C': round(mean_t, 2),
        'heating_degree_days_estimate': round(max(0.0, hdd), 1),
        'cooling_degree_days_estimate': round(max(0.0, cdd), 1),
        'annual_solar_irradiation_kWh_m2_estimate': round(max(0.0, solar), 1),
        'monthly_temperature_estimates': _monthly_temperature_estimates(mean_t, zone, lat, city),
        'notice': 'Planning estimate only; monthly temperatures are estimated monthly mean / mean high / mean low values. Use local EPW/weather data for formal calculation.',
    }

def _name(p,f):
    c=p.get('common') or {}; i=c.get('project_identity') or {}; return c.get('project_name') or i.get('project_name') or f

def _method(p):
    c=p.get('common') or {}; d=c.get('detailed_configuration') or {}; s=d.get('building_system','')
    if s=='azras':
        a=d.get('azras') or {}; return 'AZRAS_'+'_'.join(str(a.get(k,'')) for k in ('core_structure','infill_structure','infill_method') if a.get(k))
    g=d.get('general') or {}; return '_'.join(str(g.get(k,'')) for k in ('structure','method') if g.get(k)) or str(c.get('construction_method_name_ja') or 'structure')

def _positive(*values):
    for value in values:
        number = _f(value, 0.0)
        if number > 0:
            return number
    return 0.0

def _area(p,key):
    c=p.get('common') or {}; b=c.get('building') or {}
    mapped={'scale_gfa_m2':'gross_floor_area_m2','roof_area_m2':'roof_area_m2'}[key]
    return _positive(c.get(key), b.get(mapped))

def _recursive_find_text(obj, keys):
    if isinstance(obj, dict):
        for key in keys:
            value=obj.get(key)
            if value not in (None, ''):
                return str(value)
        for value in obj.values():
            found=_recursive_find_text(value, keys)
            if found:
                return found
    elif isinstance(obj, list):
        for value in obj:
            found=_recursive_find_text(value, keys)
            if found:
                return found
    return ''

def _recursive_find(obj, keys):
    if isinstance(obj, dict):
        for key in keys:
            if key in obj:
                value=_f(obj.get(key), float('nan'))
                if not math.isnan(value):
                    return value
        for value in obj.values():
            found=_recursive_find(value, keys)
            if found is not None:
                return found
    elif isinstance(obj, list):
        for value in obj:
            found=_recursive_find(value, keys)
            if found is not None:
                return found
    return None

def build_case(base,loc,base_file):
    # PATCH 376: regional/batch energy cases are downstream of Module 2.
    # Retained stale output is audit history only and must not seed a new
    # location result. Legacy outputs without explicit stale metadata remain
    # compatible through module_output_is_current().
    if not module_output_is_current(base, "module2"):
        raise ValueError(
            "Module 2 result is stale. Recalculate and save Module 2 before regional/batch analysis."
        )
    p=copy.deepcopy(base); c=p.setdefault('common',{}); ident=c.setdefault('project_identity',{}); l=c.setdefault('location',{}); r=c.setdefault('renewable_energy',{})
    city=str(loc.get('city') or loc.get('name') or ''); country=str(loc.get('country') or ''); lat=_f(loc.get('latitude')); lon=_f(loc.get('longitude'))
    c.update({'country':country,'city':city,'latitude':lat,'longitude':lon,'address':str(loc.get('address') or city)})
    l.update({'country':country,'city':city,'address':str(loc.get('address') or city),'latitude':lat,'longitude':lon,'coordinate_source':'batch_location_analysis'})
    epw_path=str(loc.get('epw_path') or loc.get('weather_file') or '').strip()
    if not epw_path or not Path(epw_path).exists():
        raise FileNotFoundError(f'登録EPWが見つかりません: {city} / {epw_path or "未設定"}')
    climate=_epw_climate(epw_path)
    climate['climate_zone']=str(loc.get('climate') or '')
    climate['climate_name_ja']=str(loc.get('climate_name_ja') or '')
    climate['climate_name_en']=str(loc.get('climate_name_en') or '')
    climate['weather_station']=str(loc.get('epw_station') or (climate.get('epw_metadata') or {}).get('city') or Path(epw_path).stem)
    c['batch_climate_estimate']=climate
    c['weather_file']=epw_path
    l['weather_file']=epw_path
    roof=_area(p,'roof_area_m2'); util=_f(r.get('roof_utilization_percent'),80); pv_area=roof*util/100; solar=_f(climate['annual_solar_irradiation_kWh_m2_estimate']); eff=_f(r.get('panel_efficiency_percent'),22)/100; pcs=_f(r.get('pcs_efficiency_percent'),97)/100; pv=pv_area*solar*eff*pcs
    r.update({'pv_area_m2':round(pv_area,3),'annual_generation_kWh':round(pv,1),'calculation_status':'registered_epw_weather','calculation_source_type':'EPW','calculation_confidence':0.95,'calculation_basis':['roof_area','roof_utilization_percent','EPW_global_horizontal_radiation','panel_efficiency','pcs_efficiency']})
    gfa=_area(p,'scale_gfa_m2')
    # Preserve the building-specific thermal performance already calculated by Module 2.
    # Regional loads are scaled by regional degree-days, rather than being rebuilt from
    # floor area alone. This keeps the effect of insulation, HVAC COP and concrete thermal
    # capacity contained in the base calculation.
    base_heating=_recursive_find(base.get('module_outputs') or {}, ('heating_load_kWh_per_year','annual_heating_energy_kWh','heating_energy_kWh_per_year'))
    base_cooling=_recursive_find(base.get('module_outputs') or {}, ('cooling_load_kWh_per_year','annual_cooling_energy_kWh','cooling_energy_kWh_per_year'))
    base_lat=_f((base.get('common') or {}).get('latitude'), _f(((base.get('common') or {}).get('location') or {}).get('latitude')))
    base_common = base.get('common') or {}
    base_city = base_common.get('city') or ((base_common.get('location') or {}).get('city'))
    base_country = base_common.get('country') or ((base_common.get('location') or {}).get('country'))
    base_climate_key = base_common.get('climate') or (base_common.get('batch_climate_estimate') or {}).get('climate_zone')
    base_weather=str(base_common.get('weather_file') or ((base_common.get('location') or {}).get('weather_file') or '') or _recursive_find_text(base.get('module_outputs') or {}, ('weather_file','epw_path','weather_path'))).strip()
    if base_weather and Path(base_weather).exists():
        base_climate=_epw_climate(base_weather)
    else:
        base_climate=climate_estimate(base_lat, _f(base_common.get('longitude'), _f((base_common.get('location') or {}).get('longitude'))), base_climate_key, base_city, base_country)
    target_hdd=_f(climate['heating_degree_days_estimate']); target_cdd=_f(climate['cooling_degree_days_estimate'])
    base_hdd=_f(base_climate['heating_degree_days_estimate']); base_cdd=_f(base_climate['cooling_degree_days_estimate'])

    # The same building envelope is used in every region. Module 2 already includes
    # the drawing-derived wall/roof/floor/window U-values, HVAC COP and the RC wall/
    # slab dynamic heat capacity. Regional comparison changes climate only.
    # Guarded ratios prevent an unrecognised base city from producing a near-zero
    # denominator and unrealistically inflating Sapporo/London/New York loads.
    heating_ratio = target_hdd / max(base_hdd, 250.0)
    cooling_ratio = target_cdd / max(base_cdd, 120.0)
    heating_ratio = min(max(heating_ratio, 0.0), 5.0)
    cooling_ratio = min(max(cooling_ratio, 0.0), 6.0)
    if base_heating is not None and base_heating >= 0:
        heating=base_heating * heating_ratio
    else:
        heating=gfa*target_hdd*.012
    if base_cooling is not None and base_cooling >= 0:
        cooling=base_cooling * cooling_ratio
    else:
        cooling=gfa*target_cdd*.010

    module2 = (base.get('module_outputs') or {}).get('module2') or {}
    settings = module2.get('settings') or {}
    performance = {
        'same_envelope_all_regions': True,
        'drawing_derived_specifications_preserved': True,
        'heating_cop': settings.get('heating_cop'),
        'cooling_cop': settings.get('cooling_cop'),
        'window_shgc': settings.get('window_shgc'),
        'active_fraction_wall': settings.get('active_fraction_wall'),
        'active_fraction_slab': settings.get('active_fraction_slab'),
        'effective_dynamic_heat_capacity_MJ_per_K': module2.get('effective_dynamic_heat_capacity_MJ_per_K'),
    }
    analysis={'source_type':'base_module2_registered_epw_scaling_v3','confidence':0.72,'basis':['base_project_module2_loads','registered_epw_degree_days','same_drawing_derived_envelope_all_regions','module2_rc_dynamic_heat_capacity','regional_solar_irradiation'],'gross_floor_area_m2':gfa,'base_climate_city':base_city,'base_heating_degree_days':round(base_hdd,1),'base_cooling_degree_days':round(base_cdd,1),'heating_scaling_ratio':round(heating_ratio,4),'cooling_scaling_ratio':round(cooling_ratio,4),'building_performance_preserved':performance,'estimated_annual_heating_energy_kWh':round(max(0.0,heating),1),'estimated_annual_cooling_energy_kWh':round(max(0.0,cooling),1),'estimated_annual_pv_generation_kWh':round(max(0.0,pv),1)}
    p['batch_location_analysis']={'version':'1.0','generated_at':_now(),'base_project_file':base_file,'base_project_name':_name(base,Path(base_file).stem),'structure_label':_method(base),'location':{'name':str(loc.get('name') or city),'country':country,'city':city,'latitude':lat,'longitude':lon},'climate_estimate':climate,'location_analysis':analysis,'notice_ja':'月別気温・日射量・地域度日は登録EPW実データを使用しています。冷暖房値は同一建物のModule 2結果をEPW度日で地域補正した比較値です。'}
    new_name=f"{_name(p,Path(base_file).stem)} - {city or loc.get('name','')}"; c['project_name']=new_name; ident['project_name']=new_name; p['updated_at']=_now(); p['last_saved_by']='AZRAS Batch Location Analysis'; return p

def run_batch(base_paths,locations,output_dir):
    out=Path(output_dir); out.mkdir(parents=True,exist_ok=True); rows=[]; files=[]; errors=[]
    for bi,bp in enumerate(base_paths,1):
        bp=Path(bp)
        try: base=json.loads(bp.read_text(encoding='utf-8'))
        except Exception as e: errors.append({'base_project':str(bp),'error':str(e)}); continue
        structure=_method(base); base_name=_name(base,bp.stem); folder=out/f"{bi:02d}_{_slug(structure or base_name)}"; folder.mkdir(exist_ok=True)
        for li,loc in enumerate(locations,1):
            try:
                case=build_case(base,loc,str(bp)); city=str(loc.get('city') or loc.get('name') or f'Location_{li}'); target=folder/f"{li:02d}_{_slug(city)}_{_slug(structure or base_name)}.json"; target.write_text(json.dumps(case,ensure_ascii=False,indent=2),encoding='utf-8'); files.append(str(target))
                b=case['batch_location_analysis']; cl=b['climate_estimate']; an=b['location_analysis']; rows.append({'base_project':base_name,'structure':structure,'location':city,'country':loc.get('country',''),'latitude':loc.get('latitude',''),'longitude':loc.get('longitude',''),'climate_zone':cl.get('climate_zone',''),'annual_mean_temperature_C':cl.get('annual_mean_temperature_C',''),'heating_degree_days_estimate':cl.get('heating_degree_days_estimate',''),'cooling_degree_days_estimate':cl.get('cooling_degree_days_estimate',''),'annual_solar_irradiation_kWh_m2_estimate':cl.get('annual_solar_irradiation_kWh_m2_estimate',''),'estimated_annual_heating_energy_kWh':an.get('estimated_annual_heating_energy_kWh',''),'estimated_annual_cooling_energy_kWh':an.get('estimated_annual_cooling_energy_kWh',''),'estimated_annual_pv_generation_kWh':an.get('estimated_annual_pv_generation_kWh',''),'source_type':'estimated_monthly_temperature_profile','confidence':an.get('confidence',''),'json_file':str(target)})
            except Exception as e: errors.append({'base_project':str(bp),'location':loc,'error':str(e)})
    csv_path=out/'Integrated_Comparison_Batch_Manifest.csv'
    if rows:
        with csv_path.open('w',newline='',encoding='utf-8-sig') as f: w=csv.DictWriter(f,fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    manifest={'version':'1.0','generated_at':_now(),'base_project_count':len(base_paths),'location_count':len(locations),'expected_case_count':len(base_paths)*len(locations),'generated_case_count':len(files),'generated_files':files,'comparison_csv':str(csv_path),'errors':errors,'notice_ja':'本バッチの気温・日射・度日は各都市に登録されたEPW実データを使用します。EPW未登録都市は計算しません。'}
    (out/'Batch_Analysis_Manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8'); return manifest
