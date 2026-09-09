"""Managed profile removes secondary vision tools instead of reinstalling them."""
from pathlib import Path
import json,sys,tempfile
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'houdini/python3.11libs'))
import dsh_profile_sync as sync
requirements=sync.load_requirements()
assert [p['name'] for p in requirements['plugins']]==['dsh-houdini']
assert '@anionex/dsh-vision-toolkit' in requirements['removePlugins']
with tempfile.TemporaryDirectory() as raw:
 home=Path(raw);profile=home/'profiles/web';profile.mkdir(parents=True)
 manifest={'dependencies':{'dsh-houdini':f'link:{ROOT.as_posix()}'},'dsh':{'profile':{'bundles':['dsh-houdini']}}}
 package=profile/'node_modules/dsh-houdini';package.mkdir(parents=True)
 (package/'package.json').write_text(json.dumps({'name':'dsh-houdini','version':'0.1.0'}))
 def save():(profile/'package.json').write_text(json.dumps(manifest))
 save();status=sync.inspect_profile(requirements,home=home);assert status['ok'],status
 for name in requirements['removePlugins']:
  manifest['dependencies'][name]='old';manifest['dsh']['profile']['bundles'].append(name)
 save();status=sync.inspect_profile(requirements,home=home)
 assert not status['ok'];assert sync.required_remove_names(requirements,status)==requirements['removePlugins']
 assert sync.required_install_specs(requirements,status)==[]
 calls=[]
 def run(prefix,args,**kwargs):
  calls.append(args);assert args[:4]==['plugin','--profile','web','remove']
  for name in args[4:]:manifest['dependencies'].pop(name);manifest['dsh']['profile']['bundles'].remove(name)
  save();return 'removed'
 sync._run_plugin_command=run
 print(sync.sync_profile_plugins(['dsh'],home=home))
 assert len(calls)==1 and sync.inspect_profile(requirements,home=home)['ok']
print('profile removal is explicit and idempotent')
