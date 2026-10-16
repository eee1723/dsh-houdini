"""Streaming fingerprints of native BJSON geometry (UT_JSONDefines.h, H21/H22).

Resolve string tokens before hashing: a date string referenced by a real user
attribute must remain evidence even when info.date itself is writer metadata.
Unknown tokens/oversized string tables fail; no byte-pattern replacement.
"""
import hashlib

WRITER_INFO_FIELDS = (b'date', b'group_summary')
_WIDTHS={0x10:1,0x11:1,0x12:2,0x13:4,0x14:8,0x21:1,0x22:2,0x18:2,0x19:4,0x1a:8}
_STRINGS=32*1024*1024


class Reader:
    def __init__(self,stream):
        self.stream=stream;self.tokens={};self.string_bytes=0
        magic=self.read(5)
        if magic not in (b'\x7fNSJb',b'\x7fbJSN'):raise ValueError('unsupported native bgeo encoding')
        self.endian='little' if magic==b'\x7fNSJb' else 'big'

    def read(self,n):
        value=self.stream.read(n)
        if len(value)!=n:raise ValueError('truncated native bgeo')
        return value

    def length(self):
        first=self.read(1)[0]
        if first<0xf1:return first
        if first not in (0xf2,0xf4,0xf8):raise ValueError('unknown BJSON length encoding')
        return int.from_bytes(self.read(first-0xf0),self.endian)

    def string(self):
        size=self.length()
        if size>_STRINGS:raise ValueError('bgeo fingerprint string budget exceeded')
        return self.read(size)

    def token(self):
        while True:
            token=self.read(1)[0]
            if token==0x2b:
                ident=self.length();value=self.string()
                self.string_bytes+=len(value)-len(self.tokens.get(ident,b''))
                if self.string_bytes>_STRINGS:raise ValueError('bgeo fingerprint token-table budget exceeded')
                self.tokens[ident]=value
            elif token==0x2d:
                self.string_bytes-=len(self.tokens.pop(self.length(),b''))
            elif token not in (0x3a,0x2c):return token

    def reference(self):
        ident=self.length()
        if ident not in self.tokens:raise ValueError('undefined BJSON string token')
        return self.tokens[ident]

    def value(self,token,path=(),depth=0):
        if depth>128:raise ValueError('bgeo fingerprint nesting budget exceeded')
        digest=hashlib.sha256();hint=None
        if token in (0x27,0x26):
            hint=self.string() if token==0x27 else self.reference()
            digest.update(b's'+len(hint).to_bytes(8,'little')+hint)
        elif token in _WIDTHS:
            digest.update(bytes([token])+self.read(_WIDTHS[token]))
        elif token in (0,0x30,0x31):digest.update(bytes([token]))
        elif token==0x40:
            kind=self.read(1)[0];count=self.length()
            digest.update(b'u'+bytes([kind])+count.to_bytes(8,'little'))
            if kind in (0x27,0x26):
                for _ in range(count):
                    value=self.string() if kind==0x27 else self.reference()
                    digest.update(len(value).to_bytes(8,'little'));digest.update(value)
            elif kind in _WIDTHS:
                remaining=((count+31)//32)*4 if kind==0x10 else count*_WIDTHS[kind]
                while remaining:
                    size=min(remaining,1024*1024);digest.update(self.read(size));remaining-=size
            else:raise ValueError('unsupported BJSON uniform array type')
        elif token==0x7b:
            fields={}
            while True:
                key_token=self.token()
                if key_token==0x7d:break
                _,key=self.value(key_token,path,depth+1)
                if key is None or key in fields:raise ValueError('invalid BJSON map key')
                child,_=self.value(self.token(),path+(key,),depth+1)
                fields[key]=child
            digest.update(b'm')
            for key in sorted(fields):
                if path==(b'info',) and key in WRITER_INFO_FIELDS:continue
                digest.update(len(key).to_bytes(8,'little'));digest.update(key);digest.update(fields[key])
        elif token==0x5b:
            unordered=path in [(name,) for name in (b'pointgroups',b'primitivegroups',b'vertexgroups',b'edgegroups')]
            children=[];digest.update(b'a')
            while True:
                child_token=self.token()
                if child_token==0x5d:break
                child,_=self.value(child_token,path+(b'[]',),depth+1)
                if unordered:
                    children.append(child)
                    if len(children)>100000:raise ValueError('bgeo group-table budget exceeded')
                else:digest.update(child)
            if unordered:
                for child in sorted(children):digest.update(child)
        else:raise ValueError('unsupported BJSON token '+hex(token))
        return digest.digest(),hint

    def geometry(self):
        if self.token()!=0x5b:raise ValueError('native bgeo root must be a field array')
        fields={}
        while True:
            token=self.token()
            if token==0x5d:break
            _,key=self.value(token)
            if key is None or key in fields:raise ValueError('invalid native bgeo root field')
            child,_=self.value(self.token(),(key,))
            fields[key]=child
        if self.stream.read(1):raise ValueError('unexpected data after native bgeo root')
        digest=hashlib.sha256()
        for key in sorted(fields):
            digest.update(len(key).to_bytes(8,'little'));digest.update(key);digest.update(fields[key])
        return {'sha256':digest.hexdigest(),'sections':{key.decode('utf-8'):value.hex() for key,value in fields.items()},
            'normalization':'BJSON token identities, map/group enumeration and writer info.date/group_summary only; all other serialized content retained'}


def fingerprint(path):
    with open(path,'rb') as stream:return Reader(stream).geometry()
