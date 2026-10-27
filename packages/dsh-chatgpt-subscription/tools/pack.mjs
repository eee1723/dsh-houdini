/** Local candidate only: no registry publication, tag, Release or host writes. */
import fs from 'node:fs/promises'
import path from 'node:path'
import os from 'node:os'
import {fileURLToPath} from 'node:url'
import {spawnSync} from 'node:child_process'
import {existsSync} from 'node:fs'
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..')
const output=path.resolve(process.argv[2]||path.join(root,'out'))
let npmCli=process.env.npm_execpath
if(process.platform==='win32'&&(!npmCli||!existsSync(npmCli))){
  const found=spawnSync('where.exe',['npm.cmd'],{encoding:'utf8',windowsHide:true})
  const launcher=found.stdout?.split(/\r?\n/).find(file=>file.trim())?.trim()
  npmCli=launcher?path.join(path.dirname(launcher),'node_modules/npm/bin/npm-cli.js'):undefined
  if(!npmCli||!existsSync(npmCli))throw Error('Run this packer with npm, or use an ordinary Node/npm installation')
}
function run(args,cwd=root){const command=npmCli?process.execPath:'npm',argv=npmCli?[npmCli,...args]:args
  const r=spawnSync(command,argv,{cwd,encoding:'utf8',shell:false,windowsHide:true});if(r.status!==0)throw Error(r.stderr||r.stdout);return r.stdout}
run(['run','build'])
const inventory=JSON.parse(run(['pack','--dry-run','--ignore-scripts','--json']))[0].files
const stage=await fs.mkdtemp(path.join(os.tmpdir(),'dsh-chatgpt-subscription-package-'))
for(const row of inventory){const to=path.join(stage,row.path);await fs.mkdir(path.dirname(to),{recursive:true});await fs.copyFile(path.join(root,row.path),to)}
const manifest=JSON.parse(await fs.readFile(path.join(stage,'package.json'),'utf8'))
delete manifest.scripts;delete manifest.devDependencies
await fs.writeFile(path.join(stage,'package.json'),JSON.stringify(manifest,null,2)+'\n')
await fs.mkdir(output,{recursive:true})
const result=JSON.parse(run(['pack','--ignore-scripts','--json','--pack-destination',output],stage))[0]
console.log(JSON.stringify({candidate:path.join(output,result.filename),integrity:result.integrity,version:manifest.version,requiresDsh:manifest.engines.dsh},null,2))
