"""Read-only native-SOP recipes and bounded parameter-state test planning.

Plans are inspectable inputs to existing governed verbs, not node creation or
quality certificates. The recipe never owns or adopts its input nodes.
"""
import itertools
import math
import re


def _name(value,label):
    if not isinstance(value,str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*',value):
        raise ValueError(label+' must be a direct child/parameter identifier')
    return value


def _number(value,label):
    if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value):
        raise ValueError(label+' must be a finite number')
    return float(value)


def sop_recipe(kind,spec=None):
    schemas={
        'hinge':{'name':'joint','inputs':['body','accessory'],'controller':'CTRL','parameter':'angle','origin':[0,0,0],'axis':[0,1,0]},
        'slider':{'name':'move','inputs':['body','accessory'],'controller':'CTRL','parameter':'travel','origin':[0,0,0],'axis':[1,0,0]},
        'repeat':{'name':'ribs','inputs':['rib_source'],'controller':'CTRL','parameter':'count','origin':[0,0,0],'axis':[1,0,0],'spacing':0.01},
        'sweep_tube':{'name':'tube','inputs':['centerline'],'controller':'CTRL','radius':0.002},
        'profile_shell':{'name':'shell','inputs':['profile'],'controller':'CTRL','thickness':0.001},
        'guided_slider':{'name':'move','inputs':['body','accessory'],'guide':'rail','controller':'CTRL','parameter':'travel',
                         'travel_min':0.0,'travel_max':0.03,'clearance':0.001,'origin':[0,0,0],'axis':[1,0,0]},
        'surface_attach':{'name':'mounted','inputs':['detail_source'],'receiver':'body','receiver_group':'mount_surface',
                          'controller':'CTRL','origin':[0,0,0],'tangent':[1,0,0],'max_distance':0.01},
        'gusset':{'name':'rib','controller':'CTRL','length':0.01,'height':0.006,'thickness':0.001},
        'fastener':{'name':'bolt','controller':'CTRL','shaft_radius':0.002,'shaft_length':0.008,
                    'head_radius':0.004,'head_height':0.003,'segments':24}}
    if kind=='catalog':
        return {'recipes':['hinge','slider','guided_slider','surface_attach','gusset','fastener','repeat','sweep_tube','profile_shell'],
                'structural_schemas':{k:schemas[k] for k in ('guided_slider','surface_attach','gusset','fastener')},
                'examples':schemas,
                'schema':{'name':'unique prefix','inputs':['existing direct source child'],
                          'controller':'CTRL (hinge/slider/repeat)','parameter':'angle/offset/count',
                          'origin':[0,0,0],'axis':[0,1,0],'spacing':1.0,'thickness':0.1,'radius':0.1},
                'scope':'read-only specs for build_module; origin is shared attachment position, source geometry must be modeled relative to its local pivot. Numeric scalar or {parm:name} origins/dimensions read a single controller. No implicit local/world conversion.'}
    if kind not in schemas:raise ValueError('unknown recipe; use catalog')
    if spec is None:return {'kind':kind,'example':schemas[kind],'scope':'example schema only, lengths in scene units; quantities may reference {parm:name} on the single CTRL'}
    if kind in ('guided_slider','surface_attach','gusset','fastener'):
        return _structural_recipe(kind,spec)
    allowed={'name','inputs','controller'}|({'parameter','origin','axis','spacing'} if kind=='repeat' else
        {'parameter','origin','axis'} if kind in ('hinge','slider') else {'radius'} if kind=='sweep_tube' else {'thickness'})
    if not isinstance(spec,dict) or set(spec)-allowed:raise ValueError('unsupported recipe spec fields')
    if kind not in ('hinge','slider','repeat','sweep_tube','profile_shell'):raise ValueError('unknown recipe; use catalog')
    name=_name(spec.get('name'),'name');inputs=spec.get('inputs')
    if not isinstance(inputs,list) or not 1<=len(inputs)<=16:raise ValueError('inputs needs 1..16 direct child names')
    for value in inputs:_name(value,'input')
    ctrl=_name(spec.get('controller','CTRL'),'controller')
    def expr(value,label):
        if isinstance(value,dict) and set(value)=={'parm'}:
            return f'ch("../{ctrl}/{_name(value["parm"],label)}")'
        return str(_number(value,label))
    nodes=[{'name':name+'_SOURCE','type':'merge','inputs':inputs}]
    if kind in ('hinge','slider','repeat'):
        parameter=_name(spec.get('parameter'),'parameter')
        origin=spec.get('origin',[0,0,0]);axis=spec.get('axis',[0,1,0])
        if not isinstance(origin,list) or len(origin)!=3 or not isinstance(axis,list) or len(axis)!=3:raise ValueError('origin/axis require three components')
        axis=[_number(v,'axis') for v in axis];length=math.sqrt(sum(v*v for v in axis))
        if length<=1e-9:raise ValueError('axis must be nonzero')
        axis=[v/length for v in axis]
        vec='set('+','.join(map(str,axis))+')';point='set('+','.join(expr(v,'origin') for v in origin)+')'
        channel=f'ch("../{ctrl}/{parameter}")'
        snippet=f'vector origin={point}; vector axis={vec};\n'
        if kind=='repeat':
            spacing=expr(spec.get('spacing',1),'spacing')
            snippet+=f'float requested={channel}; int count=int(requested); if(count!=requested || count<1 || count>256) {{ error("repeat count must be integer 1..256"); return; }}\n'
            snippet+=f'for(int i=0;i<count;i++){{ int p=addpoint(0,origin+axis*({spacing})*i); setpointattrib(0,"id",p,i); }}'
        else:
            position=f'origin+axis*({channel})' if kind=='slider' else 'origin'
            snippet+=f'int p=addpoint(0,{position}); setpointattrib(0,"id",p,0);\n'
            if kind=='hinge':snippet+=f'vector4 q=quaternion(radians({channel}),axis); setpointattrib(0,"orient",p,q);'
        nodes.extend([{'name':name+'_FRAME','type':'attribwrangle','parms':{'class':'detail','snippet':snippet}},
                      {'name':name+'_PLACE','type':'copytopoints::2.0','inputs':[name+'_SOURCE',name+'_FRAME'],
                       'parms':{'pack':0,'transform':1}}])
        final=name+'_PLACE'
    else:
        if len(inputs)!=1:raise ValueError('sweep_tube/profile_shell require one explicit profile or centerline input')
        dim='radius' if kind=='sweep_tube' else 'thickness'
        size=expr(spec.get(dim),dim)
        if not isinstance(spec.get(dim),dict) and float(size)<=0:raise ValueError(dim+' must be positive')
        parms={'surfaceshape':'tube','endcaptype':'single','radius':size,'cols':24} if kind=='sweep_tube' else {
            'dist':size,'outputfront':1,'outputback':1,'outputside':1}
        nodes.append({'name':name+'_FORM','type':'sweep::2.0' if kind=='sweep_tube' else 'polyextrude::2.0',
                      'inputs':[name+'_SOURCE'],'parms':parms})
        final=name+'_FORM'
    output='OUT_'+name.upper()
    nodes.append({'name':output,'type':'null','inputs':[final]})
    if set(inputs)&{n['name'] for n in nodes}:raise ValueError('recipe input collides with generated node names')
    return {'kind':kind,'nodes':nodes,'output':output,'required_outputs':[name+'_SOURCE',output],
            'frame_output':name+'_FRAME' if kind in ('hinge','slider','repeat') else None,
            'scope':'read-only construction proposal, no geometry evaluated; ordinary editable SOPs, no HDA/Python SOP',
            'checks':['Verify local origin/axis and shared control references on actual inputs.',
                      'Check final member identity, attachments and required control states; Copy together is not proof of connection.',
                      'Tube requires an open smooth centerline; shell requires a closed planar polygon sheet, not an existing solid.'],
            'next_action':'Inspect specs then build_module(parent, nodes, output, required_outputs=...). Keep attachment sources in the same placement branch. Test prototype before repetition.'}


