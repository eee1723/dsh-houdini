"""Native registry discovery without loading, executing, cooking or adopting."""
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'houdini/python3.11libs'))
import hou
import dsh_bridge as bridge
import dsh_tool_catalog as catalog

def run(code, owner='catalog-author'):
    result = bridge.run_code(code, owner_session=owner, owner_call='catalog-fixture')
    assert result['ok'], result.get('error')
    return result['result']

with tempfile.TemporaryDirectory(prefix='dsh-tool-catalog-') as directory:
    path = str(Path(directory)/'sample.hda')
    run(f"n=tab_create('/obj','subnet',name='catalog_source'); __result__=hda_create(n,'catalog_test::sample::1.0',description='测试目录工具',hda_file={path!r})")
    rows = catalog.tool_catalog(query='catalog_test', kind='node_type', category='Object')
    assert rows['total'] == 1 and rows['entries'][0]['source'] == str(Path(path)), rows
    assert rows['entries'][0]['origin'] == 'external'
    before = tuple(n.path() for n in hou.node('/').allSubChildren())
    data = catalog.tool_inspect('node_type', 'catalog_test::sample::1.0', category='Object', include_code=True)
    assert data['definitions'][0]['current'] and data['definitions'][0]['library_file'] == str(Path(path)), data
    assert data['entry']['edit_permission'] == 'not_inferred_from_discovery'
    assert tuple(n.path() for n in hou.node('/').allSubChildren()) == before
    native = catalog.tool_inspect('node_type', 'geo', category='Object', include_code=True)
    assert native['entry']['implementation'] == 'native_or_compiled' and native['code_status'].endswith('unavailable')
    tool = hou.shelves.newTool(name='catalog_test_shelf', label='目录测试', file_path=(Path(directory)/'catalog.shelf').as_posix(), script='raise RuntimeError("must never execute")')
    shelf = catalog.tool_inspect('shelf', tool.name(), include_code=True, max_chars=256)
    assert 'must never execute' in shelf['code'] and shelf['language'] == 'Python'
    tool.destroy()
    panels = catalog.tool_catalog(kind='panel', limit=1)
    assert panels['total'] >= len(panels['entries'])
    states = catalog.tool_catalog(kind='viewer_state')
    if not hou.isUIAvailable():
        assert states['unavailable'] and states['entries'] == []
    all_rows = catalog.tool_catalog(kind='node_type', limit=1)
    assert all_rows['truncated'] and len(all_rows['entries']) == 1
    second = catalog.tool_catalog(kind='node_type', limit=1, offset=1)
    assert all_rows['entries'][0]['name'] != second['entries'][0]['name']
    try:
        catalog.tool_inspect('node_type', 'geo')
    except ValueError:
        pass
    else:
        raise AssertionError('ambiguous type must require category')
print('tool catalog: actual HDA/native/Shelf/Panel registries, source, bounded code, pagination and no scene writes passed')
