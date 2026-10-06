import assert from "node:assert/strict";
import fs from "node:fs";
import crypto from "node:crypto";
import vm from "node:vm";
import { generatedTraceBlock, resourceIdentity, traceSources } from "../gen-trace-client.mjs";
import { loadCatalog } from "../catalog-lib.mjs";

const lfResource = Buffer.from("中文工具说明\n第二行\n");
const crlfResource = Buffer.from("中文工具说明\r\n第二行\r\n");
for (const extension of ["md", "py", "mjs", "js", "json", "yaml", "yml"]) {
  assert.deepEqual(resourceIdentity(`resource.${extension}`, crlfResource),
    resourceIdentity(`resource.${extension}`, lfResource),
    `${extension} resource inventory must survive Git checkout line-ending changes`);
  assert.equal(resourceIdentity(`resource.${extension}`, crlfResource).bytes, lfResource.length);
}
assert.notEqual(resourceIdentity("resource.md", lfResource).hash,
  resourceIdentity("resource.md", Buffer.from("修改后的工具说明\n第二行\n")).hash);
for (const extension of ["hda", "bin"]) {
  assert.deepEqual(resourceIdentity(`resource.${extension}`, crlfResource), {
    hash: crypto.createHash("sha256").update(crlfResource).digest("hex"),
    bytes: crlfResource.length,
  }, "binary resource inventory must retain original CRLF bytes");
}

const source = fs
  .readFileSync(new URL("../../client.js", import.meta.url), "utf8")
  .replaceAll("\r\n", "\n");
assert(
  source.includes(generatedTraceBlock()),
  "generated Trace runtime and source identities must match current sources",
);
const inventory = traceSources();
assert(inventory.presets.every(p => p.paragraphStarts[0].startsWith('You are ')),
  'persona identity retains the opening used for historical reading groups');
assert(inventory.guidance.bytes > 0);
assert.equal(Object.keys(inventory.tools).length,8);
assert(inventory.presets.every(p => p.bytes > 0 && !('text' in p)));
assert(
  inventory.skills.every((s) => s.files.some((f) => f.path === "SKILL.md")),
);
assert(inventory.skills.every(s => s.files.every(file => !('text' in file))),
  'ordinary client bundles do not duplicate complete skill scripts or references');
const catalog = loadCatalog(
  new URL("../../docs/tool-design.md", import.meta.url),
);
assert(catalog.every((d) => d.verbs.every((v) => v.returns)));
let registration;
let View;
const viewIds=[];
let hooks = [];
let cursor = 0;
let elements = 0;
const React = {
  createElement: (type, props, ...children) => (elements++, {
    type,
    props: props || {},
    children,
  }),
  useState: (initial) => {
    const i = cursor++;
    if (!(i in hooks)) hooks[i] = initial;
    return [
      hooks[i],
      (v) => {
        hooks[i] = v;
      },
    ];
  },
  useMemo: (fn) => fn(),
  useRef: initial => {
    const i=cursor++;
    if (!(i in hooks)) hooks[i]={current:initial};
    return hooks[i];
  },
  useEffect: () => {},
};
vm.runInNewContext(source, {
  window: {
    __ModuleLoader__: {
      load: (r) => {
        registration = r;
      },
    },
  },
});
registration
  .factory((name) => {
    assert.equal(name, "react");
    return React;
  })
  .apply({
    get: (name) =>
      name === "slots"
        ? {
            inject: (_s, fn) => fn(),
            register: (config, component) => {
              if(config.name==='conversation.view')viewIds.push(config.id);
              if (config.id === "houdinitrace") View = component;
            },
          }
        : undefined,
  });
assert.equal(elements, 0, 'registration does not render or initialize Trace');
assert.deepEqual(viewIds,['houdinitrace'],'Houdini has one conversation view; tool information lives in Trace');
View = View({}).type; // Materialize the diagnostic runtime when its view opens.
const t = (text) => [{ type: "text", text }];
// Group the selected request without substituting new source text or dropping unknowns.
const historicalSystem = 'You are an AI agent powered by DeepSeek Harness.\r\n\r\n'
  + 'You are a Houdini automation agent powered by OLD-MODEL. Old requirement.\r\n\r\n'
  + 'UNRECOGNIZED PROVIDER: preserve $HIP and <xml> verbatim.\r\n\r\n'
  + 'Use the read tool — old implementation.\r\n\r\nUse subagent_fork in the background by default.';
