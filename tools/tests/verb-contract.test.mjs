import assert from 'node:assert/strict';
import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { loadCatalog } from '../catalog-lib.mjs';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..');
const catalogNames = loadCatalog(path.join(root, 'docs', 'tool-design.md'))
  .flatMap((domain) => domain.verbs.map((verb) => verb.name))
  .sort();
const expectedHash = crypto.createHash('sha256').update(catalogNames.join('\n')).digest('hex');

const generated = fs.readFileSync(path.join(root, 'src', 'generated-verb-contract.ts'), 'utf8');
const generatedNames = JSON.parse(generated.match(/EXPECTED_VERB_NAMES = (\[[^\n]+\]) as const/)?.[1] || 'null');
const generatedHash = JSON.parse(generated.match(/EXPECTED_VERB_CATALOG_HASH = ("[^"]+")/)?.[1] || 'null');
assert.deepEqual(generatedNames, catalogNames, 'generated host names drifted from tool-design.md');
assert.equal(generatedHash, expectedHash, 'generated host hash drifted from tool-design.md');

const bridge = fs.readFileSync(path.join(root, 'houdini', 'python3.11libs', 'dsh_bridge.py'), 'utf8');
const generatedVersion = Number(generated.match(/EXPECTED_EXECUTION_CONTRACT_VERSION = (\d+)/)?.[1]);
const bridgeVersion = Number(bridge.match(/_EXECUTION_CONTRACT_VERSION = (\d+)/)?.[1]);
assert.ok(generatedVersion > 0);
assert.equal(generatedVersion, bridgeVersion, 'host/bridge semantic execution version drifted');
const registry = bridge.match(/_VERBS:\s*dict\[str, object\]\s*=\s*\{([\s\S]*?)\n\}/)?.[1] || '';
const bridgeNames = [...registry.matchAll(/^\s*"([A-Za-z_]\w*)":/gm)].map((match) => match[1]).sort();
assert.deepEqual(bridgeNames, catalogNames, 'running bridge registry source drifted from tool-design.md');
assert.match(bridge, /"verbCatalog":\s*\{/);

console.log(`verb contract tests passed (${catalogNames.length} verbs, ${expectedHash.slice(0, 12)})`);
