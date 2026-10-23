/** Compile declared, pinned dependency source patches into a new exact runtime. */
import fs from 'node:fs';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {spawnSync} from 'node:child_process';
import ts from 'typescript';

const sha = bytes => createHash('sha256').update(bytes).digest('hex');
export function buildDependencyFixes({root, source, target, manifest, files}) {
  const lock = JSON.parse(fs.readFileSync(path.join(target, 'package-lock.json'), 'utf8'));
  for (const fix of manifest.dependencyPatches ?? []) {
    const tree = path.join(path.dirname(source), 'dependencies', fix.id);
    const patchFile = path.join(root, 'deployment/dsh-runtime-fixes', fix.patch);
    const patch = fs.readFileSync(patchFile);
    if (sha(patch) !== fix.patchSha256) throw Error('Dependency patch differs from its declared hash: ' + fix.id);
    // Source-cache preparation and signed release assembly both call this
    // compiler. Fetch and patch the dependency here, through one lifecycle.
    if (!fs.existsSync(tree)) {
      const run = (args, cwd) => {
        const result = spawnSync('git', args, {cwd, stdio: 'inherit', windowsHide: true});
        if (result.error) throw result.error;
        if (result.status !== 0) throw Error('Cannot prepare pinned dependency source: ' + fix.id);
      };
      run(['clone', '--filter=blob:none', '--no-checkout', '--depth', '1', '--branch', fix.tag, fix.repository, tree], root);
      run(['sparse-checkout', 'init', '--cone'], tree);
      run(['sparse-checkout', 'set', fix.source], tree);
      run(['checkout'], tree);
      const revision = spawnSync('git', ['rev-parse', 'HEAD'], {cwd: tree, encoding: 'utf8', windowsHide: true});
      if (revision.status !== 0 || revision.stdout.trim() !== fix.commit) throw Error('Dependency tag differs from pinned revision: ' + fix.id);
      run(['apply', '--check', patchFile], tree); run(['apply', patchFile], tree);
    }
    const revision = spawnSync('git', ['rev-parse', 'HEAD'], {cwd: tree, encoding: 'utf8', windowsHide: true});
    if (revision.status !== 0 || revision.stdout.trim() !== fix.commit) throw Error('Dependency source revision differs: ' + fix.id);
    const width = /^index ([0-9a-f]+)\.\./m.exec(patch.toString('utf8'))?.[1].length ?? 10;
    const diff = spawnSync('git', ['-c', `core.abbrev=${width}`, 'diff', '--binary', 'HEAD'], {cwd: tree, windowsHide: true, maxBuffer: 16 * 1024 * 1024});
    if (diff.status !== 0 || sha(diff.stdout) !== fix.patchSha256) throw Error('Dependency source differs from the declared patch: ' + fix.id);
    const location = path.join(target, 'node_modules', fix.name);
    const installed = JSON.parse(fs.readFileSync(path.join(location, 'package.json'), 'utf8'));
    const locked = lock.packages['node_modules/' + fix.name];
    if (installed.version !== fix.version || locked?.version !== fix.version || locked?.integrity !== fix.integrity) {
      throw Error('Dependency fix requires its exact locked npm package: ' + fix.name);
    }
    const retain = file => { files[path.relative(target, file).replaceAll('\\', '/')] = sha(fs.readFileSync(file)); };
    const options = {target: ts.ScriptTarget.ES2024, module: ts.ModuleKind.ESNext, moduleResolution: ts.ModuleResolutionKind.Bundler,
      rewriteRelativeImportExtensions: true, sourceMap: true, declaration: true};
    for (const entry of fix.entries) {
      const filename = path.join(tree, fix.source, 'src', entry + '.ts');
      const content = fs.readFileSync(filename, 'utf8');
      const compiled = ts.transpileModule(content, {fileName: filename, compilerOptions: options, reportDiagnostics: true});
      const declared = ts.transpileDeclaration(content, {fileName: filename, compilerOptions: options, reportDiagnostics: true});
      const failures = [...(compiled.diagnostics ?? []), ...(declared.diagnostics ?? [])].filter(d => d.category === ts.DiagnosticCategory.Error);
      if (failures.length) throw Error(ts.formatDiagnosticsWithColorAndContext(failures, {
        getCurrentDirectory: () => root, getCanonicalFileName: n => n, getNewLine: () => '\n',
      }));
      const output = path.join(location, 'dist', entry + '.js');
      fs.writeFileSync(output, compiled.outputText); retain(output);
      if (compiled.sourceMapText) { fs.writeFileSync(output + '.map', compiled.sourceMapText); retain(output + '.map'); }
      const declaration = path.join(location, 'dist', entry + '.d.ts');
      fs.writeFileSync(declaration, declared.outputText); retain(declaration);
    }
    const sourcePackage = JSON.parse(fs.readFileSync(path.join(tree, fix.source, 'package.json'), 'utf8'));
    for (const name of fix.additionalDependencies ?? []) {
      const version = sourcePackage.dependencies[name];
      const dependency = JSON.parse(fs.readFileSync(path.join(target, 'node_modules', name, 'package.json'), 'utf8'));
      if (version !== dependency.version || lock.packages['node_modules/' + name]?.version !== version) throw Error('Additional dependency is not exactly locked: ' + name);
      installed.dependencies[name] = version;
    }
    const packageFile = path.join(location, 'package.json');
    fs.writeFileSync(packageFile, JSON.stringify(installed, null, 2) + '\n'); retain(packageFile);
    const proof = path.join(target, 'dsh-runtime-fixes', fix.id);
    fs.mkdirSync(proof, {recursive: true});
    fs.copyFileSync(patchFile, path.join(proof, 'fixes.patch'));
    fs.copyFileSync(path.join(tree, 'LICENSE'), path.join(proof, 'UPSTREAM-LICENSE'));
    console.log('Compiled dependency fix:', fix.name, fix.version);
  }
}
