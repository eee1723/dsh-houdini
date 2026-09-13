"""Execute the public help example without implementation discovery."""
import ast,inspect,sys,tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'houdini/python3.11libs'))
import hou
import dsh_bridge as b
owner='public-help-test'
def run(code):
 r=b.run_code(code,owner_session=owner)
 assert r['ok'],r.get('error')
 return r.get('result')
help=run("__result__=verb_help('hda_set_interface')")
doc=help['doc']
example=doc[doc.index('    layout = '):doc.index('\n普通Null') if '\n普通Null' in doc else doc.index('\n    普通Null')]
import textwrap
tree=ast.parse(textwrap.dedent(example))
layout=ast.literal_eval(tree.body[0].value)
with tempfile.TemporaryDirectory(prefix='dsh-help-') as tmp:
 run("g=tab_create('/obj','geo','help_fixture'); n=tab_create(g,'null','controls')")
 n=hou.node('/obj/help_fixture/controls')
 before=n.parmTemplateGroup().asDialogScript()
 run(f'__result__=create_spare_parms({n.path()!r},layout={layout!r},dry_run=True)')
 assert n.parmTemplateGroup().asDialogScript()==before
 run(f'__result__=create_spare_parms({n.path()!r},layout={layout!r})')
 assert n.evalParm('width')==1 and n.evalParm('mode')==0
 assert n.parmTuple('tint').eval()==(.6,.3,.1)
 run("s=tab_create('/obj/help_fixture','subnet','asset')")
 run(f"__result__=hda_create('/obj/help_fixture/asset','help_fixture::1.0',hda_file={str(Path(tmp)/'help.hda')!r})")
 run(f"__result__=hda_set_interface('/obj/help_fixture/asset',layout={layout!r},dry_run=True)")
 run(f"__result__=hda_set_interface('/obj/help_fixture/asset',layout={layout!r})")
 assert hou.node('/obj/help_fixture/asset').evalParm('width')==1
 bad=[{'type':'float','name':'bad','components':3,'default':1}]
 r=b.run_code(f'create_spare_parms({n.path()!r},layout={bad!r},dry_run=True)',owner_session=owner)
 assert not r['ok'] and n.parm('bad') is None
 hou.node('/obj/help_fixture').destroy()
print('PASS public UI help example '+hou.applicationVersionString())
