// Detached fixture sessions for tests and smoke runners.
// Header schema version is read from the library's own creation default so
// fixtures cannot drift when DSH bumps the session format.
import {Session} from '@deepseek-ai/dsh-session'

const {version: HEADER_VERSION} = Session.create('fixture-header-schema').header

/**
 * Create a detached session. Pass meta.cwd / meta.agentPreset only when the
 * case needs them. meta.seed defaults to [] to match historical fixture
 * construction (a non-undefined seed marks the inherited cut).
 */
export function fixtureSession(id, meta = {}) {
  return Session.create(id, 'seed' in meta ? meta.seed : [], {
    version: HEADER_VERSION,
    id,
    createdAt: meta.createdAt ?? 1,
    isSeeded: false,
    ...(meta.cwd === undefined ? {} : {cwd: meta.cwd}),
    ...(meta.agentPreset === undefined ? {} : {agentPreset: meta.agentPreset}),
  })
}