const promptSections = View.systemSections(historicalSystem);
assert.equal(promptSections.map(s=>s.text).join(''), historicalSystem);
assert.equal(promptSections.length,5);
assert.equal(promptSections[2].category,'其他／来源未识别');
assert.equal(promptSections[1].source,'presets/houdini/persona.md');
assert(promptSections[4].source.includes('toolName=subagent_fork'));
assert(!promptSections.some(s=>s.text.includes('glm-5.3-flash')));
assert.equal(View.systemSections('').length,0);
assert.equal(View.systemSections('Houdini outputs belong under $HIP; historical relay rule.')[0].source,'src/index.ts · dsh-houdini:guidance');
const req = {
  purpose: "assistant",
  turn: 1,
  step: 1,
  startSeq: 2,
  startedAt: 100,
  status: "complete",
  completedAt: 200,
  resultSeq: 3,
  prompt: {
    config: { model: "test" },
    system: "HISTORICAL SYSTEM",
    tools: [
      {
        name: "skill",
        description: "old skill description",
        parameters: { type: "object" },
      },
      { name: "houdini_exec", description: "execute" },
    ],
  },
  usage: {
    inputTokens: 100,
    cacheReadTokens: 200,
    cacheWriteTokens: 10,
    outputTokens: 20,
    reasoningTokens: 5,
  },
};
const request2 = {
  ...req,
  step: 2,
  startSeq: 12,
  startedAt: 500,
  resultSeq: 13,
  prompt: { ...req.prompt, system: "NEW SYSTEM" },
  usage: undefined,
};
const call = (id, name, args) => ({
  kind: "tool-call",
  callId: id,
  name,
  argsRaw: JSON.stringify(args),
});
const success =
  'Executed successfully.\n\ntransaction:\n{"status":"committed"}\n\noperation-evidence:\n{"checks":{"ok":true},"output":"/obj/test/OUT"}\n\n__result__:\n{"value":1}\n\nverbs (1):\n1. [ok] set_parms(["/obj/test", {"height":2}]) -> {"set":["height"]} (4ms)';
const result = (id, name, seq, time, raw = success) => ({
  kind: "tool-result",
  seq,
  time,
  callId: id,
  callTime: id === "b" ? 300 : 210,
  call: { name, argsRaw: "{}" },
  content: t(raw),
  isError: false,
  subCalls: [],
});
const snapshot = {
  requests: [req, req, request2],
  runningCalls: [
    {
      callId: "b",
      name: "houdini_exec",
      turn: 1,
      step: 1,
      argsRaw: "{}",
      time: 300,
    },
    {
      callId: "pending",
      name: "houdini_query",
      turn: 1,
      step: 2,
      argsRaw: "{}",
      time: 510,
    },
  ],
  eventNodes: [
    {
      kind: "context",
      seq: 1,
      time: 90,
      source: {
        kind: "skill-catalog",
        entries: [
          { name: "houdini-sop-workflow", description: "old description" },
        ],
      },
      content: t("catalog"),
    },
    {
      kind: "assistant",
      seq: 3,
      time: 200,
      turn: 1,
      step: 1,
      blocks: [
        call("a", "skill", { name: "houdini-sop-workflow" }),
        call("b", "houdini_exec", {}),
      ],
    },
    result("b", "houdini_exec", 5, 320),
    {
      ...result("a", "skill", 6, 400, "OLD SKILL BODY"),
      call: {
        name: "skill",
        argsRaw: JSON.stringify({ name: "houdini-sop-workflow" }),
      },
    },
    result("a", "skill", 8, 450, "REPLAY MUST NOT REPLACE ORIGINAL"),
    {
      kind: "assistant",
      seq: 13,
      time: 505,
      turn: 1,
      step: 2,
      blocks: [call("pending", "houdini_query", {})],
    },
    {
      ...result("failure", "read", 14, 520, "permission denied"),
      isError: true,
    },
  ],
};
const data = View.model(snapshot);
assert.equal(data.requests.length, 2, "deduplicate request usage");
assert.equal(data.statistics.requestUsage.reported, 1);
assert.equal(data.statistics.requestUsage.input, 310);
assert.equal(data.statistics.knownToolCount,8);
assert.equal(data.statistics.usedToolCount,1);
assert.equal(data.statistics.toolCalls,1,'current tool catalog summary excludes legacy names, retained in request visibility');
assert.equal(data.statistics.toolUsage.get('houdini_exec').calls,1,'replayed and stale running results do not inflate counts');
assert.equal(data.statistics.toolUsage.get('houdini_query').pending,1);
assert.equal(data.statistics.verbUsage.get('set_parms').calls,1);
assert.equal(data.statistics.verbCalls,1);
assert.equal(
  data.entries.length,
  4,
  "deduplicate replay and stale running call",
);
assert.equal(
  data.entries[0].id,
  "a",
  "call start order must survive out-of-order result arrival",
);
assert.equal(data.entries[0].text, "OLD SKILL BODY");
assert.equal(
  data.entries[0].accounting.input,
  310,
  "DSH input buckets are disjoint",
);
const executed = data.entries.find((e) => e.id === "b");
assert.equal(
  executed.requestKey,
  data.entries[0].requestKey,
  "parallel calls share one request",
);
assert.equal(executed.transaction.status, "committed");
assert.equal(executed.evidence.output, "/obj/test/OUT");
assert.deepEqual(
  JSON.parse(JSON.stringify(executed.resultValue)),
  { value: 1 },
  "result must not swallow operation-evidence",
);
assert.equal(
  data.entries.find((e) => e.id === "failure").failed,
  true,
  "isError must not require English failure text",
);
assert.equal(
  data.entries.find((e) => e.id === "pending").accounting,
  null,
  "missing usage is not zero",
);
assert.equal(View.usage({ inputTokens: -1, outputTokens: 0 }), null);
const orphan = View.model({
  eventNodes: [{ ...result("orphan", null, 100, 600), call: null }],
  requests: [req],
});
assert.equal(
  orphan.entries[0].request,
  null,
  "do not infer request by adjacent time",
);
const retries = View.model({
  requests: [req, {...req, startSeq: 10, resultSeq: undefined, status: 'running'},
    {...req, startSeq: 20, resultSeq: 21}],
  eventNodes: [
    ...[[3, 'first'], [12, 'retry'], [21, 'latest']].map(([seq, id]) => ({
      kind: 'assistant', turn: 1, step: 1, seq, blocks: [call(id, 'read', {})],
    })),
    ...[[4, 'first'], [14, 'retry'], [22, 'latest']].map(([seq, id]) => result(id, 'read', seq, seq, 'ok')),
  ],
});
assert.equal(retries.entriesById.get('first').requestKey, 'assistant:2');
assert.equal(retries.entriesById.get('retry').requestKey, 'assistant:2',
  'an unfinished retry keeps the latest completed request before the call');
