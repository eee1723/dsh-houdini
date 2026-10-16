"""Writer time and token IDs are metadata; aliased user strings remain data."""
import io,struct,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'houdini/python3.11libs'))
from dsh_bgeo_fingerprint import Reader

def s(value):
    value=value.encode();assert len(value)<241
    return b"'"+bytes([len(value)])+value
def token(ident,value):
    value=value.encode();return b'+'+bytes([ident,len(value)])+value+b'&'+bytes([ident])
def root(info,attributes,groups=None):
    return b'\x7fNSJb['+s('info')+info+s('attributes')+attributes+(s('primitivegroups')+groups if groups else b'')+b']'
def sig(data):return Reader(io.BytesIO(data)).geometry()['sha256']
first=root(b'{'+s('date')+token(1,'yesterday')+b'}',b'{'+s('user_date')+b'&\x01'+b'}')
metadata_changed=root(b'{'+s('date')+token(7,'today')+b'}',b'{'+s('user_date')+s('yesterday')+b'}')
assert sig(first)==sig(metadata_changed)
user_changed=root(b'{'+s('date')+token(7,'today')+b'}',b'{'+s('user_date')+b'&\x07'+b'}')
assert sig(first)!=sig(user_changed),'normalizing metadata must not hide a changed aliased user attribute'
def group(name,points):return b'['+s(name)+b'@\x13'+bytes([len(points)])+struct.pack('<'+'i'*len(points),*points)+b']'
a,b=group('A',[1,2]),group('B',[3])
assert sig(root(b'{}',b'{}',b'['+a+b+b']'))==sig(root(b'{}',b'{}',b'['+b+a+b']'))
assert sig(root(b'{}',b'{}',b'['+a+b+b']'))!=sig(root(b'{}',b'{}',b'['+group('A',[2,1])+b+b']'))
for data in [first[:-1],first+b'extra',b'\x7fNSJb['+s('unknown')+b'\x99]',b'\x7fNSJb[&\x03]']:
    try:sig(data)
    except ValueError:pass
    else:raise AssertionError('unsupported/truncated BJSON accepted')
print('PASS streaming bgeo metadata, aliased user strings, group order/membership and invalid input')
