"""Compiled missing local channels refresh when the interface is created."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'houdini/python3.11libs'))
import hou
import dsh_hou_helpers as h
import dsh_bridge as b

source = 'addpoint(0,{0,0,0}); for(int i=0;i<chi("count");i++) addpoint(0,set(i+1,0,0));'
with h._execution_owner('dependency-test', 'setup'):
    root = h.tab_create('/obj', 'geo', '__spare_dependency')
    try:
        for mode in ('scan', 'spec', 'expression', 'interface_first'):
            n = h.tab_create(root, 'attribwrangle', mode)
            if mode == 'interface_first':
                h.create_spare_parms(n, spec=[{'type':'int','name':'count','default':3}])
            h.set_parms(n, {'class':'detail', 'snippet':source})
            if mode == 'expression':
                # Preserve code expression/keys rather than baking evaluated VEX.
                n.parm('snippet').setExpression(repr(source), hou.exprLanguage.Python)
            old_keys = n.parm('snippet').keyframes()
            h.cook_node(n, force=True)
            assert len(n.geometry().points()) == (4 if mode == 'interface_first' else 1)
            if mode != 'interface_first':
                result = (h.create_spare_parms(n, defaults={'count':3}) if mode == 'scan'
                          else h.create_spare_parms(n, spec=[{'type':'int','name':'count','default':3}]))
                assert result['refreshed_code_parm'] == 'snippet', result
            assert n.parm('snippet').evalAsString() == source
            assert n.parm('snippet').keyframes() == old_keys
            for value, expected in ((3,4),(5,6),(0,1),(3,4)):
                h.set_parm(n, 'count', value)
                assert h.cook_node(n, force=True)['ok']
                assert len(n.geometry().points()) == expected, (mode,value)
            # Appending unrelated controls preserves existing animated controls.
            n.parm('count').setExpression('3+$F', hou.exprLanguage.Hscript)
            keys = n.parm('count').keyframes()
            h.create_spare_parms(n, spec=[{'type':'float','name':'unrelated','default':2}])
            assert n.parm('count').keyframes() == keys
        locked = h.tab_create(root, 'attribwrangle', 'locked')
        h.set_parms(locked, {'class':'detail', 'snippet':source})
        locked.parm('snippet').lock(True)
        before = locked.parmTemplateGroup().asDialogScript()
        try:
            h.create_spare_parms(locked, defaults={'count':3})
            raise AssertionError('locked source must reject before template changes')
        except ValueError:
            assert locked.parmTemplateGroup().asDialogScript() == before
        locked.parm('snippet').lock(False)
        # Refresh failure restores the prior interface, even outside an exec undo.
        restore = h._restore_parameters
        attempts = []
        def fail_once(snapshots):
            errors = restore(snapshots)
            attempts.append(1)
            return errors + (['injected refresh failure'] if len(attempts)==1 else [])
        try:
            h._restore_parameters = fail_once
            try:
                h.create_spare_parms(locked, defaults={'count':3})
                raise AssertionError('refresh failure expected')
            except RuntimeError as error:
                assert 'injected refresh failure' in str(error)
                assert locked.parm('count') is None
                assert locked.parm('snippet').evalAsString() == source
        finally:
            h._restore_parameters = restore
        for options, message in (({'read_only':True}, 'read-only'),
                                 ({'owner_session':'foreign'}, 'ownership guard')):
            env = b.run_code(f'create_spare_parms({locked.path()!r},defaults={{"count":3}})', **options)
            assert not env['ok'] and message in env['error'], env
            assert locked.parm('count') is None
    finally:
        h.delete_node(root)
print('spare dependency refresh/source animation/controls/locks/restoration/ownership passed on '+hou.applicationVersionString())