assert.equal(retries.entriesById.get('latest').requestKey, 'assistant:20',
  'the request index preserves exact result associations and excludes future requests');
const resourceSnapshot = {
  eventNodes: [
    {
      ...result(
        "load",
        "skill",
        1,
        100,
        '<skill_content name="sop">\nBase directory for this skill: E:/skills/sop\n</skill_content>',
      ),
      call: { name: "skill", argsRaw: '{"name":"sop"}' },
    },
    {
      ...result("inside", "read", 2, 200, "resource body"),
      call: {
        name: "read",
        argsRaw: '{"file_path":"E:/skills/sop/references/rules.md"}',
      },
    },
    {
      ...result("outside", "read", 3, 300, "same filename"),
      call: { name: "read", argsRaw: '{"file_path":"E:/elsewhere/rules.md"}' },
    },
    {
      ...result("relative", "read", 4, 400, "relative path"),
      call: { name: "read", argsRaw: '{"file_path":"references/rules.md"}' },
    },
  ],
};
const reads = View.model(resourceSnapshot).resourceReads;
assert.equal(
  reads.length,
  1,
  "only exact absolute resource paths may be attributed",
);
assert.equal(reads[0].path, "references/rules.md");
assert.equal(reads[0].version, "未采集");
const child = result("child", "houdini_query", 7, 420);
const childData = View.model({
  requests: [req],
  eventNodes: [
    snapshot.eventNodes[1],
    {
      ...result("b", "houdini_exec", 5, 320),
      subCalls: [
        { callId: "child", name: "houdini_query", argsRaw: "{}", time: 310 },
      ],
    },
    child,
  ],
});
assert.equal(
  childData.entries.find((e) => e.id === "child").pending,
  false,
  "settled child wins over parent pending snapshot",
);
assert.equal(
  childData.entries.find((e) => e.id === "child").parent,
  "b",
  "retain parent relation from pending child projection",
);
assert.equal(
  childData.entries.find((e) => e.id === "child").requestKey,
  "assistant:2",
);
assert.doesNotThrow(() =>
  View.model({
    eventNodes: [
      {
        ...result("null", "read", 1, 100),
        call: { name: "read", argsRaw: "null" },
      },
    ],
  }),
);
const controls = View.model({
  eventNodes: [
    result(
      "controls",
      "houdini_exec",
      1,
      100,
      [
        "Executed successfully.",
        'transaction:\n{"status":"committed"}',
        'control-test-summary (not_run is not pass):\n[{"status":"fail"}]',
        'operation-evidence:\n[{"verb":"test_controls","control_summary":{"status":"fail"}}]',
        'CHECKS NEED ATTENTION (execution success is not validation success):\n[{"ok":false}]',
        '__result__:\n{"value":1}',
      ].join("\n\n"),
    ),
  ],
}).entries[0];
assert.equal(controls.transaction.status, "committed");
assert.equal(
  controls.evidence[0].control_summary.status,
  "fail",
  "Host headers must not be swallowed into preceding JSON",
);
assert.equal(controls.resultValue.value, 1);
const recovery = View.model({
  eventNodes: [
    result(
      "recovery",
      "houdini_exec",
      1,
      100,
      'Execution failed:\nbad\n\ntransaction:\n{"status":"recovery_unverified"}\n\nrollback:\n{"applied":true,"error":"restore failed"}',
    ),
  ],
}).entries[0];
assert.equal(
  recovery.rollbackApplied,
  false,
  "failed recovery is not a successful rollback",
);

