"""Fresh H21/H22 note ownership, Raw Gate and explicit presentation recovery."""
from __future__ import annotations
from pathlib import Path
import importlib
import json
import sys
import tempfile
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'houdini/python3.11libs'))
import hou
import dsh_bridge as bridge
import dsh_network_notes as notes
from dsh_code_analysis import CodeAnalysis
from dsh_network_layout import Rect, overlaps

session = 'notes-' + uuid.uuid4().hex
undo_enabled = bool(hou.undos.areEnabled())


def call(code, owner=session, **kwargs):
    return bridge.run_code(code, owner_session=owner, owner_call=uuid.uuid4().hex, **kwargs)


def ok(code, **kwargs):
    result = call(code, **kwargs)
    assert result['ok'], result
    return result


def state(note):
    row = notes._state(note)
    return {k: v for k, v in row.items() if k != 'owner'}


parent = ok("__result__=tab_create('/obj','geo',name='notes_fixture').path()")['result']
p = hou.node(parent)
source = ok(f"__result__=tab_create({parent!r},'box',name='source').path()")['result']
before = {'frame': hou.frame(), 'selection': tuple(hou.selectedNodes()),
          'position': tuple(hou.node(source).position()), 'flags': (hou.node(source).isDisplayFlagSet(), hou.node(source).isRenderFlagSet())}
empty = ok(f'__result__=network_notes({parent!r})')
assert empty['result']['notes'] == [] and empty['transaction']['status'] == 'no_scene_change', empty
blocked = call(f'network_notes({parent!r})', read_only=True)
assert not blocked['ok'] and 'read-only' in blocked['error'], blocked

created = ok(f"__result__=network_notes({parent!r},[{{'name':'README','text':'先调控制，再替换曲线。'}},{{'name':'INPUTS','text':'替换输入源'}}])")
assert created['result']['created'] == ['README', 'INPUTS'], created
assert created['execution']['impact']['attempted'] is False, created
a, b = p.findStickyNote('README'), p.findStickyNote('INPUTS')
def rectangle(note):
    x, y = note.position(); w, h = note.size()
    return Rect(x, y, x + w, y + h)
assert not overlaps(rectangle(a), rectangle(b))
assert not overlaps(rectangle(a), rectangle(hou.node(source)))
assert all(notes.note_provenance(note, session)['status'] == 'owned_current_session' for note in (a, b))
assert {'frame': hou.frame(), 'selection': tuple(hou.selectedNodes()),
        'position': tuple(hou.node(source).position()), 'flags': (hou.node(source).isDisplayFlagSet(), hou.node(source).isRenderFlagSet())} == before
identity = int(a.sessionId())
updated = ok(f"__result__=network_notes({parent!r},[{{'name':'README','text':'中文使用入口与依赖','position':[-12,4],'size':[8,4],'color':[0.2,0.3,0.25]}}])")
assert updated['result']['updated'] == ['README'] and int(a.sessionId()) == identity, updated
unchanged = ok(f"__result__=network_notes({parent!r},[{{'name':'README','text':'中文使用入口与依赖'}}])")
assert unchanged['result']['unchanged'] == ['README'] and unchanged['transaction']['status'] == 'no_scene_change', unchanged
assert unchanged['result']['scene_writes'] == 0

# Entire batch preflights before updating an earlier valid target.
original = state(a)
invalid = call(f"network_notes({parent!r},[{{'name':'README','text':'must not change'}},{{'name':'invalid/name','text':'x'}}])")
assert not invalid['ok'] and invalid['verbs'][0]['summary']['scene_writes'] == 0, invalid
assert state(a) == original
foreign = p.createStickyNote('user_note'); foreign.setText('User content')
rejected = call(f"network_notes({parent!r},[{{'name':'user_note','text':'unauthorized'}}])")
assert not rejected['ok'] and 'ownership guard' in rejected['error'], rejected
assert foreign.text() == 'User content'
other_session = call(f"network_notes({parent!r},[{{'name':'README','text':'other session'}}])", owner='other-task')
assert not other_session['ok'] and a.text() == original['text'], other_session
ok(f"network_notes({parent!r},[{{'name':'user_note','text':'authorized update'}}],allow_foreign='User explicitly requested this note update')")
assert notes.note_provenance(foreign, session)['status'] == 'foreign'

# Deleting an owned containing node cannot bypass independent note authority.
delete_parent = ok("__result__=tab_create('/obj','geo',name='notes_delete_parent').path()")['result']
dp = hou.node(delete_parent)
ok(f"network_notes({delete_parent!r},[{{'name':'owned','text':'Owned note'}}])")
owned_id = int(dp.findStickyNote('owned').sessionId())
foreign_child = dp.createStickyNote('foreign'); foreign_child.setText('Artist note')
foreign_id = int(foreign_child.sessionId())
delete_denied = call(f'delete_node({delete_parent!r})')
assert not delete_denied['ok'] and 'foreign Sticky Note' in delete_denied['error'], delete_denied
assert hou.node(delete_parent) == dp and foreign_child.text() == 'Artist note'
parent_undo = call(f"delete_node({delete_parent!r},allow_foreign='User explicitly requested this container including its notes')\nraise RuntimeError('after container deletion')")
assert not parent_undo['ok'] and parent_undo['rollback']['network_notes']['ok'], parent_undo
dp = hou.node(delete_parent)
assert dp is not None and dp.findStickyNote('owned').text() == 'Owned note'
assert notes.note_provenance(dp.findStickyNote('owned'), session)['status'] == 'owned_current_session'
assert notes.note_provenance(dp.findStickyNote('foreign'), session)['status'] == 'foreign'
ok(f"delete_node({delete_parent!r},allow_foreign='User explicitly requested this container including its notes')")
assert hou.node(delete_parent) is None
assert not any(key[2] in (owned_id, foreign_id) for key in notes._OWNED_NOTES)

