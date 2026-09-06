// tsc does not remove outputs of deleted source files. These are generated
// artifacts only; retired sources/history live outside the production package.
import fs from 'node:fs'
for (const name of ['delivery.js','delivery.d.ts']) {
  const file=new URL(`../lib/${name}`,import.meta.url)
  if(fs.existsSync(file)){fs.rmSync(file);console.log(`removed obsolete build output lib/${name}`)}
}