let selectedSnapshot=snapshot,selectedSession='fixture';
function render() {
  cursor = 0;
  return View({
    sessionId: selectedSession,
    useTrajectory: (select) => select(selectedSnapshot),
  });
}
function content(n) {
  if (n == null) return "";
  if (typeof n !== "object") return String(n);
  if (Array.isArray(n)) return n.map(content).join(" ");
  if (n.type === "style") return "";
  return n.children.map(content).join(" ");
}
function all(n) {
  return n && typeof n === "object"
    ? Array.isArray(n)
      ? n.flatMap(all)
      : [n, ...n.children.flatMap(all)]
    : [];
}
function click(label) {
  const tree = render();
  const b = all(tree).find((n) => n.type === "button" && content(n) === label);
  assert(b, "missing button " + label);
  b.props.onClick();
  return render();
}
let tree = render();
const primaryNav = all(tree).find(n => n.type === 'nav');
const activePage = tree => all(all(tree).find(n=>n.type==='nav')).filter(n=>n.type==='button' && n.props['aria-pressed']).map(content);
assert.deepEqual(all(primaryNav).filter(n => n.type === 'button').map(content), ['执行记录', '能力资料', '高级诊断']);
assert.deepEqual(activePage(tree), ['执行记录']);
assert(!all(tree).some(n => n.type === 'button' && content(n) === '上一页'), 'single-page traces omit pagination controls');
assert(!all(tree).some(n => n.props.className === 'tr-call-tokens'), 'model usage is not repeated on every call');
assert(!content(tree).includes('颜色区分工具用途'), 'reading the timeline needs no color legend');
tree = click("高级诊断");
assert.deepEqual(activePage(tree), ['高级诊断'], 'primary selection matches the content immediately');
assert.match(content(tree), /NEW SYSTEM/);
const picker = all(tree).find((n) => n.type === "select");
picker.props.onChange({ target: { value: "assistant:2" } });
assert.match(content(render()), /HISTORICAL SYSTEM/);
assert(all(render()).filter(n=>n.type==='details' && /tr-prompt-/.test(n.props.className||'')).every(n=>!n.props.open),'prompt groups and bodies default closed');
assert(
  !content(render()).includes("NEW SYSTEM"),
  "history must not silently use latest header",
);
tree = click("本次工具定义");
assert.match(content(tree), /old skill description/);
tree = click("能力资料");
assert.deepEqual(activePage(tree), ['能力资料'], 'changing groups clears the old primary selection');
tree = click("技能");
assert.deepEqual(activePage(tree), ['能力资料'], 'the skills page belongs to the same capability group');
assert.match(content(tree), /old description/);
assert.match(content(tree), /OLD SKILL BODY/);
assert(!content(tree).includes("REPLAY MUST NOT REPLACE ORIGINAL"));
assert.equal(all(tree).find(n=>n.props['aria-label']==='技能加载命令').props.value,'/houdini-sop-workflow');
assert.match(content(tree),/正文返回 1 次/);
assert.match(content(tree),/当前上下文是否仍保留正文未采集/);
tree = click("工具");
assert.match(content(tree),/当前包提供 8 个工具/);
assert.match(content(tree),/本任务已用 1 个/);
for(const [name,tool] of Object.entries(inventory.tools)) {
  assert(content(tree).includes(name),'full tool catalog includes '+name);
  assert(content(tree).includes(tool.purpose),'tool purpose comes from the shared catalog');
  assert(content(tree).includes(tool.input)&&content(tree).includes(tool.output));
}
assert.match(content(tree),/本任务调用 1 次/);
tree=click('动词目录');
assert.match(content(tree), /返回类型/);
assert.match(content(tree), /build_module/);
assert.match(content(tree),/本任务执行 0 次/);
tree=click('请求可见工具');
assert.match(content(tree),/houdini_query/,'legacy tools stay visible through historical requests/calls');
selectedSnapshot={};selectedSession='empty-fixture';
tree=click('工具目录');
assert.equal((content(tree).match(/本任务调用 0 次/g)||[]).length,8,'another selected task does not inherit usage');
tree=click('技能');
assert(!content(tree).includes('正文返回 1 次'),'current package skills do not become actual loads in a fresh task');
selectedSnapshot=snapshot;selectedSession='fixture';
tree = click("高级诊断");
tree = click("执行统计");
assert.match(content(tree), /310/);
assert.match(content(tree), /1 \/ 2/);
tree = click("执行记录");
assert(
  !content(tree).includes("成功修改含动词"),
  "analysis separated from timeline",
);
console.log(
  "Trace view: real public snapshot, usage, replay, history, inventory and board interactions passed",
);