# Neither parent nor same native name can adopt a replacement or copied note.
b.destroy(); replacement = p.createStickyNote('INPUTS'); replacement.setText('replacement')
refused = call(f"network_notes({parent!r},[{{'name':'INPUTS','text':'must refuse'}}])")
assert not refused['ok'] and replacement.text() == 'replacement', refused
copied_note = p.copyItems((a,))[0]
copied_name = copied_note.name()
assert notes.note_provenance(copied_note, session)['status'] == 'foreign'
copy_refused = call(f"network_notes({parent!r},[{{'name':{copied_name!r},'text':'must refuse copied note'}}])")
assert not copy_refused['ok'] and copied_note.text() == a.text(), copy_refused
importlib.reload(notes)
assert notes.note_provenance(a, session)['status'] == 'owned_current_session'

# Native Undo removes a new parent and its note; absence restores an empty baseline.
new_parent_failure = call("p=tab_create('/obj','geo',name='notes_new_parent')\nnetwork_notes(p,[{'name':'README','text':'new asset'}])\nraise RuntimeError('after new parent')")
assert not new_parent_failure['ok'] and new_parent_failure['rollback']['network_notes']['ok'], new_parent_failure
if undo_enabled: assert hou.node('/obj/notes_new_parent') is None

# With native Undo explicitly disabled, restore note presentation but keep the
# broader scene transaction unverified and expose any recreated note identities.
with hou.undos.disabler():
    disabled = call(f"network_notes({parent!r},[{{'name':'README','text':'transient disabled'}},{{'name':'DISABLED_NEW','text':'temp'}}])\nnetwork_notes({parent!r},remove=['README'])\nraise RuntimeError('disabled undo')")
assert not disabled['ok'] and not disabled['rollback']['supported'], disabled
assert disabled['rollback']['network_notes']['ok'] and disabled['rollback']['network_notes']['identity_remaps'], disabled
assert disabled['transaction']['status'] == 'recovery_unverified', disabled
a = p.findStickyNote('README')
assert a.text() == original['text'] and p.findStickyNote('DISABLED_NEW') is None
assert notes.note_provenance(a, session)['status'] == 'owned_current_session'
original = state(a); identity = int(a.sessionId())

# A note already inside a box requires a supported membership recovery scope.
box = p.createNetworkBox('artist_group'); box.addItem(foreign)
boxed = call(f"network_notes({parent!r},remove=['user_note'],allow_foreign='User requested this note')")
assert not boxed['ok'] and 'inside a Network Box' in boxed['error'], boxed
assert foreign.parentNetworkBox() == box
box.removeItem(foreign)

service = p.createNode('subnet', 'service_fixture'); service.setUserData('dsh_houdini_owner', 'render_view_v2')
service_note = service.createStickyNote('service_note'); service_note.setText('service')
for code in (f"network_notes({service.path()!r},[{{'name':'new','text':'x'}}])",
             f"network_notes({service.path()!r},remove=['service_note'],allow_foreign='even explicit service change')"):
    response = call(code)
    assert not response['ok'] and 'render service' in response['error'], response
assert service_note.text() == 'service'

# Covered aliases cannot be bypassed by allow_raw. Python lookalikes stay generic.
raw_cases = [
    f"hou.node({parent!r}).createStickyNote('RAW')",
    f"n=hou.node({parent!r}).findStickyNote('README'); n.setText('RAW')",
    f"n=hou.node({parent!r}).findStickyNote('README'); alias=n; write=alias.setText; write('RAW')",
    f"n=hou.node({parent!r}).findStickyNote('README'); getattr(n,'setColor')(hou.Color((1,0,0)))",
    f"n=hou.node({parent!r}).stickyNotes()[0]; n.setPosition(hou.Vector2(0,0))",
    f"rows=hou.node({parent!r}).stickyNotes(); alias=rows; n=alias[0]; n.resize(hou.Vector2(1,1))",
    f"for n in hou.node({parent!r}).stickyNotes(): n.setText('RAW')",
    f"[n.setText('RAW') for n in hou.node({parent!r}).stickyNotes()]",
    f"hou.StickyNote.setText(hou.node({parent!r}).findStickyNote('README'),'RAW')",
    f"rows=list(hou.node({parent!r}).stickyNotes()); rows[0].resize(hou.Vector2(1,1))",
    f"rows=tuple(hou.node({parent!r}).stickyNotes()); rows[0].setText('RAW')",
    f"rows=hou.node({parent!r}).stickyNotes()[:]; rows[0].setText('RAW')",
    f"rows=tuple(list(hou.node({parent!r}).stickyNotes()))[1:]; alias=rows[:]; alias[0].resize(hou.Vector2(1,1))",
    f"find=hou.node({parent!r}).findStickyNote; alias=find; n=alias('README'); n.setText('RAW')",
    f"get_notes=hou.node({parent!r}).stickyNotes; alias=get_notes; rows=list(alias())[:]; rows[0].resize(hou.Vector2(1,1))",
    f"find=getattr(hou.node({parent!r}),'findStickyNote'); n=find('README'); setter=n.setText; setter('RAW')",
]
for code in raw_cases:
    assert any(row['verb'] == 'network_notes' for row in CodeAnalysis(code).raw_usage['coveredMutations']), code
    response = call(code, allow_raw='raw operations requested')
    assert not response['ok'] and response['rawUsage']['gateOutcome'] == 'blocked', response
    assert any(row['verb'] == 'network_notes' for row in response['rawUsage']['coveredMutations']), response
    readonly = call(code, read_only=True)
    assert not readonly['ok'] and readonly['rawUsage']['gateOutcome'] == 'read_only_blocked', readonly
