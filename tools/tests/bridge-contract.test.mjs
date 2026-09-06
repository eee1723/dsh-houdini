import assert from 'node:assert/strict';
import http from 'node:http';
import { HoudiniBridge } from '../../lib/bridge.js';
import {
  EXPECTED_VERB_CATALOG_HASH,
  EXPECTED_VERB_NAMES,
  EXPECTED_EXECUTION_CONTRACT_VERSION,
} from '../../lib/generated-verb-contract.js';

let stale = true;
let execCalls = 0;
let lastExecBody = null;
let semanticVersion = EXPECTED_EXECUTION_CONTRACT_VERSION;
const server = http.createServer((request, response) => {
  response.setHeader('content-type', 'application/json');
  if (request.url === '/health') {
    response.end(JSON.stringify({
      ok: true,
      executionContractVersion: semanticVersion,
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
    let body = '';
    request.setEncoding('utf8');
    request.on('data', (chunk) => { body += chunk; });
    request.on('end', () => {
      execCalls++;
      lastExecBody = JSON.parse(body);
      response.end(JSON.stringify({
        ok: true,
        stdout: '',
        stderr: '',
        ...(lastExecBody.code.includes('hou.hipFile.path()') ? { result: 'C:/project' } : {}),
      }));
    });
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
  const bridge = new HoudiniBridge(url, 1000);
  const result = await bridge.exec('__result__ = 1');
  assert.equal(result.ok, true);
  assert.equal(execCalls, 1);
  assert.deepEqual(lastExecBody.expected_contract, {version: EXPECTED_EXECUTION_CONTRACT_VERSION, hash: EXPECTED_VERB_CATALOG_HASH});
  semanticVersion--;
  await assert.rejects(bridge.exec('__result__ = 2'), /contract mismatch.*semantics/);
  assert.equal(execCalls, 1, 'same-name stale semantics must fail before /exec even immediately after a successful check');
  semanticVersion = EXPECTED_EXECUTION_CONTRACT_VERSION;
  assert.equal(await bridge.hipDir(), 'C:/project');
  assert.equal(lastExecBody.read_only, 'true', 'internal $HIP inspection must use the read-only bridge boundary');
} finally {
  await new Promise((resolve, reject) => server.close((error) => error ? reject(error) : resolve()));
}

console.log('bridge contract handshake tests passed');
