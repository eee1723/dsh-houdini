import assert from 'node:assert/strict';
import fs from 'node:fs';

const webview = fs.readFileSync('houdini/python3.11libs/dsh_webview.py', 'utf8');
assert.doesNotMatch(webview, /^import socket$/m, 'WebView GUI module must not perform socket probes');
assert.doesNotMatch(webview, /def _port_open\b/, 'WebView retry must use asynchronous QWebEngine loading');
assert.match(webview, /view\.loadFinished\.connect\(_load_finished\)/);
assert.match(webview, /retry_timer\.setSingleShot\(True\)/);

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
assert.match(functionBody('_dispatch_service_preflight'), /if not ui_available:[\s\S]*?callback\(_service_preflight/);
assert.match(functionBody('_dispatch_service_preflight'), /cannot schedule non-blocking service preflight/);
assert.match(functionBody('launch'), /clear_external_bridge=True/);
assert.doesNotMatch(functionBody('open_workspace'), /clear_external_bridge=True/);
assert.match(functionBody('open_workspace'), /bridge already running[\s\S]*?open_ui_when_ready/);

console.log('GUI-thread probe regression passed');