// Large traces keep navigation outside either scrolling pane, with stable pages.
const toolTypes = [['get_goal','planning'],['create_goal','planning'],['bash','shell'],['write','write'],['web_search','search'],['ask_user_question','interaction'],['vendor_tool','other']];
const classifications=View.model({eventNodes:toolTypes.map(([name],i)=>result('type'+i,name,i+1,i+1,'ok'))}).entries;
toolTypes.forEach(([name,kind])=>assert.equal(classifications.find(e=>e.name===name).kind,kind));
for(let i=0;i<120;i++)snapshot.eventNodes.push({...result('long'+i,toolTypes[i%toolTypes.length][0],100+i,1000+i,'ok'),callTime:900+i});
const callRows=tree=>all(tree).filter(n=>n.type==='button'&&n.props.className==='tr-call-row');
tree=render();
assert.equal(callRows(tree).length,24,'latest page has the remaining 24 calls');
assert.match(content(tree),/101–124 \/ 124/);
tree=click('上一页');assert.equal(callRows(tree).length,50);assert.match(content(tree),/51–100 \/ 124/);
const pagePicker=all(tree).find(n=>n.type==='select'&&n.props['aria-label']==='选择步骤页码');
pagePicker.props.onChange({target:{value:'0'}});tree=render();
assert.match(content(tree),/1–50 \/ 124/);
assert.equal(all(tree).find(n=>n.type==='button'&&content(n)==='上一页').props.disabled,true);
const toolbar=all(tree).find(n=>n.props.className==='tr-timeline-toolbar');
assert(all(toolbar).some(n=>n.props['aria-label']==='选择步骤页码'),'page picker stays in toolbar');
const list=all(tree).find(n=>n.props.className==='tr-call-list');
assert(!all(list).some(n=>n.type==='select'),'paging never moves to list bottom');
assert(callRows(tree).every(n=>n.children.length===2),'compact call layout has exactly two rows');
callRows(tree)[0].props.onClick();tree=render();
assert(all(tree).some(n=>n.props.className==='tr-timeline tr-detail-open'));
tree=click('← 返回步骤列表');assert(all(tree).some(n=>n.props.className==='tr-timeline'));
tree=click('最新');assert.match(content(tree),/101–124 \/ 124/);
const listNode=t=>all(t).find(n=>n.props.className==='tr-call-list');
let scrollPosition=0;
let scrollWrites=0;
const scrollElement={scrollHeight:5000,clientHeight:400,get scrollTop(){return scrollPosition;},set scrollTop(value){scrollWrites++;scrollPosition=Math.min(value,this.scrollHeight-this.clientHeight);}};
listNode(tree).props.ref(scrollElement);
assert.equal(scrollPosition,4600,'Latest performs one requested initial scroll');
scrollPosition=1200; // User moved upward before another snapshot render.
const writesAfterJump=scrollWrites;
for(let i=0;i<3;i++){tree=render();listNode(tree).props.ref(scrollElement);}
assert.equal(scrollPosition,1200,'snapshot rerenders must not snap back to the last row');
assert.equal(scrollWrites,writesAfterJump,'no repeated ref-driven scroll writes');
assert(callRows(tree).every(n=>!n.props.ref),'individual rows never force list scrolling');
tree=click('最新');assert.equal(scrollPosition,4600,'Latest can be clicked again without changing the page');
listNode(tree).props.onWheel({deltaY:-40});tree=render();
assert.equal(all(tree).find(n=>n.type==='button'&&content(n)==='最新').props['aria-pressed'],false,'upward wheel pins the current page');
for(let i=0;i<27;i++)snapshot.eventNodes.push({...result('new'+i,'get_goal',300+i,3000+i,'ok'),callTime:2900+i});
tree=render();assert.match(content(tree),/101–150 \/ 151/,'new page must not displace a manually inspected page');
tree=click('最新');assert.match(content(tree),/151–151 \/ 151/);
listNode(tree).props.ref(scrollElement);
scrollPosition=1000;listNode(tree).props.onScroll({currentTarget:scrollElement});tree=render();
assert.equal(all(tree).find(n=>n.type==='button'&&content(n)==='最新').props['aria-pressed'],false,'scrollbar/touch movement also pins the page');
assert.equal(View.model({eventNodes:[result('ok','read',1,10,'ok')]}).entries[0].state,'已成功');
assert.equal(data.entries.find(e=>e.id==='failure').state,'失败');
const retainedEntry=View.model({eventNodes:[{...result('retained','houdini_exec',1,10,'Executed successfully.\n\n__result__:\n{"omitted":true}'),
  meta:{canonical:{ok:true,transaction:{status:'committed'},result:{output:'/obj/retained/OUT'},
    verbs:[{verb:'set_parms',ok:true,args:['/obj/retained',{snippet:'full canonical source'}],kwargs:{},result:{ok:true},ms:1}],
    evidence:[{verb:'verify_network',output:'/obj/retained/OUT',ok:true}]}}}]}).entries[0];
assert.equal(retainedEntry.resultValue.output,'/obj/retained/OUT');
assert.ok(retainedEntry.verbs[0].argsText.includes('full canonical source'));
assert.equal(retainedEntry.evidence[0].ok,true,'UI uses complete audit metadata, not compact placeholders');
const detailRead=View.model({eventNodes:[{...result('detail','houdini_query',2,20,'Executed successfully.'),
  call:{name:'houdini_query',argsRaw:JSON.stringify({result_ref:'a'.repeat(64)})}}]}).entries[0];
assert.equal(detailRead.kind,'read');
assert.equal(detailRead.title,'读取历史工具结果');
const recoveredRequest=View.model({eventNodes:[{...result('recover','houdini_query',3,30,'Executed successfully.'),
  call:{name:'houdini_query',argsRaw:JSON.stringify({request_ref:'a'.repeat(32)+'.'+'b'.repeat(32)})},
  meta:{canonical:{ok:true,requestReceipt:{status:'done',retrieved:true},verbs:[{verb:'set_parm',ok:true,args:[],result:{value:1},ms:1}]}}}]}).entries[0];
assert.equal(recoveredRequest.verbs.length,0,'recovered execution is not a second mutation in the timeline');
assert.equal(recoveredRequest.title,'查回原请求');
// Request transport/admission and background execution are not scene success.
// Top-level canonical job identities also connect submit/status/cancel records.
for (const [name, canonical, expected] of [
  ['houdini_job_submit',{jobId:'job-fixture',requestReceipt:{status:'job_submitted'}},'后台任务已提交'],
  ['houdini_job_status',{ok:true,jobId:'job-fixture',status:'queued'},'后台任务排队中'],
  ['houdini_job_status',{ok:true,jobId:'job-fixture',status:'running'},'后台任务执行中'],
  ['houdini_job_cancel',{ok:false,jobId:'job-fixture',status:'cancelled'},'后台任务已取消'],
  ['houdini_job_submit',{error:'lost response',requestReceipt:{status:'unknown_transport'}},'结果未知 · 需要查回'],
  ['houdini_request',{ok:true,requestReceipt:{status:'not_executed'}},'未执行'],
  ['houdini_request',{ok:true,requestReceipt:{status:'result_expired'}},'已结束 · 结果已过期'],
  ['houdini_request',{ok:true,requestReceipt:{status:'result_unavailable'}},'已结束 · 结果不可用'],
]) {
  const entry = View.model({eventNodes:[{...result('state-fixture',name,1,10),meta:{canonical}}]}).entries[0];
  assert.equal(entry.state,expected);
  if(canonical.jobId) assert.equal(entry.jobId,canonical.jobId);
  if(['unknown_transport','result_expired','result_unavailable'].includes(canonical.requestReceipt?.status))
    assert.equal(entry.attention,true,'uncertain/unavailable outcomes remain in the attention filter');
}
const historicalReceipt = View.model({eventNodes:[result('old-receipt','houdini_request',1,10,
  'Request receipt status: unknown.\n\nrequest-receipt:\n{"status":"unknown"}\n\nexecution-observation:\n{"hip_dir":null}\n\nresult-details:\n{"stored":false}')]}).entries[0];
