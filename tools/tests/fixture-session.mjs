// Detached fixture sessions for tests and smoke runners.
// Header schema version is read from the library's own creation default so
// fixtures cannot drift when DSH bumps the session format.
import {Session} from '@deepseek-ai/dsh-session'
import {Context} from '@deepseek-ai/cordis'
import {SessionProjectionRegistry} from '@deepseek-ai/dsh-session-projection'
import {registerExecutorIdentityProjection} from '../../lib/executor-identity-projection.js'

const {version: HEADER_VERSION} = Session.create('fixture-header-schema').header

/** Exercise DSH's real cursor/materialization contract in detached fixtures. */
export function fixtureProjectionContext(overrides={}) {
  const ctx=overrides instanceof Context?overrides:new Context()
  if(!ctx.get('sessionProjections'))new SessionProjectionRegistry(ctx)
  registerExecutorIdentityProjection(ctx)
  if(overrides instanceof Context)return ctx
  return {...overrides,get:name=>name==='sessionProjections'?ctx.get(name):overrides.get?.(name)}
}

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
