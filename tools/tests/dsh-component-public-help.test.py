"""Run the component_export example supplied by public verb_help in a disposable HIP."""
from pathlib import Path
import hashlib
import sys
import tempfile
import textwrap

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'houdini/python3.11libs'))
import hou
import dsh_bridge as bridge


def run(code):
    result = bridge.run_code(code, owner_session='component-help')
    assert result['ok'], result.get('error', result)
    return result.get('result')


with tempfile.TemporaryDirectory(prefix='dsh-component-help-') as directory:
    hou.hipFile.save(str(Path(directory) / 'assembly.hip'))
    help_query = bridge.run_code("__result__=verb_help('component_export')", owner_session='component-help',
                                 read_only=True)
    assert help_query['ok'], help_query.get('error', help_query)
    help_result = help_query['result']
    assert help_result['signature'] == '(node, filename, contract)'
    assert help_result['call_mode'] == 'exec'
    doc = help_result['doc']
    example = textwrap.dedent(doc.split('Example (houdini_exec code, with the Host-assigned HIP already named):\n', 1)[1]
                                .split('\n\nSame-build native archive', 1)[0])
    result = run(example)
    artifact = Path(result['file'])
    assert artifact == Path(directory) / 'help_part_r1.dshcomponent'
    assert result['sha256'] == hashlib.sha256(artifact.read_bytes()).hexdigest()
    assert result['contract'] == {'module_id': 'part', 'revision': 1, 'units': 'm', 'outputs': [0]}
    assert result['semantic_status'] == 'unverified'
    bad = Path(directory) / 'bad.dshcomponent'
    rejected = bridge.run_code(f"component_export('/obj/help_author/part',{str(bad)!r},"
                               "{'module_id':'part','revision':1,'units':'m'})", owner_session='component-help')
    assert not rejected['ok'] and not bad.exists()
print('PASS component public help and contract rejection ' + hou.applicationVersionString())