assert.equal(historicalReceipt.state,'请求结果未知','plain historical recovery receipts keep their explicit status');
assert.equal(historicalReceipt.requestReceipt.status,'unknown');
const sameExecution={ok:false,execution:{runtime_id:'runtime',sequence:1},verbs:[
  {verb:'set_parms',ok:true,args:[],ms:1},{verb:'set_parms',ok:false,args:[],error:'bad parameter',ms:1},
]};
const counted=View.model({eventNodes:[
  {...result('counted','houdini_exec',1,10),meta:{canonical:sameExecution}},
  {...result('replayed','houdini_exec',2,20),meta:{canonical:sameExecution}},
],runningCalls:[{callId:'still-running',name:'houdini_exec',argsRaw:'{}',time:30}]}).statistics;
assert.equal(counted.toolUsage.get('houdini_exec').calls,3,'count distinct tool invocations including pending and failed calls');
assert.equal(counted.toolUsage.get('houdini_exec').failed,2);
assert.equal(counted.toolUsage.get('houdini_exec').pending,1);
assert.equal(counted.verbUsage.get('set_parms').calls,2,'count each recorded action while deduplicating an execution replay');
assert.equal(counted.verbUsage.get('set_parms').failed,1);
const sourceRead=View.model({eventNodes:[{...result('source','houdini_query',3,30,'Executed successfully.'),
  call:{name:'houdini_query',argsRaw:JSON.stringify({source_ref:'index'})}}]}).entries[0];
assert.equal(sourceRead.kind,'read');
assert.equal(sourceRead.title,'读取原始任务来源');
tree=click('需要关注');assert.equal(callRows(tree).length,1);assert.match(content(tree),/permission denied/);
const rawDetail=all(tree).find(n=>n.type==='details' && n.props.className==='tr-raw');
assert(rawDetail && !rawDetail.props.open && content(rawDetail).includes('调用标识：failure'), 'raw identifiers remain available in a closed disclosure');
const usageDetail=all(tree).find(n=>n.type==='details' && content(n.children[0])==='关联模型请求');
assert(usageDetail && !usageDetail.props.open, 'model usage is available on demand');
console.log('Trace navigation: focused timeline, conditional pagination, accessible details and grouped diagnostics passed');

// Exercise the actual detail renderer, not only the parsed model. Failed Bridge
// ledger rows legitimately carry error/summary with no result at all.
const detailCases = [
  {verb:'set_parms',ok:false,args:[],kwargs:{},error:'fixture parameter rejected',ms:0,
    summary:{dispatched:false,scene_writes:0}},
  {verb:'verify_network',ok:false,args:['/obj/g'],error:'fixture checkpoint failed',ms:2,
    result:null,summary:{status:'failed',output:'/obj/g/OUT'}},
  {verb:'read_parms',ok:true,args:[],result:null,ms:1},
  {verb:'unknown',ok:true,ms:1},
  {verb:'read_parms',ok:true,args:[],result:false,ms:1},
  {verb:'read_parms',ok:true,args:[],result:0,ms:1},
  {verb:'read_parms',ok:true,args:[],result:'',ms:1},
  {name:'do-not-infer-a-verb',ok:false,error:'fixture missing operation fields'},
  {result:null},
];
for (const [i, ledger] of detailCases.entries()) {
  hooks=[];
  snapshot.runningCalls=[];
  snapshot.eventNodes=[{...result('detail-case-'+i,'houdini_exec',1,10,'Executed successfully.'),
    meta:{canonical:{ok:ledger.ok ?? true,verbs:[ledger]}}}];
  const before=JSON.stringify(snapshot);
  const entry=View.model(snapshot).entries[0];
  tree=render();callRows(tree)[0].props.onClick();tree=render();
  const displayed=content(tree);
  if(ledger.error) assert(displayed.includes(ledger.error),'keep actual failure reason visible');
  if(ledger.summary) assert(displayed.includes('补充证据') && displayed.includes('scene_writes' in ledger.summary ? 'scene_writes' : '/obj/g/OUT'));
  if(!Object.hasOwn(ledger,'result')) assert(displayed.includes('返回值未记录'),'missing is not a successful null return');
  else assert.equal(entry.verbs[0].detail,JSON.stringify(ledger.result));
  if (!ledger.verb) {
    assert(displayed.includes('操作名称未记录'), 'incomplete public operation receipts have an explicit missing-name label');
    assert(!displayed.includes('do-not-infer-a-verb'), 'a foreign name field is not evidence of an operation name');
    assert(!all(tree).some(n=>n.type==='button' && content(n)==='查看动词契约 →'), 'missing names do not produce dead contract links');
  }
  if (ledger.ms == null) assert(displayed.includes('耗时未记录'), 'missing elapsed time is not displayed as undefined or zero');
  if (ledger.ok == null) assert(displayed.includes('状态未记录'), 'a missing operation status is not called a failure');
  assert(!displayed.includes('undefined'), 'missing public fields never leak JavaScript sentinels into display text');
  assert.equal(JSON.stringify(snapshot),before,'rendering cannot rewrite canonical evidence');
  tree=click('← 返回步骤列表');
  assert.equal(callRows(tree).length,1,'a failure detail must not remove the trace');
}
console.log('Trace failed-detail rendering: missing/null/falsy returns, errors, summaries and back navigation passed');

