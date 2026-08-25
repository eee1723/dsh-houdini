import assert from 'node:assert/strict';
import http from 'node:http';
import { HoudiniBridge } from '../../lib/bridge.js';
import {
  EXPECTED_VERB_CATALOG_HASH,
  EXPECTED_VERB_NAMES,
} from '../../lib/generated-verb-contract.js';

let stale = true;
let execCalls = 0;
const server = http.createServer((request, response) => {
  response.setHeader('content-type', 'application/json');
  if (request.url === '/health') {
    response.end(JSON.stringify({
      ok: true,
      verbCatalog: stale
        ? { hash: 'old', count: 1, names: ['scene_info'] }
        : {
            hash: EXPECTED_VERB_CATALOG_HASH,
            count: EXPECTED_VERB_NAMES.length,
            names: EXPECTED_VERB_NAMES,
          },
    }));
    return;
  }
  if (request.url === '/exec') {
    execCalls++;
    response.end(JSON.stringify({ ok: true, stdout: '', stderr: '' }));
    return;
  }
  response.statusCode = 404;
  response.end('{}');
});

await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
try {
  const address = server.address();
  assert(address && typeof address === 'object');
  const url = `http://127.0.0.1:${address.port}`;

  await assert.rejects(
    new HoudiniBridge(url, 1000).exec('__result__ = 1'),
    /contract mismatch.*Repair and restart runtime/,
  );
  assert.equal(execCalls, 0, 'mismatch must fail before scene code reaches /exec');

  stale = false;
  const result = await new HoudiniBridge(url, 1000).exec('__result__ = 1');
  assert.equal(result.ok, true);
  assert.equal(execCalls, 1);
} finally {
  await new Promise((resolve, reject) => server.close((error) => error ? reject(error) : resolve()));
}

console.log('bridge contract handshake tests passed');
