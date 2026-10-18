// Shared Node-test Python lookup. The plugin tests need a normal Python 3.11+
// for cross-language source checks; Houdini ships one even when no global
// `python` is installed, so a Houdini-only development machine must still be
// able to run the baseline Node suite.
import fs from 'node:fs'
import path from 'node:path'
import {spawnSync} from 'node:child_process'

function usable(command) {
  if (!command || typeof command !== 'string') return false
  const probe = spawnSync(command, ['-c', 'import sys;raise SystemExit(0 if sys.version_info >= (3, 11) else 1)'],
    {encoding: 'utf8', windowsHide: true, timeout: 15000})
  return probe.status === 0
}

function houdiniCandidates() {
  const roots = [process.env.ProgramFiles, process.env.ProgramW6432]
    .filter(Boolean)
    .map(root => path.join(root, 'Side Effects Software'))
  const candidates = []
  for (const root of roots) {
    let entries = []
    try { entries = fs.readdirSync(root) } catch { continue }
    for (const entry of entries.sort().reverse()) {
      if (!/^Houdini 2[1-9]\./.test(entry)) continue
      const install = path.join(root, entry)
      let pythons = []
      try { pythons = fs.readdirSync(install).filter(name => /^python3\d+$/.test(name)) } catch { continue }
      for (const name of pythons.sort().reverse()) candidates.push(path.join(install, name, 'python.exe'))
    }
  }
  return candidates
}

export function resolvePython() {
  const explicit = process.env.DSH_TEST_PYTHON
  if (explicit) {
    if (!usable(explicit)) throw new Error('DSH_TEST_PYTHON is not a usable Python 3.11+: ' + explicit)
    return explicit
  }
  for (const command of [process.env.PYTHON, 'python3', 'python']) if (usable(command)) return command
  for (const candidate of houdiniCandidates()) if (fs.existsSync(candidate) && usable(candidate)) return candidate
  throw new Error('No Python 3.11+ found for Node regressions; set DSH_TEST_PYTHON to an interpreter')
}