// The generated UI and offline reports share the raw-effect classifier.
const effectCases=[
  ['blocked-backup','houdini_exec',{code:'copy_backup()'},false,'blocked','gate_blocked'],
  ['blocked-query','houdini_query',{code:'change_path()'},false,'read_only_blocked','gate_blocked'],
  ['dynamic','houdini_exec',{code:'runtime.check()'},true,'read_only','unknown'],
  ['readonly','houdini_query',{code:'hou.frame()'},true,'read_only','read_only_query'],
  ['detail-history','houdini_query',{result_ref:'stored'},true,'blocked',null],
];
const effectNodes=effectCases.map(([id,name,args,ok,gateOutcome],i)=>({
  ...result(id,name,i+1,10+i,'See retained result.'),
  call:{name,argsRaw:JSON.stringify(args)},
  meta:{canonical:{ok,verbs:[],transaction:{status:'no_scene_change'},rawUsage:{gateOutcome}}},
}));
const effectEntries=View.model({eventNodes:effectNodes}).entries;
for(const [id,, , , ,expected] of effectCases) {
  assert.equal(effectEntries.find(e=>e.id===id).rawEffect,expected);
}
assert.equal(effectEntries.find(e=>e.id==='blocked-query').state,'Gate 拦截');
assert.equal(effectEntries.find(e=>e.id==='detail-history').gateBlocked,false,'historical blocked receipts are not new Gate rejections');
hooks=[];snapshot.runningCalls=[];snapshot.eventNodes=effectNodes;
tree=render();tree=click('高级诊断');tree=click('执行统计');
assert.match(content(tree),/无动词副作用未知/);
assert.match(content(tree),/Host 历史结果 \/ 来源回读/);
console.log('Trace UI raw effects: canonical blocked query/exec, dynamic unknown, historical detail exclusion passed');

const caughtOutcome={batch:'completed',operations:{total:2,failed:1},checks:{failed:0,warning:0,unverified:0}};
const returnedCheckOutcome={batch:'completed',operations:{total:1,failed:0},checks:{failed:1,warning:0,unverified:0}};
const caughtCanonical={ok:true,result:{fallback:[]},outcome:caughtOutcome,
  execution:{runtime_id:'outcome-fixture',sequence:1},transaction:{status:'no_scene_change'},
  verbs:[{verb:'describe',ok:false,error:'missing node',args:[],ms:1},
    {verb:'find_nodes',ok:true,result:[],args:[],ms:1}]};
const outcomeModel=View.model({eventNodes:[
  {...result('caught-read','houdini_inspect',1,10),meta:{canonical:caughtCanonical}},
  {...result('failed-check','houdini_exec',2,20),meta:{canonical:{ok:true,outcome:returnedCheckOutcome,
    verbs:[{verb:'verify_network',ok:true,check_status:'failed',result:{ok:false},args:[],ms:1}]}}},
  {...result('retrieved-caught','houdini_request',3,30),meta:{canonical:{...caughtCanonical,requestReceipt:{retrieved:true,status:'done'}}}},
]});
assert.equal(outcomeModel.entries[0].failed,false,'a caught read does not become a tool failure');
assert.equal(outcomeModel.entries[0].state,'已完成 · 子操作失败');
assert.equal(outcomeModel.entries[1].state,'已完成 · 检查未通过');
assert.equal(outcomeModel.statistics.failedToolCalls,0);
assert.equal(outcomeModel.statistics.failedVerbCalls,1);
assert.equal(outcomeModel.statistics.operationAttentionCalls,1,'retrieved receipt does not count operations again');
assert.equal(outcomeModel.statistics.checkAttentionCalls,1,'raised operations are not returned failed checks');
assert.equal(outcomeModel.statistics.verbCalls,3);
const legacyCaught=View.model({eventNodes:[{...result('legacy-caught','houdini_exec',1,10),
  meta:{canonical:{ok:true,verbs: caughtCanonical.verbs}}}]}).entries[0];
assert.equal(legacyCaught.state,'已完成 · 子操作失败','old records use direct ledger errors without inventing checks');
assert.equal(legacyCaught.checkCounts,null);
const textOutcome=View.model({eventNodes:[result('text-outcome','houdini_exec',1,10,
  'Batch completed; one or more operations raised errors.\n\nexecution-outcome:\n'+JSON.stringify(caughtOutcome)
  +'\n\noperation-errors:\n[{"verb":"describe","error":"missing node"}]')]}).entries[0];
assert.equal(textOutcome.state,'已完成 · 子操作失败','text-only projection preserves the producer outcome');
assert.equal(textOutcome.failed,false);
console.log('Trace separates batch, caught operation and returned check outcomes without recounting recovery receipts');
const nestedId='p:ptc:1', nestedFacts={ok:true,result:{actual:1},verbs:[],execution:{read_only:true}};
const nestedNode={...result(nestedId,'houdini_inspect',21,21),callId:nestedId,
  call:{name:'houdini_inspect',argsRaw:'{"code":"__result__=hou.frame()"}'},
  content:[{type:'text',text:JSON.stringify({kind:'dsh-houdini/execution-v1',callId:nestedId,tool:'houdini_inspect',value:nestedFacts})}]};
