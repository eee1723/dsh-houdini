import assert from 'node:assert/strict'
import { mkdtemp, rm, writeFile } from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import { checkPackage } from '../../skills/houdini-unreal-handoff/scripts/check-package.mjs'

const root = await mkdtemp(path.join(os.tmpdir(), 'hda-package-'))
try {
  const manifest = path.join(root, 'delivery.json')
  const declare = files => writeFile(manifest, JSON.stringify({ hda: 'example.hda', files }))
  await writeFile(path.join(root, 'example.hda'), 'abc')
  await declare([])
  const receipt = await checkPackage(manifest)
  assert.equal(receipt.files[0].sha256, 'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad')
  await declare(['missing.png'])
  await assert.rejects(checkPackage(manifest), { code: 'ENOENT' })
  await declare(['../external.png'])
  await assert.rejects(checkPackage(manifest), /package-relative/)
} finally { await rm(root, { recursive: true, force: true }) }
