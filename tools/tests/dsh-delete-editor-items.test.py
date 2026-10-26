"""Native node deletion keeps editor-item authority and complete Undo scope.

Run in isolated H21/H22. GUI execution additionally verifies native Undo of
the whole Karma subtree, including exact Box/Sticky Note identities.
"""
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'houdini/python3.11libs'))
import hou
import dsh_bridge as bridge
import dsh_network_boxes as boxes
import dsh_network_notes as notes
import dsh_ownership as ownership

SESSION = 'delete-editor-items'

def call(code, owner=SESSION):
    return bridge.run_code(code,owner_session=owner,owner_call='delete-editor-fixture')

def ok(code):
    result=call(code)
    assert result['ok'],result
    return result.get('result')

def create(name):
    return ok(f"__result__=tab_create('/stage','karmarendersettings',name={name!r}).path()")

def baseline(node):
    networks=[node,*[child for child in node.allSubChildren() if child.isNetwork()]]
    return {
        'nodes':[(int(child.sessionId()),child.path()) for child in [node,*node.allSubChildren()]],
        'boxes':{int(parent.sessionId()):[boxes._state(box) for box in parent.networkBoxes()]
                 for parent in networks if parent.networkBoxes()},
        'notes':{int(parent.sessionId()):[notes._state(note) for note in parent.stickyNotes()]
                 for parent in networks if parent.stickyNotes()},
    }

locked_path=create('locked_native_editor_delete')
assert not hou.node(locked_path).isEditable()
ok(f'delete_node({locked_path!r})')
assert hou.node(locked_path) is None,'locked native internals delete with their owned root'

path=create('native_editor_delete')
node=hou.node(path)
node.allowEditingOfContents()  # Fixture-only: add adversarial user items below.
assert node.networkBoxes() and node.stickyNotes(),'shipped Karma settings must exercise native editor items'
assert any(any(isinstance(item,hou.StickyNote) for item in box.items(recurse=False))
           for box in node.networkBoxes())
assert all(boxes.box_provenance(box,SESSION)['status']=='owned_current_session' for box in node.networkBoxes())
assert all(notes.note_provenance(note,SESSION)['status']=='owned_current_session' for note in node.stickyNotes())
original=baseline(node)
assert not call(f'delete_node({path!r})',owner='another-author')['ok']
assert baseline(node)==original

# Deletion snapshots can observe note membership. Presentation editing retains
# its narrower model and cannot detach/delete a note as if it were a node.
native_box=node.networkBoxes()[0]
rejected=call(f"network_boxes({path!r},[],remove={[native_box.name()]!r})")
assert not rejected['ok'] and 'non-node' in rejected['error'],rejected
assert baseline(node)==original

# Later user objects are foreign even inside an owned native root. Repeating
# node registration must not turn ancestry into editor-item authority.
late_note=node.createStickyNote('late_user_note')
native_box.addItem(late_note)
with ownership.execution_owner(SESSION,'repeat-registration'):
    ownership.register_owned_node(node)
assert notes.note_provenance(late_note,SESSION)['status']=='foreign'
blocked=call(f'delete_node({path!r})')
assert not blocked['ok'] and 'foreign Sticky Note' in blocked['error'],blocked
assert hou.node(path) is not None
late_note.destroy()
late_box=node.createNetworkBox('late_user_box')
with ownership.execution_owner(SESSION,'repeat-registration'):
    ownership.register_owned_node(node)
assert boxes.box_provenance(late_box,SESSION)['status']=='foreign'
blocked=call(f'delete_node({path!r})')
assert not blocked['ok'] and 'foreign Network Box' in blocked['error'],blocked
late_box.destroy(destroy_contents=False)

# Unknown non-node editor kinds are still rejected, even for an explicitly
# authorized subtree; this change supports only the separately checked notes.
dot=node.createNetworkDot()
native_box.addItem(dot)
blocked=call(f"delete_node({path!r},allow_foreign='fixture explicitly authorizes this subtree')")
assert not blocked['ok'] and 'unsupported editor items' in blocked['error'],blocked
dot.destroy()

undo=bool(hou.undos.areEnabled())
if undo:
    before=baseline(node)
    rolled=call(f"delete_node({path!r})\nraise RuntimeError('after complete native deletion')")
    assert not rolled['ok'] and rolled['rollback']['applied'],rolled
    assert rolled['rollback']['network_boxes']['ok'] and rolled['rollback']['network_notes']['ok'],rolled
    node=hou.node(path)
    after=baseline(node)
    assert after['boxes']==before['boxes'] and after['notes']==before['notes'],(before,after)
    before_nodes={path:identity for identity,path in before['nodes']}
    after_nodes={path:identity for identity,path in after['nodes']}
    assert set(before_nodes)==set(after_nodes)
    changed={path for path in before_nodes if before_nodes[path]!=after_nodes[path]}
    # Native Undo can rebuild wrangle compiler children. Only the existing
    # ownership reconciliation's explicitly reported slots may change IDs.
    assert changed<=set(rolled['rollback'].get('reconciled_resurrected_identities',[])),rolled
    with ownership.execution_owner(SESSION,'verify-native-undo'):
        for changed_path in changed:
            ownership.require_owned(hou.node(changed_path),'native undo fixture')
    assert all(boxes.box_provenance(box,SESSION)['status']=='owned_current_session' for box in node.networkBoxes())
    assert all(notes.note_provenance(note,SESSION)['status']=='owned_current_session' for note in node.stickyNotes())

parent_ids={int(item.sessionId()) for item in [node,*node.allSubChildren()] if item.isNetwork()}
ok(f'delete_node({path!r})')
assert hou.node(path) is None
assert not any(key[1] in parent_ids for key in boxes._OWNED_BOXES)
assert not any(key[1] in parent_ids for key in notes._OWNED_NOTES)

# A failed initializer must not leave typed Box registration after tab_create
# removes its new subtree, including when headless has no native Undo.
known_boxes=set(boxes._OWNED_BOXES)
known_notes=set(notes._OWNED_NOTES)
failed=call("tab_create('/stage','karmarendersettings',name='failed_editor_init',parms={'not_a_native_parm':1})")
assert not failed['ok'] and hou.node('/stage/failed_editor_init') is None,failed
assert set(boxes._OWNED_BOXES)==known_boxes
assert set(notes._OWNED_NOTES)==known_notes

# Explicit authorization remains a one-call exemption; user/native items are
# not permanently adopted in order to delete a clearly selected foreign root.
foreign=hou.node('/stage').createNode('karmarendersettings','foreign_editor_delete')
foreign_path=foreign.path()
assert not call(f'delete_node({foreign_path!r})')['ok']
ok(f"delete_node({foreign_path!r},allow_foreign='user explicitly selected this fixture root and contents')")
assert hou.node(foreign_path) is None
print(json.dumps({'version':hou.applicationVersionString(),'native_undo':undo,
                  'native_editor_delete':True,'foreign_items_preserved':True,
                  'unsupported_items_preserved':True,'creation_failure_cleanup':True}),flush=True)