def _structural_recipe(kind,spec):
    fields={'guided_slider':{'inputs','guide','parameter','travel_min','travel_max','clearance','origin','axis'},
            'surface_attach':{'inputs','receiver','receiver_group','origin','tangent','max_distance'},
            'gusset':{'length','height','thickness'},
            'fastener':{'shaft_radius','shaft_length','head_radius','head_height','segments'}}
    if not isinstance(spec,dict) or set(spec)-({'name','controller'}|fields[kind]):raise ValueError('unsupported '+kind+' spec fields')
    name=_name(spec.get('name'),'name');ctrl=_name(spec.get('controller','CTRL'),'controller')
    def expr(value,label):
        if isinstance(value,dict) and set(value)=={'parm'}:return f'ch("../{ctrl}/{_name(value["parm"],label)}")'
        return str(_number(value,label))
    def vector(value,label):
        if not isinstance(value,list) or len(value)!=3:raise ValueError(label+' needs three components')
        return 'set('+','.join(expr(v,label) for v in value)+')'
    def positive(field):
        value=spec.get(field)
        if not isinstance(value,dict) and _number(value,field)<=0:raise ValueError(field+' must be positive')
        return expr(value,field)
    nodes=[];inputs=[]
    if kind in ('guided_slider','surface_attach'):
        inputs=spec.get('inputs')
        if not isinstance(inputs,list) or not 1<=len(inputs)<=16:raise ValueError('inputs needs 1..16 source child names')
        for value in inputs:_name(value,'input')
        nodes.append({'name':name+'_SOURCE','type':'merge','inputs':inputs})
        origin=vector(spec.get('origin',[0,0,0]),'origin')
        if kind=='guided_slider':
            guide=_name(spec.get('guide'),'guide');parameter=_name(spec.get('parameter'),'parameter')
            axis=vector(spec.get('axis',[1,0,0]),'axis')
            low=expr(spec.get('travel_min'),'travel_min');high=expr(spec.get('travel_max'),'travel_max');clear=expr(spec.get('clearance',0),'clearance')
            code=f'vector origin={origin}; vector axis={axis}; float low={low}, high={high}, clearance={clear}; float u=ch("../{ctrl}/{parameter}");\n'
            code+='if(length(axis)<1e-8 || clearance<0 || high<=low || u<low || u>high) { error("invalid guide/parameter domain"); return; } axis=normalize(axis);\n'
            code+='float amin=1e30,amax=-1e30,rmin=1e30,rmax=-1e30;\n'
            code+='for(int input=1;input<=2;input++){ if(nprimitives(input)==0 || npoints(input)==0 || npoints(input)>100000) { error("guide/source point budget"); return; } for(int pr=0;pr<nprimitives(input);pr++) if(primintrinsic(input,"typename",pr)!="Poly") { error("guided_slider requires polygon source and guide"); return; } }\n'
            code+='for(int i=0;i<npoints(1);i++){ vector P=point(1,"P",i); float v=dot(P,axis); amin=min(amin,v);amax=max(amax,v); }\n'
            code+='for(int i=0;i<npoints(2);i++){ vector P=point(2,"P",i); float v=dot(P-origin,axis);rmin=min(rmin,v);rmax=max(rmax,v); }\n'
            code+='float eps=max(1e-9,abs(rmax-rmin)*1e-6); if(amax<=amin || rmax-rmin+eps < amax-amin+2*clearance+high-low) { error("requested travel exceeds actual guide support span"); return; }\n'
            code+='int p=addpoint(0,origin+axis*(rmin+clearance-amin+u-low));setpointattrib(0,"id",p,0);'
            frame_inputs=[None,name+'_SOURCE',guide]
            notes=['Travel is displacement from its declared minimum, not world X.',
                   'Actual source/attachment and guide point projections determine support span; valid bounds do not prove groove fit/contact.']
        else:
            receiver=_name(spec.get('receiver'),'receiver');group=_name(spec.get('receiver_group'),'receiver_group')
            tangent=vector(spec.get('tangent',[1,0,0]),'tangent');distance=positive('max_distance')
            code=f'vector origin={origin}; int pr=-1; vector uv; if(nprimitives(1)==0 || nprimitives(1)>100000) {{error("receiver surface budget");return;}} float d=xyzdist(1,"{group}",origin,pr,uv);\n'
            code+=f'if(pr<0 || d>{distance}) {{ error("attachment surface missing or outside explicit reach"); return; }}\n'
            code+=f'vector normal=normalize(prim_normal(1,pr,uv.x,uv.y));vector tangent={tangent}; tangent-=dot(tangent,normal)*normal;\n'
            code+='if(length(normal)<1e-8 || length(tangent)<1e-8) { error("attachment frame is degenerate"); return; } tangent=normalize(tangent);\n'
            code+='matrix3 frame=set(tangent,normal,cross(tangent,normal)); vector hit=primuv(1,"P",pr,uv); int p=addpoint(0,hit);setpointattrib(0,"orient",p,quaternion(frame));setpointattrib(0,"id",p,0);'
            frame_inputs=[None,receiver]
            notes=['Source foot must lie in local Y=0 and rise along +Y. Receiver group is an actual surface.',
                   'Projection anchors one point; verify the complete foot and neighbors in the final output. No bounding-box attachment certificate.']
        nodes.extend([{'name':name+'_FRAME','type':'attribwrangle','inputs':frame_inputs,'parms':{'class':'detail','snippet':code}},
                      {'name':name+'_PLACE','type':'copytopoints::2.0','inputs':[name+'_SOURCE',name+'_FRAME'],'parms':{'pack':0,'transform':1}}])
        final=name+'_PLACE'
    elif kind=='gusset':
        length=positive('length');height=positive('height');thickness=positive('thickness')
        code=f'float l={length},h={height},t={thickness};if(min(l,min(h,t))<=0) {{ error("positive gusset dimensions required"); return; }}\n'
        code+='int a=addpoint(0,set(0,0,-t/2));int b=addpoint(0,set(l,0,-t/2));int c=addpoint(0,set(0,h,-t/2));addprim(0,"poly",a,b,c);'
        nodes.extend([{'name':name+'_PROFILE','type':'attribwrangle','parms':{'class':'detail','snippet':code}},
                      {'name':name+'_FORM','type':'polyextrude::2.0','inputs':[name+'_PROFILE'],
                       'parms':{'dist':thickness,'outputfront':1,'outputback':1,'outputside':1}},
                      {'name':name+'_FOOT','type':'attribwrangle','inputs':[name+'_FORM'],
                       'parms':{'class':'point','snippet':f'if(abs(@P.y)<1e-9) setpointgroup(0,"{name}_foot",@ptnum,1);'}}])
        final=name+'_FOOT';notes=['Triangular closed rib prism, local foot Y=0; attach to a real surface then verify all foot vertices.',
                               'Dimensions are scene lengths; convert source dimensions to meters first.']
    else:
        radius=positive('shaft_radius');length=positive('shaft_length');head_r=positive('head_radius');head_h=positive('head_height')
        segments=spec.get('segments',24)
        if type(segments) is not int or not 8<=segments<=128:raise ValueError('segments must be 8..128')
        for suffix,r,h,y in [('SHAFT',radius,length,f'({length})/2'),('HEAD',head_r,head_h,f'({length})+({head_h})/2')]:
            nodes.append({'name':name+'_'+suffix,'type':'tube','parms':{'type':'poly','cap':1,'orient':'y',
                          'rad1':r,'rad2':r,'height':h,'ty':y,'cols':segments}})
        nodes.append({'name':name+'_ASSEMBLY','type':'merge','inputs':[name+'_SHAFT',name+'_HEAD']})
        final=name+'_ASSEMBLY';notes=['Separate closed shaft/head sharing an exact mating plane, local mounting foot Y=0.',
                                   'No thread/torque/manufacturing certification; cut appropriate receiver holes and verify final fit.']
    output='OUT_'+name.upper();nodes.append({'name':output,'type':'null','inputs':[final]})
    names={n['name'] for n in nodes}
    if names&set(inputs) or spec.get('guide') in names or spec.get('receiver') in names:raise ValueError('recipe source/receiver collides with generated names')
    return {'kind':kind,'nodes':nodes,'output':output,'required_outputs':[output],
            'frame_output':name+'_FRAME' if kind in ('guided_slider','surface_attach') else None,
            'checks':notes,'scope':'read-only native-SOP proposal; graph, physical dimensions and final interfaces require execution evidence'}