assert not CodeAnalysis('class Label:\n def setText(self,text): pass\nx=Label();x.setText("text")').raw_usage['coveredMutations']
assert not CodeAnalysis('class Image:\n def resize(self,size): pass\nx=Image();x.resize((1,1))').raw_usage['coveredMutations']
assert not CodeAnalysis("n=hou.node('/obj/p').item('unknown'); n.setText('text')").raw_usage['coveredMutations']

# Inject failure after one target changed; local compensation keeps the original ID.
old_set = notes._set_value
def fail_second(note, field, value):
    if note.name() == 'FAIL' and field == 'text': raise RuntimeError('injected second note setter failure')
    return old_set(note, field, value)
notes._set_value = fail_second
try:
    failed = call(f"network_notes({parent!r},[{{'name':'README','text':'transient'}},{{'name':'FAIL','text':'fail'}}])")
finally: notes._set_value = old_set
assert not failed['ok'] and failed['verbs'][0]['summary']['restored'] is True, failed
assert state(a) == original and p.findStickyNote('FAIL') is None

# A later script failure compensates the first-touch baseline across multiple verbs.
rolled = call(f"network_notes({parent!r},[{{'name':'README','text':'transient'}},{{'name':'TX_NEW','text':'temp'}}])\nnetwork_notes({parent!r},[{{'name':'README','text':'transient 2'}}])\nraise RuntimeError('after notes')")
assert not rolled['ok'] and rolled['rollback']['network_notes']['ok'], rolled
assert state(a) == original and p.findStickyNote('TX_NEW') is None
assert (rolled['rollback']['supported'] and rolled['rollback']['applied']) if undo_enabled else not rolled['rollback']['supported'], rolled
removed = call(f"network_notes({parent!r},remove=['README'])\nraise RuntimeError('after remove')")
assert not removed['ok'] and removed['rollback']['network_notes']['ok'], removed
a = p.findStickyNote('README')
assert a.text() == original['text'] and tuple(a.position()) == tuple(original['position'])
if undo_enabled:
    assert int(a.sessionId()) == identity and removed['transaction']['status'] == 'rolled_back', removed
else:
    assert removed['rollback']['network_notes']['identity_remaps'] and removed['transaction']['status'] == 'recovery_unverified', removed
assert notes.note_provenance(a, session)['status'] == 'owned_current_session'

# An observed restoration failure stays false, including a caught mutation.
old_restore = notes._restore
def fail_restore(snapshot):
    return {'ok': False, 'errors': ['injected restoration failure'], 'identity_remaps': []}
notes._restore = fail_restore
notes._set_value = fail_second
try:
    unresolved = call(f"try:\n network_notes({parent!r},[{{'name':'UNRESTORED','text':'created'}},{{'name':'FAIL','text':'fail'}}])\nexcept RuntimeError:\n pass\nnetwork_notes({parent!r},[{{'name':'MUST_NOT_DISPATCH','text':'x'}}])")
finally:
    notes._restore = old_restore; notes._set_value = old_set
assert not unresolved['ok'] and unresolved['verbs'][0]['summary']['restored'] is False, unresolved
assert unresolved['verbs'][-1]['summary']['dispatched'] is False, unresolved
assert not unresolved['rollback']['network_notes']['ok'] and 'Sticky Note rollback failed' in unresolved['rollback']['error'], unresolved
assert p.findStickyNote('MUST_NOT_DISPATCH') is None

ok(f"__result__=network_notes({parent!r},remove=['README'])")
assert p.findStickyNote('README') is None
print(json.dumps({'version': hou.applicationVersionString(), 'real_gui': hou.isUIAvailable(),
                  'note_create_update_list_remove': True, 'ownership_raw_gate': True,
                  'local_failure_compensation': True, 'script_failure_note_recovery': True,
                  'native_undo_verified': undo_enabled, 'failed_restoration_kept': True}))
