"""Current profile requires exactly the project plugin and installs it idempotently."""
from pathlib import Path
import json,sys,tempfile
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'houdini/python3.11libs'))
import dsh_profile_sync as sync
requirements=sync.load_requirements()
assert [p['name'] for p in requirements['plugins']]==['dsh-houdini']
with tempfile.TemporaryDirectory() as raw:
 home=Path(raw);profile=home/'profiles/web';profile.mkdir(parents=True)
 manifest={'dependencies':{'dsh-houdini':f'link:{ROOT.as_posix()}'},'dsh':{'profile':{'bundles':['dsh-houdini']}}}
 package=profile/'node_modules/dsh-houdini';package.mkdir(parents=True)
 (package/'package.json').write_text(json.dumps({'name':'dsh-houdini','version':'0.1.0'}))
 def save():(profile/'package.json').write_text(json.dumps(manifest))
 save();status=sync.inspect_profile(requirements,home=home);assert status['ok'],status
 assert sync.required_install_specs(requirements,status)==[]
 calls=[]
 sync._run_plugin_command=lambda *args,**kwargs: calls.append(args) or 'unexpected'
 assert sync.sync_profile_plugins(['dsh'],home=home).startswith('profile plugins ok:')
 assert calls==[]
 manifest['dependencies'].pop('dsh-houdini');manifest['dsh']['profile']['bundles'].remove('dsh-houdini');save()
 status=sync.inspect_profile(requirements,home=home);assert not status['ok']
 assert sync.required_install_specs(requirements,status)==[str(ROOT)]
 def run(prefix,args,**kwargs):
  calls.append(args);assert args[:4]==['plugin','--profile','web','add']
  manifest['dependencies']['dsh-houdini']=f'link:{ROOT.as_posix()}'
  manifest['dsh']['profile']['bundles'].append('dsh-houdini');save();return 'added'
 sync._run_plugin_command=run
 print(sync.sync_profile_plugins(['dsh'],home=home))
 assert len(calls)==1 and sync.inspect_profile(requirements,home=home)['ok']
print('profile requirement is exact and idempotent')
