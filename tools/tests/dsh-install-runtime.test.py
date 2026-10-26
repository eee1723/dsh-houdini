"""Install only Houdini helpers; preserve the simulated official Desktop home."""
import importlib.util
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('helper_installer', ROOT / 'houdini/install.py')
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)
with patch.dict(os.environ, {'HOUDINI_USER_PREF_DIR': 'D:/Fixture/houdini__HVER__'}):
    assert installer.default_packages_dirs() == [Path('D:/Fixture/houdini21.0/packages'), Path('D:/Fixture/houdini22.0/packages')]

if os.name == 'nt':
    with tempfile.TemporaryDirectory(prefix='dsh-helper-install-中文 空格-') as temporary:
        # Windows CI can expose TEMP through an 8.3 user-directory alias.
        # Derive every fixture argument/expectation from the same existing,
        # canonical root before PowerShell applies its path normalization.
        folder = Path(temporary).resolve()
        home, helpers, packages = folder / 'official-home', folder / 'helpers', folder / 'prefs/packages'
        home.mkdir()
        preserved = home / 'settings.yaml'
        preserved.write_bytes(b'official-fixture: preserve\n')
        profile = home / 'profiles/desktop/package.json'
        profile.parent.mkdir(parents=True)
        third_party = {'name': 'issue-4-existing-profile', 'private': True, 'dependencies': {
            '@ace-zone/dsh-market': 'fixture-market', 'cc-safety-net': 'fixture-safety',
            'dsh-reverse-image-search': 'fixture-images'}, 'dsh': {'profile': {'bundles': [
                '@deepseek-ai/dsh-base', '@deepseek-ai/dsh-web-app', '@ace-zone/dsh-market']}}}
        profile_bytes = json.dumps(third_party).encode()
        profile.write_bytes(profile_bytes)
        packages.mkdir(parents=True)
        target = packages / 'dsh-houdini.json'
        unknown = b'{"user-fixture":"unowned registration must survive"}'
        target.write_bytes(unknown)
        environment = dict(os.environ, DSH_HOME=str(home), HOUDINI_PACKAGE_DIR='',
                           HOUDINI_USER_PREF_DIR=str(folder / 'fallback-houdini__HVER__'))
        powershell = str(Path(os.environ['SystemRoot']) / 'System32/WindowsPowerShell/v1.0/powershell.exe')
        def source_version(name, version):
            source = folder / name
            shutil.copytree(ROOT / 'houdini', source / 'houdini', ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
            (source / 'installer').mkdir()
            for name in ('install.ps1', 'uninstall.ps1', 'legacy-migration.ps1'):
                shutil.copy2(ROOT / 'installer' / name, source / 'installer' / name)
            manifest = json.loads((ROOT / 'package.json').read_text(encoding='utf-8'))
            manifest['version'] = version
            (source / 'package.json').write_text(json.dumps(manifest), encoding='utf-8')
            return source

        first_source = source_version('helper-v1', '0.0.8-fixture')
        second_source = source_version('helper-v2', '0.0.10-fixture')
        command = [powershell, '-NoLogo', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
                   str(first_source / 'installer/install.ps1'), '-Root', str(helpers), '-PackagesDir', str(packages)]
        fixed_pref = folder / 'non-template-preferences'
        default_preview = subprocess.run([*command[:7], '-Root', str(folder / 'uncreated-install'), '-PrintOnly'],
                                         env=dict(environment, HOUDINI_USER_PREF_DIR=str(fixed_pref)), check=True,
                                         capture_output=True, text=True, encoding='utf-8', timeout=30)
        assert json.loads(default_preview.stdout)['targets'] == [str(fixed_pref / 'packages')]
        package_directories = [folder / '环境 包目录/first', folder / '环境 包目录/second']
        package_environment = dict(environment, HOUDINI_PACKAGE_DIR=os.pathsep.join(map(str, [
            *package_directories, package_directories[0]])))
        environment_preview = subprocess.run([*command[:7], '-Root', str(folder / 'uncreated-env-install'), '-PrintOnly'],
                                             env=package_environment, check=True, capture_output=True,
                                             text=True, encoding='utf-8', timeout=30)
        actual_targets = json.loads(environment_preview.stdout)['targets']
        expected_targets = list(map(str, package_directories))
        assert actual_targets == expected_targets, {'actual': ascii(actual_targets), 'expected': ascii(expected_targets)}
        assert not (folder / 'uncreated-env-install').exists()
        assert not any(path.exists() for path in package_directories)
        relative_environment = dict(package_environment, HOUDINI_PACKAGE_DIR=str(package_directories[0]) + os.pathsep + 'C:relative')
        relative_refused = subprocess.run([*command[:7], '-Root', str(folder / 'relative-env-install'), '-PrintOnly'],
                                          env=relative_environment, capture_output=True, timeout=30)
        assert relative_refused.returncode != 0 and not (folder / 'relative-env-install').exists()
        assert not any(path.exists() for path in package_directories)

        # Use the same Node UTF-8 execFile consumer as Desktop. A parent PS5
        # deliberately starts with GBK/OEM encodings; the installer must reset
        # both output encodings before writing the Chinese JSON receipt.
        node = shutil.which('node')
        assert node, 'Node is required for the real Desktop-like receipt consumer'
        node_consumer = folder / 'consume-install.cjs'
        node_consumer.write_text('''const {execFile}=require('node:child_process');
const [powershell,script,root]=process.argv.slice(2);
const q=value=>"'"+value.replaceAll("'","''")+"'";
const source="[Console]::OutputEncoding=[Text.Encoding]::GetEncoding(936);"+
 "$OutputEncoding=[Text.Encoding]::GetEncoding(936); & "+q(script)+" -Root "+q(root);
execFile(powershell,['-NoLogo','-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-Command',source],
 {encoding:'utf8',windowsHide:true,timeout:60000},(error,stdout,stderr)=>{
  if(error){process.stderr.write(stderr);process.exitCode=1;return;}
  const line=stdout.trimEnd().split(/\\r?\\n/).at(-1);
  const prefix='DSH_HOUDINI_INSTALL_RESULT=';
  if(!line?.startsWith(prefix))throw Error('Missing last-line installer receipt');
  const result=JSON.parse(line.slice(prefix.length));
  if(result.message.includes('\\uFFFD'))throw Error('Mojibake in installer receipt');
  process.stdout.write(JSON.stringify(result));
});
''', encoding='utf-8')
        environment_install_root = folder / '环境 安装根'
        consumed = subprocess.run([node, str(node_consumer), powershell, str(first_source / 'installer/install.ps1'),
                                   str(environment_install_root)], env=package_environment, check=True,
                                  capture_output=True, text=True, encoding='utf-8', timeout=75)
        native_receipt = json.loads(consumed.stdout)
        assert native_receipt['ok'] and native_receipt['message'].startswith('Houdini 组件已安装。')
        assert Path(native_receipt['helperRoot']).is_relative_to(environment_install_root)
        assert all((path / 'dsh-houdini.json').is_file() for path in package_directories)
        assert not (folder / 'fallback-houdini21.0').exists(), 'HOUDINI_PACKAGE_DIR must precede the fallback preferences'

        preview = subprocess.run([*command, '-MigrationPreview'], env=environment, check=True,
                                 capture_output=True, text=True, encoding='utf-8', timeout=30)
        assert json.loads(preview.stdout)['migration']['conflicts'][0]['path'] == str(target)
        assert not helpers.exists(), 'preview may not create helpers, locks, reports or backups'
        refused = subprocess.run(command, env=environment, capture_output=True, timeout=30)
        assert refused.returncode != 0 and target.read_bytes() == unknown
        assert not (helpers / 'helpers').exists(), 'unknown conflicts must precede all helper/package changes'

        legacy_bootstrap = helpers / 'bootstrap/1234567890abcdef'
        previous = json.dumps({'env': [
            {'DSH_HOUDINI_INSTALL_ROOT': helpers.as_posix()},
            {'PYTHONPATH': legacy_bootstrap.as_posix() + '/python;$PYTHONPATH'}],
            'path': legacy_bootstrap.as_posix()}, indent=2).encode()
        target.write_bytes(previous)
        duplicate = packages / 'old-copy.json'
        duplicate.write_bytes(previous)
        private_data = helpers / 'data/old-install/sessions/retained.jsonl'
        private_data.parent.mkdir(parents=True)
        private_data.write_bytes(b'private-old-session-fixture\n')
        startup = packages.parent / 'python3.11libs/pythonrc.py'
        startup.parent.mkdir()
        legacy_stub = (b'# Only capture a small installation-state snapshot at process startup.\r\n'
                       b'# No hashing, network, process probes, Node or DSH on the GUI thread.\r\n'
                       b'import dsh_bootstrap\r\ndsh_bootstrap.initialize()\r\n')
        startup.write_bytes(legacy_stub)
        mixed = packages.parent / 'python3.13libs/pythonrc.py'
        mixed.parent.mkdir()
        mixed_bytes = legacy_stub + b'print("user studio startup; never execute in this test")\n'
        mixed.write_bytes(mixed_bytes)
        shelf = packages.parent / 'toolbar/custom.shelf'
        shelf.parent.mkdir()
        shelf_bytes = b'<shelf><tool><script>import dsh_launcher; dsh_launcher.launch()</script></tool></shelf>'
        shelf.write_bytes(shelf_bytes)
        wrapper = helpers / 'Uninstall.cmd'
        wrapper_bytes = (b'@echo off\r\nsetlocal\r\npowershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass '
                         b'-File "%~dp0bootstrap\\1234567890abcdef\\uninstall.ps1" -Root "%~dp0." %*\r\n'
                         b'if errorlevel 1 (pause & exit /b 1)\r\npause\r\n')
        wrapper.write_bytes(wrapper_bytes)
        other_legacy_root = folder / 'previous private installation'
        other_legacy_root.mkdir()
        other_package = packages / 'previous-install.json'
        other_bootstrap = other_legacy_root / 'bootstrap/fedcba9876543210'
        other_package.write_text(json.dumps({'env': [
            {'DSH_HOUDINI_INSTALL_ROOT': other_legacy_root.as_posix()},
            {'PYTHONPATH': other_bootstrap.as_posix() + '/python;$PYTHONPATH'}],
            'path': other_bootstrap.as_posix()}), encoding='utf-8')
        unknown_shortcut = other_legacy_root / 'DSH-Houdini.lnk'
        unknown_shortcut.write_bytes(b'user-edited-or-unreadable-shortcut-fixture')
        retained = {}
        for relative, data in {
                'releases/0.0.15/private-runtime.bin': b'old-runtime-fixture-never-execute',
                'data/old-install/credentials.json': b'opaque-fixture-credentials',
                'projects/existing.hip': b'fake-HIP-fixture-never-load',
                'cache/user-owned.bin': b'cache-fixture-preserve'}.items():
            path = helpers / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            retained[path] = data

        def ps_quote(value):
            return "'" + str(value).replace("'", "''") + "'"

        # Persist a real Unicode Windows shell link using the same native writer
        # interface used in the last 0.0.x release; no shortcut is executed.
        migration_source = (ROOT / 'installer/legacy-migration.ps1').read_text(encoding='utf-8')
        native_source = migration_source.split("Add-Type -TypeDefinition @'\n", 1)[1].split("\n'@", 1)[0]
        fixture_writer = '''public static void SaveFixture(string path,string target,string args) {
   object instance=new MigrationLink();
   try { var link=(IMigrationLink)instance; link.SetPath(target); link.SetArguments(args);
    ((IPersistFile)instance).Save(path,true);
   } finally { Marshal.FinalReleaseComObject(instance); }
  }
  '''
        native_source = native_source.replace('public static string[] Read', fixture_writer + 'public static string[] Read')
        native_file = folder / 'fixture-shortcut.cs'
        native_file.write_text(native_source, encoding='utf-8-sig')
        known_shortcut = helpers / 'DSH-Houdini.lnk'
        shortcut_args = ('-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "' +
                         str(legacy_bootstrap / 'open-workbench.ps1') + '" -Root "' + str(helpers) + '"')
        fixture_script = folder / 'fixture-shortcut.ps1'
        fixture_script.write_text(
            '$ErrorActionPreference="Stop"\nAdd-Type -Path ' + ps_quote(native_file) + '\n' +
            '[DshHoudini.MigrationShortcut]::SaveFixture(' + ','.join(map(ps_quote, [known_shortcut, powershell, shortcut_args])) + ')\n',
            encoding='utf-8-sig')
        subprocess.run([*command[:6], str(fixture_script)], env=environment, check=True, capture_output=True, timeout=30)
        shortcut_bytes = known_shortcut.read_bytes()
        def reports():
            return [json.loads(path.read_text(encoding='utf-8')) for path in (helpers / 'migrations').glob('*/report.json')]

        installed_result = subprocess.run(command, env=environment, check=True, capture_output=True,
                                          text=True, encoding='utf-8', timeout=60)
        receipt_line = installed_result.stdout.splitlines()[-1]
        assert receipt_line.startswith('DSH_HOUDINI_INSTALL_RESULT=')
        receipt = json.loads(receipt_line.split('=', 1)[1])
        assert receipt['ok'] is True and receipt['requiresRestart'] is True
        assert receipt['migration']['disabledCount'] == 6
        assert receipt['migration']['reviewCount'] == 3
        assert Path(receipt['migration']['reportPath']).is_file()
        package = json.loads(target.read_text(encoding='utf-8'))
        values = {key: value for item in package['env'] for key, value in item.items()}
        installed = Path(values['DSH_HOUDINI_PATH'])
        assert Path(receipt['helperRoot']) == installed.parent and receipt['helperId'] == installed.parent.name
        assert installed.is_relative_to(helpers)
        assert (installed / 'python3.11libs/dsh_desktop_client.py').is_file()
        assert not (installed / 'python3.11libs/dsh_webview.py').exists()
        assert not (installed / 'python3.11libs/dsh_workbench.py').exists()
        assert (installed / 'MainMenuCommon.xml').is_file()
        assert not (installed.parent / 'node_modules').exists()
        assert private_data.read_bytes() == b'private-old-session-fixture\n'
        assert all(path.read_bytes() == data for path, data in retained.items())
        applied = next(report for report in reports() if report['status'] == 'applied')
        assert any(action['beforeSha256'] == hashlib.sha256(previous).hexdigest() for action in applied['actions'])
        for report_path in (helpers / 'migrations').glob('*/report.json'):
            report = json.loads(report_path.read_text(encoding='utf-8'))
            for action in report['actions']:
                if action.get('backup'):
                    data = (report_path.parent / action['backup']).read_bytes()
                    assert hashlib.sha256(data).hexdigest() == action['beforeSha256']
        assert not duplicate.exists() and not startup.exists() and not wrapper.exists()
        assert not known_shortcut.exists(), 'exact old standalone shortcut must be retired'
        assert next(helpers.glob('DSH-Houdini.lnk.dsh-disabled-*')).read_bytes() == shortcut_bytes
        assert next(duplicate.parent.glob('old-copy.json.dsh-disabled-*')).read_bytes() == previous
        assert next(startup.parent.glob('pythonrc.py.dsh-disabled-*')).read_bytes() == legacy_stub
        assert mixed.read_bytes() == mixed_bytes and shelf.read_bytes() == shelf_bytes
        assert unknown_shortcut.read_bytes() == b'user-edited-or-unreadable-shortcut-fixture'
        assert {item['path'] for item in applied['preserved']} >= {str(mixed), str(shelf), str(unknown_shortcut)}
        before_repeat = len(reports())
        subprocess.run(command, env=environment, check=True, capture_output=True, timeout=60)
        assert len(reports()) == before_repeat, 'repeated installation must not create more migrations'

        applied_path = next(path for path in (helpers / 'migrations').glob('*/report.json')
                            if json.loads(path.read_text(encoding='utf-8')).get('status') == 'applied')
        installed_bytes = target.read_bytes()
        rollback = [*command[:6], str(first_source / 'installer/install.ps1'), '-Root', str(helpers),
                    '-RollbackMigration', str(applied_path)]
        rollback_preview = subprocess.run([*rollback, '-MigrationPreview'], env=environment, check=True,
                                          capture_output=True, text=True, encoding='utf-8', timeout=30)
        assert json.loads(rollback_preview.stdout)['restore']
        assert target.read_bytes() == installed_bytes and not duplicate.exists()
        target.write_bytes(installed_bytes + b'\n')
        rejected_rollback = subprocess.run(rollback, env=environment, capture_output=True, timeout=30)
        assert rejected_rollback.returncode != 0, 'rollback must refuse even a semantically identical later byte edit'
        assert target.read_bytes() == installed_bytes + b'\n'
        assert not duplicate.exists() and not startup.exists(), 'rollback must preflight every file before restoring any'
        target.write_bytes(installed_bytes)
        subprocess.run(rollback, env=environment, check=True, capture_output=True, timeout=30)
        assert target.read_bytes() == previous and duplicate.read_bytes() == previous
        assert startup.read_bytes() == legacy_stub and wrapper.read_bytes() == wrapper_bytes
        assert known_shortcut.read_bytes() == shortcut_bytes
        assert all(path.read_bytes() == data for path, data in retained.items())
        assert profile.read_bytes() == profile_bytes and mixed.read_bytes() == mixed_bytes and shelf.read_bytes() == shelf_bytes
        subprocess.run(rollback, env=environment, check=True, capture_output=True, timeout=30)
        subprocess.run(command, env=environment, check=True, capture_output=True, timeout=60)
        assert preserved.read_bytes() == b'official-fixture: preserve\n'
        assert profile.read_bytes() == profile_bytes
        assert sorted(file.name for file in home.iterdir()) == ['profiles', 'settings.yaml']

        first_install = installed
        first_manifest = (installed.parent / 'package.json').read_bytes()
        ignored_environment_target = folder / 'environment-must-not-override-records'
        subprocess.run([*command[:6], str(second_source / 'installer/install.ps1'), '-Root', str(helpers)],
                       env=dict(environment, HOUDINI_PACKAGE_DIR=str(ignored_environment_target)),
                       check=True, capture_output=True, timeout=60)
        assert not ignored_environment_target.exists(), 'recorded custom preferences must precede a new environment path'
        assert not (folder / 'fallback-houdini21.0').exists(), 'upgrade must retain recorded custom preferences'
        updated = json.loads(target.read_text(encoding='utf-8'))
        installed = Path(next(item['DSH_HOUDINI_PATH'] for item in updated['env'] if 'DSH_HOUDINI_PATH' in item))
        assert installed != first_install and first_install.is_dir()
        assert (first_install.parent / 'package.json').read_bytes() == first_manifest
        selector = installed.parent / 'installer/install.ps1'
        listing = subprocess.run([*command[:6], str(selector), '-Root', str(helpers), '-ListHelpers'],
                                 env=environment, check=True, capture_output=True, text=True, encoding='utf-8', timeout=30)
        rows = json.loads(listing.stdout)
        assert {item['version'] for item in rows if item['valid']} == {'0.0.8-fixture', '0.0.10-fixture'}
        # A file added inside the runtime-bearing Houdini tree invalidates the
        # snapshot for every consumer. A normal reinstall must not silently
        # reactivate a helper that the version picker already rejects.
        extra = first_install / 'python3.11libs/user-extra.py'
        extra_bytes = b'# user fixture file: preserve, never execute\n'
        extra.write_bytes(extra_bytes)
        polluted_listing = subprocess.run([*command[:6], str(selector), '-Root', str(helpers), '-ListHelpers'],
                                          env=environment, check=True, capture_output=True,
                                          text=True, encoding='utf-8', timeout=30)
        polluted_rows = json.loads(polluted_listing.stdout)
        assert next(row for row in polluted_rows if row['id'] == first_install.parent.name)['valid'] is False
        target_before_extra = target.read_bytes()
        registrations_before_extra = (helpers / 'registrations.json').read_bytes()
        normal_refused = subprocess.run(command, env=environment, capture_output=True, timeout=60)
        assert normal_refused.returncode != 0, {
            'listRejected': True, 'normalInstallExit': normal_refused.returncode,
            'packageChanged': target.read_bytes() != target_before_extra,
            'extraPreserved': extra.read_bytes() == extra_bytes}
        # Windows PowerShell can wrap its rendered error in the middle of a
        # word or path even when redirected. Verify the full meaning and ID.
        identity_error = ''.join(normal_refused.stderr.decode('utf-8', errors='replace').split())
        assert 'Unknownfileswerepreserved' in identity_error and 'noPackageorregistrationswerechanged' in identity_error, identity_error
        assert first_install.parent.name in identity_error, 'the failure must identify the exact helper snapshot'
        assert b'DSH_HOUDINI_INSTALL_RESULT=' not in normal_refused.stdout
        assert target.read_bytes() == target_before_extra, 'invalid helper must not replace the active Package'
        assert (helpers / 'registrations.json').read_bytes() == registrations_before_extra
        assert extra.read_bytes() == extra_bytes, 'unknown helper content must remain untouched'
        selected_refused = subprocess.run([*command[:6], str(selector), '-Root', str(helpers),
                                           '-SelectHelper', first_install.parent.name],
                                          env=environment, capture_output=True, timeout=30)
        assert selected_refused.returncode != 0 and target.read_bytes() == target_before_extra
        # Remove only this test's own injected fixture, then continue the healthy
        # two-version lifecycle without changing production's preserve behavior.
        extra.unlink()
        subprocess.run([*command[:6], str(selector), '-Root', str(helpers), '-SelectHelper', first_install.parent.name],
                       env=environment, check=True, capture_output=True, timeout=30)
        rolled = json.loads(target.read_text(encoding='utf-8'))
        selected = Path(next(item['DSH_HOUDINI_PATH'] for item in rolled['env'] if 'DSH_HOUDINI_PATH' in item))
        assert selected == first_install, 'rollback must atomically select the retained helper path'
        code = ('import sys,json;sys.path.insert(0,sys.argv[1]); '
                'import dsh_deployment,dsh_desktop_client,dsh_executor_registry,dsh_managed_runtime; '
                'print(json.dumps([m.__file__ for m in '
                '[dsh_deployment,dsh_desktop_client,dsh_executor_registry,dsh_managed_runtime]]))')
        loaded = subprocess.run([sys.executable, '-B', '-c', code, str(selected / 'python3.11libs')],
                                cwd=folder, env=environment, check=True, capture_output=True, text=True, timeout=15)
        assert all(Path(filename).is_relative_to(selected) for filename in json.loads(loaded.stdout))
        assert profile.read_bytes() == profile_bytes, 'both installs and rollback must preserve third-party profile dependencies'
        before_unregister = target.read_bytes()
        edited_root_shortcut = helpers / 'DSH-Houdini.lnk'
        edited_root_shortcut.write_bytes(b'edited-shortcut-do-not-delete-by-name')
        subprocess.run([powershell, '-NoLogo', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
                        str(ROOT / 'installer/uninstall.ps1'), '-Root', str(helpers), '-PackagesDir', str(packages)],
                       env=environment, check=True, capture_output=True, timeout=30)
        assert not target.exists()
        assert installed.is_dir(), 'unregister must preserve helper files and earlier data'
        assert unknown_shortcut.read_bytes() == b'user-edited-or-unreadable-shortcut-fixture'
        assert edited_root_shortcut.read_bytes() == b'edited-shortcut-do-not-delete-by-name'
        assert private_data.read_bytes() == b'private-old-session-fixture\n'
        assert preserved.read_bytes() == b'official-fixture: preserve\n'
        assert all(path.read_bytes() == data for path, data in retained.items())
        # Removal itself is reversible and does not reactivate a private Host.
        unregister_report = next(path for path in (helpers / 'migrations').glob('*/report.json')
                                 if json.loads(path.read_text(encoding='utf-8')).get('purpose') == 'uninstall')
        subprocess.run([*command[:6], str(selector), '-Root', str(helpers), '-RollbackMigration', str(unregister_report)],
                       env=environment, check=True, capture_output=True, timeout=30)
        assert target.read_bytes() == before_unregister

        race = folder / 'changed-after-preview'
        race_packages = race / 'prefs/packages'
        race_packages.mkdir(parents=True)
        first_race = race_packages / 'first-old.json'
        second_race = race_packages / 'second-old.json'
        first_race.write_bytes(previous)
        second_race.write_bytes(previous)
        race_script = folder / 'fixture-preview-race.ps1'
        race_script.write_text(
            '$ErrorActionPreference="Stop"\n'
            '$env:PSModulePath=(Join-Path $PSHOME "Modules")+[IO.Path]::PathSeparator+$env:PSModulePath\n. '
            + ps_quote(ROOT / 'installer/legacy-migration.ps1') + '\n' +
            '$plan=New-DshMigrationPlan ' + ps_quote(race / 'install-root') + ' @(' + ps_quote(race_packages) + ") '{}'\n" +
            '[IO.File]::AppendAllText(' + ps_quote(second_race) + '," ")\nInvoke-DshMigration $plan\n',
            encoding='utf-8-sig')
        changed = subprocess.run([*command[:6], str(race_script)], env=environment, capture_output=True, timeout=30)
        assert changed.returncode != 0
        assert first_race.read_bytes() == previous and second_race.read_bytes() == previous + b' ', (
            changed.stderr.decode('utf-8', errors='replace'),
            first_race.stat().st_size, second_race.stat().st_size, len(previous),
            [path.name for path in race_packages.iterdir()])
        assert not (race_packages / 'dsh-houdini.json').exists()
        assert not list(race_packages.glob('*.dsh-disabled-*'))

    assert not folder.exists(), 'all test-owned temporary helpers, reports, backups and fixtures must be cleaned up'
    print('Self-owned temporary install tree removed; no native Houdini/Desktop process was started')

print('Immutable helper install/upgrade/version selection; owned legacy migration; exact-byte rollback/unregister; changed-file guards; unknown-entry and Desktop preservation passed')
