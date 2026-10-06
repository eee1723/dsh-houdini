"""Shared definition authority, atomic section restoration and independent forks.

Run only in fresh isolated H21/H22 hython. Native HOM creates adversarial fixture
assets; all operations under test run through the normal Bridge contracts.
"""
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'houdini/python3.11libs'))
import hou
import dsh_bridge as b
import dsh_hou_helpers as h
import dsh_hda_interfaces as interfaces


def run(code, ok=True, owner='definition-author'):
    result = b.run_code(code, owner_session=owner, owner_call='definition-ownership')
    assert result['ok'] is ok, result.get('error')
    return result


def sections(definition):
    return {name: bytes(section.binaryContents()) for name, section in definition.sections().items()}


with tempfile.TemporaryDirectory(prefix='dsh-definition-ownership-') as temporary:
    folder = Path(temporary)
    owned_file = folder / 'owned.hda'
    path = run("source=tab_create('/obj','subnet','owned_tool')\n"
               f"__result__=hda_create(source,'contract::owned_definition::1.0',hda_file={str(owned_file)!r})")['result']['node']
    run(f'hda_set_section({path!r},"PythonModule","VALUE = 1\\n")')
    node = hou.node(path)
    definition = node.type().definition()
    before = owned_file.read_bytes()
    before_sections = sections(definition)
    foreign = hou.node('/obj').createNode(node.type().name(), 'user_instance')
    for call in (f'hda_set_section({path!r},"PythonModule","VALUE = 2\\n")',
                 f'hda_patch_section({path!r},"PythonModule","VALUE = 1","VALUE = 2")'):
        result = run(call, False)
        assert 'ownership' in result['error']
        assert owned_file.read_bytes() == before and sections(definition) == before_sections
    foreign.destroy()

    # Every section write, including an added section, restores the entire
    # original library/loaded sections/root channels after a write failure.
    original = h._write_hda_section
    def fail_after_write(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError('injected section post-write failure')
    h._write_hda_section = fail_after_write
    try:
        for section in ('PythonModule', 'new_payload'):
            failed = run(f'hda_set_section({path!r},{section!r},"VALUE = 9\\n")', False)
            assert 'injected section' in failed['error'] and 'restored' in str(failed)
            assert owned_file.read_bytes() == before and sections(definition) == before_sections
        failed = run(f'hda_patch_section({path!r},"PythonModule","VALUE = 1","VALUE = 9")', False)
        assert owned_file.read_bytes() == before and sections(definition) == before_sections
    finally:
        h._write_hda_section = original
    run(f'hda_patch_section({path!r},"PythonModule","VALUE = 1","VALUE = 2")')
    assert definition.sections()['PythonModule'].contents() == 'VALUE = 2\n'
    run(f'hda_set_section({path!r},"PythonModule","VALUE = 3\\n")')

    # A new owned instance is not authority over a pre-existing disk library,
    # even when no other/foreign instances survive.
    external_file = folder / 'external.hda'
    raw = hou.node('/obj').createNode('subnet', 'external_fixture')
    raw = raw.createDigitalAsset(name='contract::external_definition::1.0', hda_file_name=str(external_file))
    raw.type().definition().addSection('PythonModule', 'VALUE = 4\n')
    raw.destroy()
    own_instance = run("__result__=tab_create('/obj','contract::external_definition::1.0','own_instance').path()")['result']
    external_before = external_file.read_bytes()
    for call in (f'hda_set_section({own_instance!r},"PythonModule","VALUE = 5\\n")',
                 f'hda_patch_section({own_instance!r},"PythonModule","VALUE = 4","VALUE = 5")',
                 f'hda_set_interface({own_instance!r},spec=[],dry_run=True)',
                 f'hda_edit({own_instance!r},"save",dry_run=True)'):
        failed = run(call, False)
        assert 'definition ownership guard' in failed['error'], failed['error']
        assert external_file.read_bytes() == external_before
    run(f'hda_set_section({own_instance!r},"PythonModule","VALUE = 5\\n",allow_foreign="User explicitly authorized this external type/library")')
    assert 'definition ownership guard' in run(f'hda_set_section({own_instance!r},"PythonModule","VALUE = 6\\n")', False)['error']

    # Disk or loaded-definition changes outside authoring invalidate the
    # recorded creation; a one-call edit does not adopt that new source.
    definition.addSection('external_edit', 'user changed source')
    assert 'changed outside' in run(f'hda_set_section({path!r},"PythonModule","VALUE = 7\\n")', False)['error']
    run(f'hda_set_section({path!r},"PythonModule","VALUE = 7\\n",allow_foreign="User explicitly authorized this changed library")')
    assert 'changed outside' in run(f'hda_set_section({path!r},"PythonModule","VALUE = 8\\n")', False)['error']

    # replace is always rejected, including fully owned instances. Existing
    # target files are never appended to merely because a new name is free.
    replacement = run("__result__=tab_create('/obj','subnet','replacement').path()")['result']
    unchanged = external_file.read_bytes()
    failed = run(f'hda_create({replacement!r},"contract::external_definition::1.0",hda_file={str(external_file)!r},replace=True)', False)
    assert 'not supported' in failed['error']
    failed = run(f'hda_create({replacement!r},"contract::new_in_foreign_file::1.0",hda_file={str(external_file)!r})', False)
    assert 'already exists' in failed['error']
    assert external_file.read_bytes() == unchanged and hou.node(own_instance) is not None

    # Fork reads a foreign source without claiming it, installs an independent
    # exact type, and never creates/migrates an instance or replaces a definition.
    source = hou.node(own_instance)
    original_identity = source.sessionId()
    original_type = source.type()
    fork_file = folder / 'fork.hda'
    fork = run(f'__result__=hda_fork({own_instance!r},"contract::forked_definition::1.0",{str(fork_file)!r},description="独立工具")', owner='fork-author')['result']
    assert fork['source_instances_migrated'] == 0 and fork['instances_created'] == 0
    assert source.sessionId() == original_identity and source.type() == original_type
    assert external_file.read_bytes() == unchanged
    assert not hou.nodeType(hou.objNodeTypeCategory(),fork['type']).instances()
    fork_instance = run(f"__result__=tab_create('/obj',{fork['type']!r},'fork_instance').path()", owner='fork-author')['result']
    run(f'hda_set_section({fork_instance!r},"PythonModule","VALUE = 10\\n")', owner='fork-author')
    assert external_file.read_bytes() == unchanged
    assert hou.node(fork_instance).type().definition().sections()['PythonModule'].contents() == 'VALUE = 10\n'
    # Reusing either the source type or a previously written target is rejected.
    for name, target in ((source.type().name(), folder/'unused.hda'),
                         ('contract::new_fork::1.0', external_file)):
        failed = run(f'hda_fork({own_instance!r},{name!r},{str(target)!r})', False, owner='fork-author')
        assert external_file.read_bytes() == unchanged

    # A failure after copy/install reclaims only the newly created library/type.
    original_register = interfaces.register_created_definition
    def fail_registration(definition):
        raise RuntimeError('injected fork registration failure')
    interfaces.register_created_definition = fail_registration
    failed_file = folder/'failed_fork.hda'
    try:
        failed = run(f'hda_fork({own_instance!r},"contract::failed_fork::1.0",{str(failed_file)!r})', False, owner='fork-author')
    finally:
        interfaces.register_created_definition = original_register
    assert 'injected fork registration' in failed['error']
    assert not failed_file.exists()
    assert 'contract::failed_fork::1.0' not in hou.objNodeTypeCategory().nodeTypes()
    assert source.sessionId() == original_identity and external_file.read_bytes() == unchanged

    # Vendor assets stay readable/forkable, but exemptions never authorize
    # writing any files inside the Houdini installation.
    system_target = str(Path(hou.text.expandString('$HFS'))/'otls/dsh_should_never_exist.hda')
    failed = run(f'hda_create({replacement!r},"contract::system_write::1.0",hda_file={system_target!r})', False)
    assert '$HFS' in failed['error'] and not Path(system_target).exists()

print('PASS definition/library ownership, section rollback, replace rejection and independent fork ' + hou.applicationVersionString())