def control_test_plan(controller,parameters,max_cases=16,domain=None):
    import dsh_hou_helpers as h
    from dsh_quality_contracts import _control_parameter,domain_checks,validate_domain
    ctrl=h._resolve(controller)
    if not isinstance(parameters,dict) or not 1<=len(parameters)<=8:raise ValueError('parameters needs 1..8 named scalar level lists')
    if type(max_cases) is not int or not 1<=max_cases<=16:raise ValueError('max_cases must be 1..16')
    if domain is not None:
        validate_domain(domain)
        names={c['left'] for c in domain}|{c['right'] for c in domain if isinstance(c['right'],str)}
        names.update(n for c in domain if isinstance(c['right'],dict) for n in c['right']['terms'])
        if any(_control_parameter(ctrl,n).keyframes() for n in names):
            raise ValueError('domain planning requires independent unkeyed controls; use explicit test cases for expressions/animation')
        if any(row['status']=='fail' for row in domain_checks(ctrl,domain)):
            raise ValueError('baseline outside declared domain; resolve it before planning perturbations')
    names=sorted(parameters);levels=[];baseline={}
    for name in names:
        _name(name,'control')
        parm=_control_parameter(ctrl,name);baseline[name]=float(parm.eval())
        values=parameters[name]
        if not isinstance(values,list) or not 2<=len(values)<=8:raise ValueError('each parameter needs 2..8 explicit levels including boundaries/intermediate states')
        clean=[]
        for value in values:
            _number(value,'level')
            if parm.parmTemplate().type().name()=='Int' and type(value) is not int:raise ValueError('integer control requires integer levels')
            if parm.parmTemplate().type().name()=='Toggle' and (type(value) is not int or value not in (0,1)):
                raise ValueError('toggle control requires levels 0 and 1')
            if value not in clean:clean.append(value)
        if len(clean)<2:raise ValueError('levels must include two distinct values')
        levels.append(clean)
    combinations=math.prod(map(len,levels))
    if combinations>4096:raise ValueError('candidate grid exceeds 4096; split independent controls')
    candidates=[];excluded=[]
    for values in itertools.product(*levels):
        row=dict(zip(names,values))
        if domain and any(r['status']=='fail' for r in domain_checks(ctrl,domain,row)):
            excluded.append(row);continue
        candidates.append(row)
    if not candidates:raise ValueError('no candidate satisfies the declared domain')
    def tokens(row):
        return {('level',n,row[n]) for n in names}|{('pair',a,row[a],b,row[b]) for a,b in itertools.combinations(names,2)}
    required=set().union(*(tokens(row) for row in candidates))
    covered=tokens(baseline)&required;selected=[]
    remaining=[r for r in candidates if any(r[n]!=baseline[n] for n in names)]
    while remaining and len(selected)<max_cases:
        best=max(remaining,key=lambda row:len(tokens(row)-covered))
        if not tokens(best)-covered:break
        selected.append(best);covered.update(tokens(best));remaining.remove(best)
    cases=[{'id':'state_'+str(i+1),'values':{n:v for n,v in row.items() if v!=baseline[n]},'expectations':[]}
           for i,row in enumerate(selected)]
    missing=sorted(required-covered,key=str)
    return {'controller':ctrl.path(),'baseline':baseline,'tests':cases,'candidate_count':len(candidates),
            'excluded_count':len(excluded),'excluded_sample':excluded[:8],
            'coverage':{'status':'complete_pairwise' if not missing else 'partial_pairwise',
                        'required_tokens':len(required),'covered_tokens':len(required&covered),'missing':missing[:32],
                        'missing_count':len(missing),'all_combinations_tested':False},
            'scope':'planning only; zero writes/cooks; pairwise requested levels, not continuous motion or quality proof',
            'next_action':'Fill each case with independent expected responses/invariants and state-specific interfaces, then test_controls. Empty expectations cannot be executed as accepted tests. Include extra intermediate motion states when collisions are possible.'}
