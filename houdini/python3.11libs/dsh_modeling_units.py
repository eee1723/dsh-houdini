"""Explicit source quantities -> canonical SI lengths, without changing HIP units."""
import math
import re

_UNITS={'m':(1.,1,'m'),'cm':(.01,1,'m'),'mm':(.001,1,'m'),'um':(.000001,1,'m'),
        'in':(.0254,1,'m'),'ft':(.3048,1,'m'),'m2':(1.,2,'m2'),'cm2':(.0001,2,'m2'),
        'mm2':(.000001,2,'m2'),'m3':(1.,3,'m3'),'cm3':(.000001,3,'m3'),'mm3':(1e-9,3,'m3'),
        'deg':(1.,0,'deg'),'rad':(180/math.pi,0,'deg'),'count':(1.,0,'count'),'ratio':(1.,0,'ratio')}


def modeling_dimensions(quantities, require_meter_scene=True):
    from dsh_context import unit_length_meters
    if type(require_meter_scene) is not bool:raise ValueError('require_meter_scene must be boolean')
    if not isinstance(quantities,dict) or not 1<=len(quantities)<=64:
        raise ValueError('quantities must be a dict with 1..64 named records, e.g. {"length":{"value":120,"unit":"mm"}}; consume canonical_values["length"]=0.12 for a meter-based scene, not the original 120')
    unit=unit_length_meters()
    if unit is None:raise ValueError('scene unit length unavailable; no guessed conversion')
    if require_meter_scene and not math.isclose(unit,1.,rel_tol=0,abs_tol=1e-12):
        raise ValueError('scene is not meter-based; preserve existing HIP units and explicitly use require_meter_scene=False for an adapter')
    rows={};canonical={};scene_values={};spec=[]
    for name,item in quantities.items():
        if not isinstance(name,str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*',name):raise ValueError('quantity name must be a parameter identifier')
        if not isinstance(item,dict) or set(item)-{'value','unit','min','max','source'}:raise ValueError('quantity supports value/unit/min/max/source')
        declared=item.get('unit')
        if not isinstance(declared,str) or declared not in _UNITS:raise ValueError('unsupported unit; use '+', '.join(_UNITS))
        factor,power,target=_UNITS[declared]
        try:scene_factor=unit**power
        except OverflowError:raise ValueError('scene unit exponent overflow') from None
        if scene_factor<=0 or not math.isfinite(scene_factor):raise ValueError('scene unit exponent is not representable')
        result={}
        for field in ('value','min','max'):
            if field not in item:
                if field=='value':raise ValueError('quantity value required')
                continue
            value=item[field]
            if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value):raise ValueError('quantity values must be finite scalar numbers')
            if declared=='count' and type(value) is not int:raise ValueError('count values must be integers')
            result[field]=value*factor
            if not math.isfinite(result[field]) or not math.isfinite(result[field]/scene_factor):raise ValueError('quantity conversion overflow')
        if result.get('min',-math.inf)>result.get('max',math.inf) or not result.get('min',-math.inf)<=result['value']<=result.get('max',math.inf):
            raise ValueError('quantity value/range inconsistent')
        source=item.get('source')
        if source is not None and (not isinstance(source,str) or not source.strip() or len(source)>1000):raise ValueError('source must be a short nonempty reference')
        canonical[name]=result['value'];scene_values[name]=result['value']/scene_factor
        rows[name]={'source':dict(item),'canonical_unit':target,'canonical':result,
                    'scene':{k:v/scene_factor for k,v in result.items()},'dimension_power':power}
        spec.append({'type':'int' if declared=='count' else 'float','name':name,
                     'label':name+' ('+target+')','default':int(result['value']) if declared=='count' else result['value'],
                     **{k:result[k] for k in ('min','max') if k in result}})
    return {'scene_unit_length_meters':unit,'canonical_values':canonical,'scene_values':scene_values,'quantities':rows,
            'controller_spec':spec if math.isclose(unit,1.,rel_tol=0,abs_tol=1e-12) else None,
            'scope':'read-only conversion, not source interpretation or geometry validation; canonical lengths are meters, angles degrees, counts unchanged. Existing HIP units are never modified.',
            'next_action':'Use canonical values for a meter-based asset; an existing nonmeter scene requires explicit scene_values adaptation. Verify actual final physical extents after construction.'}
