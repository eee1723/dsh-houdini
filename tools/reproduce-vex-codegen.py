"""Compare repeated VEX instructions with a runtime loop in native new processes.

Default checks the loop. --form both additionally runs a potentially crashing
literal expansion in its own process. A fixed Houdini compiler may accept both;
the observed outcome is reported, never turned into a production admission rule.
No user HIP, plugin, renderer, model service or global setting is used.
"""
from pathlib import Path
import argparse
import json
import math
import subprocess
import tempfile
import time

from houdini_test_environment import isolated_environment, launch_directory, reexec_unpacked_test_cli

def sources(count, samples, forms):
    expanded = []
    for piece in range(count) if 'expanded' in forms else ():
        code = ['{int vertices[];']
        for sample in range(samples):
            u = sample / (samples - 1)
            pos = (piece * .15 + .02 * math.cos(8 * math.pi * u),
                   .3 * math.sin(8 * math.pi * u), 4 * u)
            code.append('append(vertices,addpoint(0,set(%g,%g,%g)));' % pos)
        code.append('addprim(0,"polyline",vertices);}')
        expanded.append(''.join(code))
    loop = f'''for(int piece=0;piece<{count};piece++){{
int vertices[];
for(int sample=0;sample<{samples};sample++){{
float u=float(sample)/({samples}-1);
vector pos=set(piece*.15+.02*cos(8*M_PI*u),.3*sin(8*M_PI*u),4*u);
append(vertices,addpoint(0,pos));
}}
addprim(0,"polyline",vertices);
}}'''
    return {'expanded': ''.join(expanded), 'loop': loop}

def run(executable, directory, code, timeout):
    directory.mkdir(parents=True)
    snippet = directory / 'paths.vfl'
    snippet.write_text(code, encoding='utf8')
    script = directory / 'native.py'
    script.write_text('''import sys,json
from pathlib import Path
import hou
print('IDENTITY='+json.dumps({'version':hou.applicationVersionString(),
 'dshModules':[n for n in sys.modules if n.startswith('dsh_')],
 'newHip':hou.hipFile.isNewFile(),'ui':hou.isUIAvailable()}),flush=True)
assert not any(n.startswith('dsh_') for n in sys.modules)
g=hou.node('/obj').createNode('geo','native_codegen')
w=g.createNode('attribwrangle','paths')
w.parm('class').set(0)
w.parm('snippet').set(Path(sys.argv[1]).read_text(encoding='utf8'))
print('SOURCE_BEGIN',flush=True)
geo=w.geometry()
print('SOURCE_COMPLETE='+json.dumps({'points':len(geo.points()),'primitives':len(geo.prims())}),flush=True)
s=g.createNode('sweep','formed')
s.setInput(0,w)
s.parm('surfaceshape').set('tube')
s.parm('radius').set(.02)
s.parm('cols').set(6)
a=g.createNode('attribwrangle','identity')
a.setInput(0,s)
a.parm('class').set(1)
a.parm('snippet').set('s@part="detail";v@Cd={.3,.5,.7};')
print('CONSUMER_BEGIN',flush=True)
geo=a.geometry()
assert geo and len(geo.prims())>0 and not a.errors(),a.errors()
assert set(geo.primStringAttribValues('part'))=={'detail'}
print('CONSUMER_COMPLETE='+json.dumps({'points':len(geo.points()),'primitives':len(geo.prims())}),flush=True)
print('BODY_COMPLETE',flush=True)
''', encoding='utf8')
    env = isolated_environment(directory, executable=executable)
    temp = directory / 'houdini_temp'
    temp.mkdir()
    env['HOUDINI_TEMP_DIR'] = str(temp)
    started = time.monotonic()
    timed_out = False
    try:
        proc = subprocess.run([str(executable), str(script), str(snippet)],
                              cwd=launch_directory(executable), env=env,
                              capture_output=True, text=True, encoding='utf8', errors='replace',
                              timeout=timeout, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        exit_code, stdout, stderr = proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired as error:
        timed_out, exit_code = True, None
        def text(value):
            return value.decode('utf8', errors='replace') if isinstance(value, bytes) else value or ''
        stdout, stderr = text(error.stdout), text(error.stderr)
    (directory / 'stdout.txt').write_text(stdout, encoding='utf8')
    (directory / 'stderr.txt').write_text(stderr, encoding='utf8')
    rows = [json.loads(line.split('=', 1)[1]) for line in stdout.splitlines() if line.startswith('IDENTITY=')]
    return {'directory':str(directory),'sourceChars':len(code),'identity':rows[-1] if rows else None,
            'seconds':round(time.monotonic()-started,3),'timeout':timed_out,'exitCode':exit_code,
            'exitHex':f'0x{exit_code & 0xffffffff:08X}' if exit_code is not None else None,
            'sourceComplete':'SOURCE_COMPLETE=' in stdout,'consumerComplete':'CONSUMER_COMPLETE=' in stdout,
            'bodyComplete':'BODY_COMPLETE' in stdout}

def main():
    reexec_unpacked_test_cli()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--hython', type=Path, required=True, action='append')
    parser.add_argument('--form', choices=('loop','expanded','both'), default='loop')
    parser.add_argument('--count', type=int, default=192)
    parser.add_argument('--samples', type=int, default=50)
    parser.add_argument('--timeout', type=int, default=90)
    parser.add_argument('--out-root', type=Path)
    args = parser.parse_args()
    if args.count<1 or args.samples<2 or args.timeout<1:
        parser.error('count>=1, samples>=2 and timeout>=1 are required for this nonempty diagnostic')
    forms = ('loop','expanded') if args.form=='both' else (args.form,)
    codes = sources(args.count, args.samples, forms)
    root = Path(tempfile.mkdtemp(prefix='dsh-vex-codegen-', dir=args.out_root)).resolve()
    report = {'scope':'Independent native diagnostic; not a safe code-size threshold or model quality evaluation',
              'count':args.count,'samples':args.samples,'cases':[]}
    for index, executable in enumerate(args.hython):
        executable = executable.resolve(strict=True)
        for form in forms:
            row = run(executable, root / f'installation-{index}-{form}', codes[form], args.timeout)
            row['form'] = form
            report['cases'].append(row)
            (root / 'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2), encoding='utf8')
            print(json.dumps(row, ensure_ascii=False), flush=True)
    print('REPORT='+str(root/'report.json'),flush=True)
    return 0 if all(r['bodyComplete'] and r['exitCode']==0 for r in report['cases']) else 1

if __name__=='__main__':
    raise SystemExit(main())