assert.equal(View.model({eventNodes:[nestedNode]}).entries[0].resultValue.actual,1);
assert.equal(View.model({eventNodes:[nestedNode]}).entries[0].rawEffect,'read_only_query');

// Classification comes only from the receipt. Later successful calls cannot
// erase a historical failure or certify a model's semantic correctness.
const checkCases = ['failed','warning','unverified'].map((status,i) => ({
  ...result('check-'+status,'houdini_exec',i+1,(i+1)*10,'Executed successfully.'),
  meta:{canonical:{ok:true,outcome:{batch:'completed',operations:{total:1,failed:0},
    checks:{failed:0,warning:0,unverified:0,[status]:1}},
    verbs:[{verb:'verify_network',ok:true,args:[],check_status:status,
      result:{validation:{output:'/obj/check/OUT',warnings:['fixture diagnostic '+status]}}}]}}
}));
const cleanSemantic={...result('clean-semantic','houdini_exec',4,40,'Executed successfully.'),
  meta:{canonical:{ok:true,outcome:{batch:'completed',operations:{total:1,failed:0},checks:{failed:0,warning:0,unverified:0}},
    verbs:[{verb:'render_view',ok:true,args:[],check_status:'passed',result:{semantic_status:'unverified'}}]}}};
const checksSnapshot={eventNodes:[...checkCases,cleanSemantic]};
const checksModel=View.model(checksSnapshot);
assert.equal(checksModel.entries[0].state,'已完成 · 检查未通过');
assert.equal(checksModel.entries[1].state,'已完成 · 检查有警告');
assert.equal(checksModel.entries[2].state,'已完成 · 检查未验证');
assert.equal(checksModel.entries[3].attention,false,'semantic unknown is not a producer check failure');
assert.deepEqual(Array.from(checksModel.entries.slice(0,3),e=>e.attentionLevel),['error','warning','unknown']);
assert.equal(checksModel.entries[1].checkFindings[0].target,'/obj/check/OUT');
assert.equal(checksModel.entries[1].checkFindings[0].reason,'fixture diagnostic warning');
hooks=[];selectedSnapshot=checksSnapshot;
tree=render();tree=click('需要关注');
assert.equal(callRows(tree).length,3);
assert.match(content(tree),/历史记录不代表当前仍未修复/);
callRows(tree)[1].props.onClick();tree=render();
assert.match(content(tree),/检查有警告 1 项/);
assert.match(content(tree),/fixture diagnostic warning/);
assert.match(content(tree),/\/obj\/check\/OUT/);
assert(all(tree).some(n=>n.props.className==='tr-attention tr-attention-warning'));
const textChecks=View.model({eventNodes:[result('text-checks','houdini_exec',1,10,
  'Executed successfully.\n\nexecution-outcome:\n'+JSON.stringify(returnedCheckOutcome)
  +'\n\nchecks:\n[{"verb":"test_controls","status":"failed"}]')]}).entries[0];
assert.equal(textChecks.checkFindings[0].label,'检查未通过');
assert.equal(textChecks.checkFindings[0].reason,null,'absent reasons are not inferred');
const summaryOnly={...result('summary-only','houdini_exec',1,10,'Executed successfully.'),
  meta:{canonical:{ok:true,outcome:returnedCheckOutcome}}};
hooks=[];selectedSnapshot={eventNodes:[summaryOnly]};
tree=render();callRows(tree)[0].props.onClick();tree=render();
assert.match(content(tree),/回执只提供检查计数/);
const nestedCheckId='parent:ptc:check', nestedCheck={...checkCases[1],callId:nestedCheckId,meta:undefined,
  content:t(JSON.stringify({kind:'dsh-houdini/execution-v1',callId:nestedCheckId,tool:'houdini_exec',value:checkCases[1].meta.canonical}))};
assert.equal(View.model({eventNodes:[nestedCheck]}).entries[0].checkFindings[0].reason,'fixture diagnostic warning');
console.log('Trace attention: reasons, unknown scope, nested/text receipts and historical failure preservation passed');
for (const [verb, facts, target, reason] of [
  ['build_module',{validation:{output:'/obj/fixture/OUT',issues:[{path:'/obj/fixture/source',warnings:['channel source absent']}]}},'/obj/fixture/OUT','/obj/fixture/source channel source absent'],
  ['geo_piece_stats',{node:'/obj/fixture/shape',risk_reasons:['duplicate_boundary_faces']},'/obj/fixture/shape','duplicate_boundary_faces'],
  ['test_controls',{output:'/obj/fixture/OUT',control_summary:{failures:[{id:'width',status:'fail'}]}},'/obj/fixture/OUT','测试 width：fail'],
]) {
  const node={...result('structured-reason','houdini_exec',1,10,'Executed successfully.'),
    meta:{canonical:{ok:true,outcome:returnedCheckOutcome,
      verbs:[{verb,ok:true,check_status:'failed',result:facts}]}}};
  const finding=View.model({eventNodes:[node]}).entries[0].checkFindings[0];
  assert.equal(finding.target,target);assert.equal(finding.reason,reason);
}
