/** Inputs shared by source cache preparation and release runtime compilation. */
import fs from 'node:fs';
import path from 'node:path';
import {createHash} from 'node:crypto';

export function runtimeFixInputs(root, manifest) {
  return Object.fromEntries(manifest.inputFiles.map(name => [name,
    createHash('sha256').update(fs.readFileSync(path.join(root, name))).digest('hex'),
  ]));
}

export function runtimeFixKey(inputs) {
  return createHash('sha256').update(JSON.stringify(inputs)).digest('hex').slice(0, 12);
}
