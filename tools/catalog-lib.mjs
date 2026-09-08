// 词表目录解析：docs/tool-design.md（唯一真相源）→ 按域分组的动词清单。
// tools/trace-report.mjs（复盘报告）与 tools/gen-client-catalog.mjs（构建期
// 注入 client.js）共用本模块——解析规则只维护这里，改一处两边同步。
import fs from 'node:fs';

export function loadCatalog(docFile) {
  const domains = [];
  let cur = null;
  for (const line of fs.readFileSync(docFile, 'utf8').split(/\r?\n/)) {
    // 域标题：### node 域（场景图）/ ### render / sim 域（…）/ ### 类型目录（…）
    // （「N 个域」是章节标题而不是动词域，按「个域」排除）
    const h = line.match(/^###\s+(.+?)\s*$/);
    if (h && ((h[1].includes('域') && !h[1].includes('个域')) || h[1].includes('类型目录'))) {
      cur = { domain: h[1].replace(/（.*?）/g, '').trim(), note: h[1], verbs: [] };
      domains.push(cur);
      continue;
    }
    // 动词行：| `verb(sig)` | 语义 | 返回 |——返回列可能含空格（path 列表/新 path）
    const row = line.match(/^\|\s*`(\w+)\((.*?)\)`\s*\|\s*(.+?)\s*\|\s*([^|]+?)\s*\|$/);
    if (row && cur) {
      cur.verbs.push({ name: row[1], sig: row[2], desc: row[3], returns: row[4], used: 0 });
    }
  }
  return domains;
}
