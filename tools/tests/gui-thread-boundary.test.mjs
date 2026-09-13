import assert from 'node:assert/strict';
import fs from 'node:fs';

const webview = fs.readFileSync('houdini/python3.11libs/dsh_webview.py', 'utf8');
assert.doesNotMatch(webview, /^import socket$/m, 'WebView GUI module must not perform socket probes');
assert.doesNotMatch(webview, /def _port_open\b/, 'WebView retry must use asynchronous QWebEngine loading');
assert.match(webview, /view\.loadFinished\.connect\(_load_finished\)/);
assert.match(webview, /retry_timer\.setSingleShot\(True\)/);
assert.match(webview, /Promise\.withResolvers/);
assert.match(webview, /Object\.defineProperty\(Promise, 'withResolvers'/);
assert.match(webview, /QWebEngineScript\.InjectionPoint\.DocumentCreation/);
assert.match(webview, /_POLYFILL_ABORT_SIGNAL_ANY_JS \+ ";\\n" \+ _POLYFILL_PROMISE_WITH_RESOLVERS_JS/);
const finished = webview.match(/def _load_finished\(ok: bool\)[\s\S]*?(?=\ndef )/)[0];
assert.doesNotMatch(finished, /\.load\(/, 'auth completion must not restart the app and abort startup RPCs');
assert.match(webview, /window\.history\.replaceState/);
assert.match(webview, /current\.origin !== target\.origin/);
assert.match(webview, /current\.searchParams\.has\('token'\)/);

const launcher = fs.readFileSync('houdini/python3.11libs/dsh_launcher.py', 'utf8');
const functionBody = (name) => {
  const match = launcher.match(new RegExp(
    `^def ${name}\\([^\\r\\n]*\\)[^\\r\\n]*:\\r?\\n([\\s\\S]*?)(?=^def |^if __name__|(?![\\s\\S]))`,
    'm',
  ));
  assert.ok(match, `missing launcher function ${name}`);
  return match[1];
};
assert.doesNotMatch(functionBody('restart_bridge'), /_kill_port_process|_port_open|_port_pid/);
assert.doesNotMatch(functionBody('launch'), /_kill_port_process|_port_open|_port_pid/);
assert.doesNotMatch(functionBody('open_workspace'), /_kill_port_process|_port_open|_port_pid/);
assert.match(functionBody('_service_preflight'), /_port_open[\s\S]*?_port_pid/);
assert.match(functionBody('_dispatch_service_preflight'), /threading\.Thread\(target=worker/);
assert.match(functionBody('_dispatch_service_preflight'), /if not ui_available:[\s\S]*?callback\(preflight/);
assert.match(functionBody('_dispatch_service_preflight'), /cannot schedule non-blocking service preflight/);
assert.doesNotMatch(launcher, /clear_external_bridge|external_bridge_cleared|_kill_port_process|taskkill/);
assert.doesNotMatch(functionBody('_service_preflight'), /stop_owned|terminate|restart_bridge/);
assert.match(functionBody('_frontend_online'), /owns_pid\(pid\)/);
assert.match(functionBody('_service_preflight'), /bridge port conflict/);
assert.match(functionBody('restart_frontend'), /_frontend_online\(\)[\s\S]*?_terminate_pending_frontend/);
assert.match(functionBody('_terminate_pending_frontend'), /dsh_managed_runtime\.stop_owned\(\*\*ownership\)/);
assert.match(functionBody('_cancel_startup'), /threading\.Thread\([\s\S]*?"expected_process": process/);
assert.match(functionBody('open_workspace'), /bridge already running[\s\S]*?open_ui_when_ready/);
assert.match(functionBody('open_workspace'), /open_ui\(frontend_cwd\)/);
assert.doesNotMatch(launcher, /ensure_houdini_session|_select_houdini_session|_open_existing_frontend|archivedSessionIds/);
assert.doesNotMatch(functionBody('open_workspace'), /_dsh_rpc_wire|session\/create/);
assert.match(functionBody('open_ui'), /raise_workspace\(workspace_dir\)[\s\S]*?_DSH_WEB_SESSION\.launch_url/);
assert.match(functionBody('open_ui_when_ready'), /open_ui\(frontend_cwd, force_reload=True\)/);

console.log('GUI-thread probe regression passed');
