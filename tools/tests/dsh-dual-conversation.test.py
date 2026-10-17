"""One workbench Bridge, two Host conversations: writer handover and fences.

Run with ordinary Python --hython <H21 or H22>. No installed DSH, user
credentials, user HIP, GUI, global services or production registry are touched.
"""
from pathlib import Path
import argparse
import json
import os
import queue
import subprocess
import sys
import tempfile
import threading
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'houdini/python3.11libs'))
sys.path.insert(0, str(ROOT / 'tools'))
from houdini_test_environment import isolated_environment, reexec_unpacked_test_cli


def worker(args):
    import hou
    import dsh_bridge as bridge
    from dsh_shared_executor import prepare_registration, publish_registration
    hou.hipFile.setName(args.hip)
    server = bridge.start(0)
    bridge._pump_active = True
    facts = prepare_registration(workbench=True)
    registration = []

    def publish():
        publish_registration(args.registry, facts)
        from dsh_executor_registry import active_registration
        item = active_registration()
        registration.append(item)
        record = item.publish(server.server_port, bridge._RUNTIME_ID)
        print('READY=' + json.dumps(record), flush=True)

    published = threading.Thread(target=publish)
    published.start()
    published.join()
    done = threading.Event()

    def input_loop():
        for _line in sys.stdin:
            done.set()
            return
        done.set()

    threading.Thread(target=input_loop, daemon=True).start()
    try:
        while not done.wait(.01):
            bridge._pump()
    finally:
        bridge.stop()
        cleanup = threading.Thread(target=lambda: [r.close() for r in registration])
        cleanup.start()
        cleanup.join()


def main():
    reexec_unpacked_test_cli()
    parser = argparse.ArgumentParser()
    parser.add_argument('--worker', action='store_true')
    parser.add_argument('--registry')
    parser.add_argument('--hip')
    parser.add_argument('--hython')
    parser.add_argument('--host-node')
    args = parser.parse_args()
    if args.worker:
        worker(args)
        return
    if not args.hython or not args.host_node:
        parser.error('--hython and --host-node are required')
    binary = Path(args.hython).resolve(strict=True)
    node = Path(args.host_node).resolve(strict=True)
    with tempfile.TemporaryDirectory(prefix='dsh-dual-conversation-', ignore_cleanup_errors=True) as temporary:
        base = Path(temporary)
        registry = base / 'registry'
        hip = base / 'dual-project.hip'
        hip.write_bytes(b'dual conversation writer fixture')
        output = (base / 'worker.log').open('wb')
        try:
            child = subprocess.Popen(
                [str(binary), str(Path(__file__).resolve()), '--worker',
                 '--registry', str(registry), '--hip', str(hip)],
                cwd=binary.parent,
                env=isolated_environment(base / 'env', executable=binary),
                stdin=subprocess.PIPE, stdout=output, stderr=subprocess.STDOUT,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            deadline = time.monotonic() + 45
            while True:
                records = list((registry / 'endpoints').glob('*.json')) if registry.exists() else []
                if records:
                    break
                if child.poll() is not None:
                    raise RuntimeError('worker failed: ' + (base / 'worker.log').read_text(errors='replace')[-3000:])
                if time.monotonic() > deadline:
                    raise RuntimeError('worker registration timeout: ' + str(base))
                time.sleep(.1)
            result = subprocess.run(
                [str(node), str(ROOT / 'tools' / 'dual-conversation-handover.mjs'), str(registry)],
                cwd=ROOT, env=isolated_environment(base / 'host-env'),
                capture_output=True, text=True, encoding='utf-8', errors='replace',
                timeout=60, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            if result.returncode != 0:
                raise RuntimeError('handover smoke failed:\n' + result.stdout + result.stderr)
            print(result.stdout.strip(), flush=True)
            print('PASS dual conversation on one workbench Bridge: steal refusal, idle handover, ownership fence', flush=True)
        finally:
            if child.poll() is None:
                child.stdin.write(b'\n')
                child.stdin.flush()
                try:
                    child.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait(timeout=10)
            output.close()


if __name__ == '__main__':
    main()
