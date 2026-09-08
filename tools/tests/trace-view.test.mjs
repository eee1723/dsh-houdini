import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";
import { generatedTraceBlock, traceSources } from "../gen-trace-client.mjs";
import { loadCatalog } from "../catalog-lib.mjs";

const source = fs
  .readFileSync(new URL("../../client.js", import.meta.url), "utf8")
  .replaceAll("\r\n", "\n");
assert(
  source.includes(generatedTraceBlock()),
  "generated renderer and content inventory must match current sources",
);
const inventory = traceSources();
assert(inventory.guidance.text.includes("set_parms"));
assert(
  inventory.presets.every((p) => p.text.length > 1000),
  "persona extraction must retain complete multiline template",
);
assert(
  inventory.skills.every((s) => s.files.some((f) => f.path === "SKILL.md")),
);
const catalog = loadCatalog(
  new URL("../../docs/tool-design.md", import.meta.url),
);
assert(catalog.every((d) => d.verbs.every((v) => v.returns)));
let registration;
let View;
let hooks = [];
let cursor = 0;
const React = {
  createElement: (type, props, ...children) => ({
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
              if (config.id === "houdinitrace") View = component;
            },
          }
        : undefined,
  });
const t = (text) => [{ type: "text", text }];
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

function render() {
  cursor = 0;
  return View({
    sessionId: "fixture",
    useTrajectory: (select) => select(snapshot),
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
let tree = click("提示词与上下文");
assert.match(content(tree), /NEW SYSTEM/);
const picker = all(tree).find((n) => n.type === "select");
picker.props.onChange({ target: { value: "assistant:2" } });
assert.match(content(render()), /HISTORICAL SYSTEM/);
assert(
  !content(render()).includes("NEW SYSTEM"),
  "history must not silently use latest header",
);
tree = click("本次工具定义");
assert.match(content(tree), /old skill description/);
tree = click("技能");
assert.match(content(tree), /old description/);
assert.match(content(tree), /OLD SKILL BODY/);
assert(!content(tree).includes("REPLAY MUST NOT REPLACE ORIGINAL"));
tree = click("工具");
assert.match(content(tree), /返回类型/);
assert.match(content(tree), /build_module/);
tree = click("分析");
assert.match(content(tree), /310/);
assert.match(content(tree), /1 \/ 2/);
tree = click("执行过程");
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
const sourceRead=View.model({eventNodes:[{...result('source','houdini_query',3,30,'Executed successfully.'),
  call:{name:'houdini_query',argsRaw:JSON.stringify({source_ref:'index'})}}]}).entries[0];
assert.equal(sourceRead.kind,'read');
assert.equal(sourceRead.title,'读取原始任务来源');
tree=click('失败 / 拦截');assert.equal(callRows(tree).length,1);assert.match(content(tree),/permission denied/);
console.log('Compact timeline: tool colors, 124 calls, top pagination, direct page selection and detail navigation passed');

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
];
for (const [i, ledger] of detailCases.entries()) {
  hooks=[];
  snapshot.runningCalls=[];
  snapshot.eventNodes=[{...result('detail-case-'+i,'houdini_exec',1,10,'Executed successfully.'),
    meta:{canonical:{ok:ledger.ok,verbs:[ledger]}}}];
  const before=JSON.stringify(snapshot);
  const entry=View.model(snapshot).entries[0];
  tree=render();callRows(tree)[0].props.onClick();tree=render();
  const displayed=content(tree);
  if(ledger.error) assert(displayed.includes(ledger.error),'keep actual failure reason visible');
  if(ledger.summary) assert(displayed.includes('补充证据') && displayed.includes('scene_writes' in ledger.summary ? 'scene_writes' : '/obj/g/OUT'));
  if(!Object.hasOwn(ledger,'result')) assert(displayed.includes('返回值未记录'),'missing is not a successful null return');
  else assert.equal(entry.verbs[0].detail,JSON.stringify(ledger.result));
  assert.equal(JSON.stringify(snapshot),before,'rendering cannot rewrite canonical evidence');
  tree=click('← 返回步骤列表');
  assert.equal(callRows(tree).length,1,'a failure detail must not remove the trace');
}
console.log('Trace failed-detail rendering: missing/null/falsy returns, errors, summaries and back navigation passed');
