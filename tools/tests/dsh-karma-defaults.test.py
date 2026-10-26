"""Isolated H21/H22 Karma creation defaults and composed USD focus contract.

No live connection or source HIP. --render adds two small real Karma images
in a new OS temporary folder and verifies render_frame preserves artist DOF.
"""
from pathlib import Path
import json
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'houdini/python3.11libs'))
import hou
import dsh_bridge as bridge
import dsh_hou_helpers as h


def execute(code):
    result = bridge.run_code(code, owner_session='karma-defaults', owner_call='fixture')
    assert result['ok'], result
    return result.get('result')


stage = hou.node('/stage')
native = stage.createNode('karmarendersettings', 'native_artist_settings')
native_dof = native.evalParm('enabledof')
assert native_dof == 1
native.parm('enablemblur').set(False)
native_state = {p.name(): p.eval() for p in native.parms() if p.name() in ('enabledof', 'enablemblur', 'denoiser')}

created = execute("""normal=tab_create('/stage','karmarendersettings',name='general_asset')
artist=tab_create('/stage','karmarendersettings',name='explicit_dof',parms={'enabledof':True})
setup=tab_apply('/stage','lop_karma_setup')
__result__={'normal':normal.path(),'artist':artist.path(),'setup':setup}
""")
normal = hou.node(created['normal'])
artist = hou.node(created['artist'])
settings = next(hou.node(r['path']) for r in created['setup']['created'] if r['type'] == 'karmarendersettings')
rop = next(hou.node(r['path']) for r in created['setup']['created'] if r['type'] == 'usdrender_rop')
assert normal.evalParm('enabledof') == settings.evalParm('enabledof') == 0
assert artist.evalParm('enabledof') == 1
assert {p.name(): p.eval() for p in native.parms() if p.name() in native_state} == native_state
for node in (normal, settings):
    assert node.evalParm('enablemblur') == 1 and node.evalParm('denoiser') == 'off'

def dof(node):
    scene = node.stage()
    prim = scene.GetPrimAtPath(node.evalParm('primpath'))
    return prim.GetAttribute('karma:global:enable_dof').Get()

assert dof(native) is True and dof(artist) is True
assert dof(normal) is False and dof(settings) is False
info = h.node_info(stage, 'karmarendersettings', parm_filter='no_such_filter', limit=1)
assert any(p['name'] == 'enabledof' for p in info['operation_parameters']), info
assert not info['operation_parameters_missing'], info
assert any('existing settings and render_frame preserve' in note for note in info['usage_notes']), info

# An explicit later choice stays active; creation of another setup cannot reset
# existing settings, and the existing setup expressions keep their own target.
execute(f"set_parms({settings.path()!r},{{'enabledof':True}})\n"
        "tab_apply('/stage','lop_karma_setup')")
assert settings.evalParm('enabledof') == 1 and dof(settings) is True
assert rop.evalParm('rendersettings') == settings.evalParm('primpath')

if '--render' in sys.argv:
    output = Path(tempfile.mkdtemp(prefix='dsh-karma-focus-'))
    print('KARMA_FOCUS_DIR=' + str(output), flush=True)
    geo = h.tab_create('/obj', 'geo', name='focus_asset')
    shape = h.tab_create(geo, 'box', name='OUT', parms={'size':(0.8,0.8,0.15)})
    h.sop_set_output(shape)
    camera = h.tab_create('/obj', 'cam', name='focus_camera', parms={
        'tz':3, 'focus':0.25, 'fstop':0.5, 'focal':50, 'resx':128, 'resy':96})
    importer = h.tab_create(stage, 'sceneimport', name='focus_scene', parms={
        'objects':geo.path()+' '+camera.path(), 'forceobjects':geo.path()+' '+camera.path()})
    h.connect(importer, settings)
    h.set_parms(settings, {'camera':'/focus_camera', 'engine':'cpu',
                          'convergence_mode':'Path Traced', 'pathtracedsamples':16})
    h.set_parms(rop, {'husk_enable_headlight':1,'husk_headlight':'distant',
                     'override_res':'specific','res_user':(128,96)})
    images = []
    for enabled in (False, True):
        h.set_parms(settings, {'enabledof':enabled})
        before = (settings.evalParm('enabledof'), camera.evalParm('focus'), camera.evalParm('fstop'))
        scene = settings.stage()
        usd_camera = scene.GetPrimAtPath('/focus_camera')
        assert abs(usd_camera.GetAttribute('focusDistance').Get()-.25)<1e-6
        assert abs(usd_camera.GetAttribute('fStop').Get()-.5)<1e-6
        image = h.render_frame(rop, picture=str(output / ('dof_on.png' if enabled else 'dof_off.png')), timeout=90)
        assert image['fresh'] and image['file_bytes'] and not image['errors'], image
        assert (settings.evalParm('enabledof'), camera.evalParm('focus'), camera.evalParm('fstop')) == before
        assert dof(settings) is enabled
        images.append({'enabledof':enabled,'render':image,'pixels':h.render_check(image['output'])})
    (output/'evidence.json').write_text(json.dumps({'version':hou.applicationVersionString(),'images':images},indent=2),encoding='utf8')

print('Karma creation DOF defaults, explicit artist settings and composed USD passed on ' + hou.applicationVersionString(), flush=True)
