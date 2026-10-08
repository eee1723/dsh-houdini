"""Explicit proxy edits preserve the rest of the user-owned .env; no real home writes."""
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'houdini/python3.11libs'))
from dsh_network_diagnostics import update_home_proxy, redact_proxy, validate_proxy

with tempfile.TemporaryDirectory(prefix='dsh-network-config-') as temporary:
    home = Path(temporary)
    original = (b'\xef\xbb\xbf# keep this comment\r\n'
                b'OTHER="first\r\nHTTP_PROXY=inside unrelated multiline value\r\nlast"\r\n'
                b"export http_proxy = 'http://old:1000' # lower comment\r\n"
                b'HTTP_PROXY=http://other:2000 # upper comment\r\n'
                b'HTTPS_PROXY="http://secure:3000"\r\n'
                b'ALL_PROXY=http://fallback:4000\r\nNO_PROXY=localhost,example.test\r\n'
                b'UNRELATED_SECRET=do-not-display')
    filename = home / '.env'
    filename.write_bytes(original)
    outcome = update_home_proxy(home, {'http': 'http://127.0.0.1:7897'})
    actual = filename.read_bytes()
    expected = original.replace(b"'http://old:1000'", b'"http://127.0.0.1:7897"').replace(
        b'HTTP_PROXY=http://other:2000', b'HTTP_PROXY="http://127.0.0.1:7897"')
    assert actual == expected, actual
    assert outcome['updated'] == ['http'] and 'UNRELATED_SECRET' not in str(outcome)
    assert not list(home.glob('*.tmp'))
    update_home_proxy(home, {'https': 'http://user:credential@127.0.0.1:7897'})
    assert 'credential' not in redact_proxy('http://user:credential@127.0.0.1:7897')
    assert 'user' not in redact_proxy('http://user:credential@127.0.0.1:7897')
    assert redact_proxy('http://user:credential@127.0.0.1:7897/path?token=private#secret') == 'http://redacted@127.0.0.1:7897'
    assert b'ALL_PROXY=http://fallback:4000' in filename.read_bytes()
    assert b'NO_PROXY=localhost,example.test' in filename.read_bytes()
    unchanged = filename.read_bytes()
    for value in ('socks5://127.0.0.1:1080', 'http://', 'http://localhost:bad', 'http://localhost\nSECRET=value'):
        try:
            update_home_proxy(home, {'http': value})
        except ValueError:
            pass
        else:
            raise AssertionError('Invalid proxy was accepted')
        assert filename.read_bytes() == unchanged
    filename.write_bytes(b'HTTP_PROXY="http://localhost:\n7897"\nOTHER=value\n')
    unchanged = filename.read_bytes()
    try:
        update_home_proxy(home, {'http': 'http://127.0.0.1:7897'})
    except ValueError as error:
        assert '多行' in str(error)
    else:
        raise AssertionError('Multiline proxy edit was guessed')
    assert filename.read_bytes() == unchanged

with tempfile.TemporaryDirectory(prefix='dsh-network-new-home-') as temporary:
    home = Path(temporary) / 'new-home'
    update_home_proxy(home, {'https': 'http://127.0.0.1:7897'})
    assert (home / '.env').read_text(encoding='utf8') == 'HTTPS_PROXY="http://127.0.0.1:7897"\n'
print('DSH home proxy edits: preserved comments, unrelated multiline values, duplicate casing and redaction passed')
