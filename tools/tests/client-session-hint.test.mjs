import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import vm from 'node:vm';


const source = await readFile(new URL('../../client.js', import.meta.url), 'utf8');
const packageManifest = JSON.parse(await readFile(new URL('../../package.json', import.meta.url), 'utf8'));
assert(packageManifest.dsh.client.inject.includes('@deepseek-ai/dsh-client-ui-trajectory'));


const flush = async () => { for (let i = 0; i < 16; i++) await Promise.resolve(); };
const deferred = () => { let resolve, reject; const promise = new Promise((a, b) => { resolve = a; reject = b; }); return { promise, resolve, reject }; };
function store(value) {
  const listeners = new Set();
  return { getSnapshot: () => value, subscribe: fn => { listeners.add(fn); return () => listeners.delete(fn); },
    set: next => { value = next; for (const listener of [...listeners]) listener(); }, listeners };
}
function element(tag) {
  return { tag, style: {}, dataset: {}, attributes: {}, children: [], textContent: '', removed: false,
    setAttribute(name, value) { this.attributes[name] = value; },
    appendChild(child) { this.children.push(child); return child; },
    remove() { this.removed = true; },
    contains(target) { return target===this || this.children.some(child=>child.contains(target)); } };
}
async function run(href, options = {}) {
  let registration;
  const opened = [], replaced = [], injected = [], creates = [], workspaceCreates = [], panels = [], disposers = [], bootstrapSignals = [];
  const registrations = {}, listeners = new Map(), timers = new Map(), targetRequests=[];
  const connection={generation:{getSnapshot:()=>1,subscribe:()=>()=>{}},rpc:{call:async(_channel,method,payload)=>{targetRequests.push({method,payload});return {ok:true,value:method==='houdiniTargets/list'?{candidates:[],state:{status:'unbound'}}:{workbench:true}};}}};
  const url = new URL(href);
  const path = url.searchParams.get('dsh-houdini-workspace') ?? 'E:\\fixture';
  const rows = options.rows ?? (url.searchParams.has('dsh-houdini-session')
    ? [{ id: url.searchParams.get('dsh-houdini-session'), cwd: path, projectionValues: {agentPreset:'houdini'}, updatedAt: 1 }] : []);
  const sessionStore = options.sessionStore ?? store({
    ids: rows.map(row => row.id), byId: Object.fromEntries(rows.map(row => [row.id, row])),
    phase: options.sessionPhase ?? 'ready',
  });
  const currentSession = options.currentSession ?? store({key: options.current});
  const workspaceStore = options.workspaceStore ?? store({
    items: [{workspaceId:'w', path, sessionIds: options.accounted ?? rows.map(row => row.id)}],
    archivedSessionIds: options.archived ?? [], phase: options.workspacePhase ?? 'ready', state:options.workspaceStatus??'idle', error:null,
  });
  let refreshes = 0, reloads = 0, earlyDisposed = false;
  let navigation = new AbortController();
  const layout = {beginNavigation:()=>{navigation.abort();navigation=new AbortController();return navigation.signal;},
    selectPanel:id=>{navigation.abort();panels.push(id);}};
  const openSession = id => {
    assert(sessionStore.getSnapshot().byId[id], 'native session navigation rejects unaddressable IDs');
    opened.push(id);
    if(!options.rejectSelection)currentSession.set({key:id});
    layout.selectPanel(null);
  };
  // Native uiWorkspace registers its constructor's watcher before consumers.
  // At ready it synchronously starts navigation, then awaits connection and
  // checks that signal before committing. Model this actual DSH lifecycle.
  if (options.bootstrapRestore) {
    let started = false;
    const restore = () => {
      if (started || workspaceStore.getSnapshot().phase !== 'ready' || sessionStore.getSnapshot().phase !== 'ready') return;
      started = true;
      const signal = layout.beginNavigation(); bootstrapSignals.push(signal);
      options.bootstrapRestore.wait.then(() => {
        if (!signal.aborted) {
          // Native restoration preserves the selected global panel, unlike a
          // user's openSession action which reveals Conversation.
          opened.push(options.bootstrapRestore.sessionId);
          currentSession.set({key:options.bootstrapRestore.sessionId});
        }
      });
    };
    disposers.push(workspaceStore.subscribe(restore), sessionStore.subscribe(restore));
    restore();
  }
  const sessions = {
    list: sessionStore,
    refresh: async () => { refreshes++; if (options.refresh) await options.refresh(api); },
  };
  const uiSession = {adapter:{current:currentSession}};
  const uiWorkspace = {openSession};
  // This launcher fixture does not serve any settings namespaces. DSH still
  // provides the shared form service; whileServed leaves their pages absent.
  const configForms = {whileServed: () => () => {}};
  function publish(request, preset = 'houdini', attached = true) {
    const previous = sessionStore.getSnapshot();
    sessionStore.set({...previous, ids:[...new Set([...previous.ids,request.sessionId])],
      byId:{...previous.byId,[request.sessionId]:{id:request.sessionId,cwd:path,updatedAt:100,projectionValues:{agentPreset:preset}}}});
    if (attached) {
      const state = workspaceStore.getSnapshot();
      workspaceStore.set({...state,items:state.items.map(w=>w.workspaceId===request.workspaceId
        ? {...w,sessionIds:[...new Set([...w.sessionIds,request.sessionId])]} : w)});
    }
  }
  const workspaces = {
    list: workspaceStore,
    create: async input => {
      workspaceCreates.push({...input});
      if (options.createWorkspace) return options.createWorkspace(input, api);
      return workspaceStore.getSnapshot().items[0];
    },
  };
  const remote = {session:{create:async request=>{
    creates.push({...request});
    if (options.create) return options.create(request, api);
    publish(request);
    return {ok:true,value:{sessionId:request.sessionId,agentPreset:'houdini'}};
  }}};
  const slots = {
    inject: (_name, install) => { install(); },
    register: (options, component) => { registrations[options.id] = {options,component}; return () => {}; },
    registerFactory: () => () => {},
    entriesOfSlot: () => [],
    subscribe: () => () => {},
  };
  const window = {
    location: { href, reload: () => { reloads++; } },
    crypto: {randomUUID:()=> 'generated-navigation-id'},
    history: { state:{retained:true}, replaceState:(state,title,target)=>{
      replaced.push({state,title,url:target}); window.location.href = new URL(target,window.location.href).href;
    }},
    addEventListener: (name, fn) => { if (!listeners.has(name)) listeners.set(name,new Set()); listeners.get(name).add(fn); },
    removeEventListener: (name, fn) => { listeners.get(name)?.delete(fn); },
    __ModuleLoader__: {load:value=>{registration=value;}},
  };
  const body = element('body');
  const document = {body, querySelector:()=>({}), createElement:element, head:element('head')};
  const scope = {
    get: name => ({sessions,workspaces,remote,slots,uiSession,uiWorkspace,connection,
      layout,configForms})[name],
    effect: install => { const dispose=install(); if(dispose) disposers.push(dispose); },
  };
  const api = {
    opened,replaced,injected,registrations,creates,workspaceCreates,targetRequests,panels,window,body,sessionStore,workspaceStore,currentSession,sessions,uiWorkspace,publish,layout,bootstrapSignals,
    get refreshes(){return refreshes;},get reloads(){return reloads;},get earlyDisposed(){return earlyDisposed;},
    emit: (name,event={target:body})=>{for(const fn of [...(listeners.get(name)??[])])fn(event);},
    timeout:()=>{for(const fn of [...timers.values()])fn();},
    dispose:()=>{for(const dispose of disposers)dispose();},
    notices:()=>body.children.filter(e=>e.id==='dsh-houdini-navigation'&&!e.removed),
  };
  const context = vm.createContext({
    URL,console,document,window,AbortController,
    setTimeout: fn=>{const id={};timers.set(id,fn);return id;},
    clearTimeout:id=>timers.delete(id),
  });
  vm.runInContext(source,context,{filename:'client.js'});
  assert.equal(registration.id,'dsh-houdini');
  const plugin = registration.factory(name=>{
    if(name==='react')return {
      createElement:(type,props,...children)=>({type,props:props??{},children}),
      useState:value=>[value,()=>{}],useMemo:fn=>fn(),useEffect:()=>{},useRef:value=>({current:value}),useSyncExternalStore:(_subscribe,get)=>get(),
    };
    if(name==='@deepseek-ai/dsh-client-ui-primitives')return {Tooltip:'tooltip',Menu:'menu',MenuItemButton:'menuitem',Button:'button',Toast:'toast'};
    throw new Error(`unexpected client dependency: ${name}`);
  });
  plugin.apply({
    get:scope.get,
    effect:scope.effect,
    inject:(deps,callback)=>{injected.push([...deps]);callback(scope);},
  });
  await flush();
  return api;
}

const hinted = await run(
  'http://127.0.0.1:3081/?dsh-houdini-session=session-target&retained=yes#conversation',
);
assert.deepEqual(hinted.injected, [[
  'sessions', 'workspaces', 'remote', 'remote.session', 'uiSession', 'uiWorkspace', 'layout',
], ['connection', 'configForms'], ['connection'], ['connection', 'uiSession', 'sessions', 'uiWorkspace'], ['connection', 'uiConversation']]);
const chipOwner=hinted.registrations['houdini-project-label'].component;
const chipProps={sessionId:'session-target',useSessions:select=>select(hinted.sessionStore.getSnapshot())};
const chipMenuElement=chipOwner(chipProps);
assert(chipMenuElement,'native Houdini header registers the compact target selector');
const chipMenu=chipMenuElement.type(chipMenuElement.props);
const chipTooltip=chipMenu.props.anchor.type(chipMenu.props.anchor.props);
const chipButton=chipTooltip.children[0];
assert.equal(chipButton.props['data-state'],'unbound','the real registered UI shows an actionable unbound state');
chipButton.props.onClick();await flush();
assert.equal(hinted.targetRequests.length,0,'opening the selector uses the shared presence lifecycle, without a second per-conversation target list or binding change');
assert.deepEqual(hinted.opened, ['session-target']);
assert.deepEqual(hinted.replaced.slice(-1), [{
  state: { retained: true },
  title: '',
  url: '/?retained=yes#conversation',
}]);

const plain = await run('http://127.0.0.1:3081/');
assert.deepEqual(plain.injected, hinted.injected);
assert.deepEqual(plain.opened, []);
assert.deepEqual(plain.replaced, []);

const workspaceUrl = 'http://127.0.0.1:3081/?dsh-houdini-workspace=E%3A%5Cfixture&dsh-houdini-request=dsh-houdini-navigation-1';
const row = (id, updatedAt = 1, preset = 'houdini', extra = {}) => ({
  id, updatedAt, cwd:'E:\\fixture', projectionValues:{agentPreset:preset}, ...extra,
});
// Host can create/attach/flush a new native task after the current page's
// list became ready. The first explicit intent must refresh that same native
// store before rejecting a missing row; no second session or workspace is made.
const externalTask = await run('http://127.0.0.1:3081/?dsh-houdini-session=host-created', {
  rows:[row('previous')],current:'previous',accounted:['previous','host-created'],
  refresh:api=>api.publish({workspaceId:'w',sessionId:'host-created'}),
});
assert.equal(externalTask.refreshes,1);
assert.deepEqual(externalTask.opened,['host-created']);
assert.equal(externalTask.creates.length,0);
assert.equal(externalTask.workspaceCreates.length,0);
assert.equal(externalTask.notices().length,0);
externalTask.dispose();

for (const layout of [false, true]) {
  // Native current selection wins over recency; do not replace an older task
  // the user is actually viewing merely because another one ran recently.
  const current = await run(workspaceUrl, {rows:[row('current'),row('newer',10)],current:'current',layout});
  assert.deepEqual(current.opened,['current']);
  assert.equal(current.creates.length,0);
  assert.equal(current.refreshes,0, 'the initial native baseline already loaded the list');
  assert.equal(current.notices().length,0);
  assert.deepEqual(current.panels,[null]);
  current.dispose();
}
const archived = await run(workspaceUrl, {
  rows:[row('old',1),row('new',2),row('archived',30),row('other-preset',40,'standard'),
    row('child',50,'houdini',{origin:'subagent'}),row('unaccounted',60)],
  archived:['archived'],current:'archived',accounted:['old','new','archived','other-preset','child'],
});
assert.deepEqual(archived.opened,['new']);
assert.equal(archived.creates.length,0);
archived.dispose();

const created = await run(workspaceUrl,{rows:[row('other',1,'standard')],current:'other'});
assert.deepEqual(created.creates,[{workspaceId:'w',sessionId:'dsh-houdini-navigation-1',agentPreset:'houdini'}]);
assert.deepEqual(created.opened,['dsh-houdini-navigation-1']);
assert.equal(created.refreshes,1);
assert.equal(created.notices().length,0,'newly created task confirmation uses the refreshed workspace membership');
assert.equal(created.sessionStore.getSnapshot().byId.other.projectionValues.agentPreset,'standard',
  'do not repurpose a user-owned blank task under another preset');
created.dispose();

// Ordinary input cannot cancel workspace navigation, including while baselines load.
const inputWaiting = await run(workspaceUrl,{rows:[row('ready')],workspacePhase:'pending'});
inputWaiting.emit('pointerdown');inputWaiting.emit('keydown',{key:'x',target:inputWaiting.body});
assert.equal(inputWaiting.notices().length,1);
inputWaiting.workspaceStore.set({...inputWaiting.workspaceStore.getSnapshot(),phase:'ready'});await flush();
assert.deepEqual(inputWaiting.opened,['ready']);inputWaiting.dispose();

const wrongSelection = await run(workspaceUrl,{rows:[row('ready')],rejectSelection:true});
assert.match(wrongSelection.notices()[0].textContent,/DSH 未选中请求的任务/);
assert(new URL(wrongSelection.window.location.href).searchParams.has('dsh-houdini-workspace'));
wrongSelection.dispose();

const waiting = await run(workspaceUrl,{rows:[row('ready')],workspacePhase:'pending'});
assert.deepEqual(waiting.opened,[]);
assert.equal(waiting.creates.length,0);
waiting.workspaceStore.set({...waiting.workspaceStore.getSnapshot(),phase:'ready'});
await flush();
assert.deepEqual(waiting.opened,['ready']);
assert.equal(waiting.workspaceStore.listeners.size,0);
waiting.dispose();

// Initial native restoration is an earlier bootstrap, not user navigation.
// Its async connection may finish later but must not replace the launch task.
const bootstrapConnection = deferred();
const bootstrap = await run(workspaceUrl,{rows:[row('bootstrap',1,'standard'),row('launch',2)],workspacePhase:'pending',
  bootstrapRestore:{sessionId:'bootstrap',wait:bootstrapConnection.promise}});
assert(new URL(bootstrap.window.location.href).searchParams.has('dsh-houdini-workspace'));
assert.deepEqual(bootstrap.opened,[]);
bootstrap.workspaceStore.set({...bootstrap.workspaceStore.getSnapshot(),phase:'ready'});
await flush();
assert.equal(bootstrap.bootstrapSignals.length,1);
assert.equal(bootstrap.bootstrapSignals[0].aborted,true,'explicit launch cancels the earlier native restoration');
assert.deepEqual(bootstrap.opened,['launch']);
bootstrapConnection.resolve();await flush();
assert.deepEqual(bootstrap.opened,['launch'],'late bootstrap completion cannot overwrite the explicit selection');
assert(!new URL(bootstrap.window.location.href).searchParams.has('dsh-houdini-workspace'));
bootstrap.dispose();

// Native restoration checks phases, not the workspace's refresh state. Its
// commit during a ready-but-loading baseline must not consume the launch.
const loadingConnection = deferred();
const loadingBootstrap = await run(workspaceUrl,{rows:[row('bootstrap',1,'standard'),row('launch',2)],workspaceStatus:'loading',
  bootstrapRestore:{sessionId:'bootstrap',wait:loadingConnection.promise}});
loadingConnection.resolve();await flush();
assert.deepEqual(loadingBootstrap.opened,['bootstrap']);
assert(new URL(loadingBootstrap.window.location.href).searchParams.has('dsh-houdini-workspace'));
loadingBootstrap.workspaceStore.set({...loadingBootstrap.workspaceStore.getSnapshot(),state:'idle'});
await flush();
assert.deepEqual(loadingBootstrap.opened,['bootstrap','launch']);
loadingBootstrap.dispose();

const reconnecting = await run(workspaceUrl,{rows:[row('old'),row('new',2)],current:'old',workspaceStatus:'loading'});
assert.deepEqual(reconnecting.opened,[],'ready phase can retain a stale archive baseline during reconnect');
reconnecting.workspaceStore.set({...reconnecting.workspaceStore.getSnapshot(),state:'idle',archivedSessionIds:['old']});
await flush();
assert.deepEqual(reconnecting.opened,['new']);
reconnecting.dispose();
const missingRow = await run(workspaceUrl,{rows:[],accounted:['loading-task']});
assert.equal(missingRow.creates.length,0,'an unarrived accounted row is not proof that no task exists');
missingRow.sessionStore.set({...missingRow.sessionStore.getSnapshot(),ids:['loading-task'],byId:{'loading-task':row('loading-task')}});
await flush();
assert.deepEqual(missingRow.opened,['loading-task']);
missingRow.dispose();

const disposed = await run(workspaceUrl,{workspacePhase:'pending'});
disposed.dispose();
disposed.workspaceStore.set({...disposed.workspaceStore.getSnapshot(),phase:'ready'});
await flush();
assert.equal(disposed.creates.length,0);
assert.deepEqual(disposed.opened,[]);
assert.equal(disposed.notices().length,0);
assert.equal(disposed.workspaceStore.listeners.size,0);
assert.equal(disposed.sessionStore.listeners.size,0);
assert.equal(disposed.currentSession.listeners.size,0);

// Actual DSH navigation supersedes a pending launch, never ordinary input.
const workspaceGate = deferred();
const manual = await run(workspaceUrl,{rows:[row('manual',1,'standard')],
  createWorkspace:(_input,api)=>workspaceGate.promise.then(()=>api.workspaceStore.getSnapshot().items[0])});
manual.emit('pointerdown');
manual.uiWorkspace.openSession('manual');
workspaceGate.resolve();
await flush();
assert.deepEqual(manual.opened,['manual']);
assert.equal(manual.creates.length,0);
assert.equal(manual.notices().length,0);
manual.dispose();

const createGate = deferred();
const duringCreate = await run(workspaceUrl,{rows:[row('manual',1,'standard')],create:async(request,api)=>{
  await createGate.promise;api.publish(request);return {ok:true,value:{sessionId:request.sessionId,agentPreset:'houdini'}};
}});
assert.equal(duringCreate.creates.length,1);
duringCreate.emit('keydown');
duringCreate.uiWorkspace.openSession('manual');
createGate.resolve();
await flush();
assert.deepEqual(duringCreate.opened,['manual']);
assert.equal(duringCreate.creates.length,1);
duringCreate.dispose();

const oldGate = deferred();
const old = await run(workspaceUrl,{createWorkspace:(_input,api)=>oldGate.promise.then(()=>api.workspaceStore.getSnapshot().items[0])});
old.window.location.href = workspaceUrl.replace('fixture','different').replace('navigation-1','navigation-2');
oldGate.resolve();
await flush();
assert.equal(old.creates.length,0);
assert.deepEqual(old.opened,[]);
assert.equal(new URL(old.window.location.href).searchParams.get('dsh-houdini-request'),'dsh-houdini-navigation-2');
old.dispose();
const errorGate = deferred();
const oldError = await run(workspaceUrl,{createWorkspace:()=>errorGate.promise});
oldError.window.location.href = workspaceUrl.replace('navigation-1','navigation-2');
errorGate.reject(new Error('late old error'));await flush();
assert.equal(oldError.notices().length,0,'a rejected old hint must not leave a stale error over the new intent');
assert.equal(new URL(oldError.window.location.href).searchParams.get('dsh-houdini-request'),'dsh-houdini-navigation-2');
oldError.dispose();

// A published-but-unattached/lost create response is not retried automatically.
// Manual reload carries the same prospective identity and can safely attach it.
const lost = await run(workspaceUrl,{create:(request,api)=>{
  api.publish(request,'houdini',false);
  return {ok:false,error:{code:'session/workspace-attach-failed',message:'fixture attachment failure'}};
}});
assert.equal(lost.creates.length,1);
assert.deepEqual(lost.opened,[]);
assert.match(lost.notices()[0].textContent,/fixture attachment failure/);
assert.equal(lost.notices()[0].attributes.role,'alert');
const retry = await run(lost.window.location.href,{sessionStore:lost.sessionStore,workspaceStore:lost.workspaceStore});
assert.equal(retry.creates[0].sessionId,lost.creates[0].sessionId);
assert.equal(retry.sessionStore.getSnapshot().ids.length,1);
assert.deepEqual(retry.opened,['dsh-houdini-navigation-1']);
lost.dispose();retry.dispose();

let attachmentPending=true;
const inplace = await run(workspaceUrl,{create:(request,api)=>{
  api.publish(request,'houdini',!attachmentPending);
  if(attachmentPending){attachmentPending=false;return {ok:false,error:{message:'first attachment failed'}};}
  return {ok:true,value:{sessionId:request.sessionId,agentPreset:'houdini'}};
}});
inplace.notices()[0].children.at(-1).onclick();await flush();
assert.equal(inplace.creates.length,2);
assert.equal(new Set(inplace.creates.map(call=>call.sessionId)).size,1);
assert.deepEqual(inplace.opened,['dsh-houdini-navigation-1']);
assert.equal(inplace.reloads,0);
inplace.dispose();

const lateCreate = deferred();let attempts=0;
const overlapping = await run(workspaceUrl,{create:async(request,api)=>{
  if(++attempts===1)await lateCreate.promise;
  api.publish(request);
  return {ok:true,value:{sessionId:request.sessionId,agentPreset:'houdini'}};
}});
overlapping.timeout();await flush();
const firstRetry = overlapping.notices()[0].children.at(-1);
firstRetry.onclick();firstRetry.onclick();await flush();
assert.equal(overlapping.creates.length,2,'double-click does not submit a third create');
lateCreate.resolve();await flush();
assert.deepEqual(overlapping.opened,['dsh-houdini-navigation-1'],'late old completion cannot reopen or supersede a newer attempt');
overlapping.dispose();

const wrong = await run(workspaceUrl,{create:request=>({ok:true,value:{sessionId:request.sessionId,agentPreset:'standard'}})});
assert.equal(wrong.creates.length,1);
assert.deepEqual(wrong.opened,[]);
assert.match(wrong.notices()[0].textContent,/没有创建请求的 Houdini/);
wrong.dispose();
const unverified = await run(workspaceUrl,{create:(request,api)=>{
  api.publish(request);const s=api.sessionStore.getSnapshot();
  api.sessionStore.set({...s,byId:{...s.byId,[request.sessionId]:{...s.byId[request.sessionId],projectionValues:{}}}});
  return {ok:true,value:{sessionId:request.sessionId}};
}});
assert.deepEqual(unverified.opened,[]);
unverified.timeout();await flush();
assert.match(unverified.notices()[0].textContent,/未就绪/);
assert.equal(unverified.creates.length,1);
const timedOutButton = unverified.notices()[0].children.at(-1);
assert.equal(timedOutButton.type,'button');
assert.equal(timedOutButton.textContent,'重试打开工作区');
unverified.emit('keydown',{key:'Tab',target:unverified.body});
assert.equal(unverified.notices().length,1,'keyboard focus must be able to reach Retry');
timedOutButton.onclick();await flush();
assert.equal(unverified.reloads,0,'retry must not reload a page containing drafts');
assert.equal(unverified.creates.length,2);
assert.equal(new Set(unverified.creates.map(call=>call.sessionId)).size,1);
unverified.dispose();

// Failure is not permission for an old retry button to navigate after the user
// edits another task. This must also work after a timeout already aborted it.
for (const timeout of [false,true]) {
  const failed = await run(workspaceUrl,{rows:[row('manual',1,'standard')],
    workspacePhase:timeout?'pending':'ready',
    create:()=>({ok:false,error:{message:'fixture offline'}})});
  if(timeout){failed.timeout();await flush();}
  const retryButton = failed.notices()[0].children.at(-1);
  failed.emit('pointerdown',{target:retryButton});
  assert.equal(failed.notices().length,1,'the notice itself is not a different navigation intent');
  failed.emit('keydown',{key:'x',target:failed.body});
  failed.uiWorkspace.openSession('manual');
  const count=failed.creates.length;
  retryButton.onclick();await flush();
  assert.equal(failed.creates.length,count);
  assert.deepEqual(failed.opened,['manual']);
  assert.equal(failed.notices().length,0);
  assert.equal(failed.reloads,0);
  assert(!new URL(failed.window.location.href).searchParams.has('dsh-houdini-workspace'));
  failed.dispose();
}

assert.equal(plain.registrations['houdini-watermark'], undefined, 'content is not covered by a decorative watermark');
assert.equal(plain.registrations.houdinitools, undefined, 'Houdini tool documentation belongs to Trace');
assert.equal(plain.registrations.houdinitrace.options.label, '执行记录');
assert.equal(plain.registrations['houdini-workspace-status'], undefined, 'the compact project component owns workspace state without a second warning bar');

const deliveryScope = plain.registrations['houdini-delivery-scope'].component;
assert.equal(plain.registrations['houdini-delivery-scope'].options.name,'conversation.chat.turnTail');
for (const preset of ['houdini','standard',undefined]) {
  const marker=deliveryScope({sessionId:'s',useSessions:fn=>fn({byId:{s:{projectionValues:{agentPreset:preset}}}})});
  if (preset==='houdini') {
    assert.equal(marker.props.hidden,true);
    assert.equal(marker.props['data-houdini-workspace'],true);
  } else assert.equal(marker,null,'delivery appearance must remain local to Houdini tasks');
}
const view = plain.registrations.houdinitrace.component({}).type;
const ledgerLine = '1. [ok] verb_help(["set_keyframes"]) -> '
  + '{"name":"set_keyframes","signature":"(node, channels) -> dict"} (0ms)';
const tree = view({
  useTrajectory: (select) => select({
    eventNodes: [{
      kind: 'tool-result',
      seq: 4,
      time: 100,
      call: { name: 'houdini_query', argsRaw: '{}' },
      content: [{ type: 'text', text: `Executed successfully.\n\nverbs (1):\n${ledgerLine}` }],
    }],
  }),
});
assert(textContent(tree).includes('(node, channels) -> dict'),
  'legacy verb response remains available in the expandable execution details');

function textContent(node) {
  if (node === null || node === undefined) return '';
  if (typeof node === 'string' || typeof node === 'number') return String(node);
  if (Array.isArray(node)) return node.map(textContent).join(' ');
  if (typeof node !== 'object') return '';
  return (node.children ?? []).map(textContent).join(' ');
}

const mixedRawUsage = {
  directCalls: [{ name: 'hou.node', count: 1 }],
  coveredMutations: [],
  suspectedMutations: [],
  gateOutcome: 'read_only',
};
const blockedRawUsage = {
  directCalls: [{ name: 'hou.hipFile.save', count: 1 }],
  coveredMutations: [],
  suspectedMutations: [{ name: 'save', count: 1 }],
  gateOutcome: 'blocked',
};
const traceProps = {
  useTrajectory: (select) => select({ eventNodes: [
      {
        kind: 'tool-result', seq: 10, time: 1000,
        call: { name: 'houdini_exec', argsRaw: JSON.stringify({ code: "n = hou.node('/obj')\n__result__ = scene_info()" }) },
        content: [{ type: 'text', text: [
          'Executed successfully.',
          'stdout:\n[verb] scene_info([]) -> {} (0ms)\ninspection complete',
          '__result__:\n{"ok":true,"nodes":[]}',
          `raw-usage:\n${JSON.stringify(mixedRawUsage, null, 2)}`,
          `verbs (1):\n1. [ok] scene_info([]) -> {"ok":true} (0ms)`,
        ].join('\n\n') }],
      },
      {
        kind: 'tool-result', seq: 11, time: 2000,
        call: { name: 'houdini_exec', argsRaw: JSON.stringify({ code: 'hou.hipFile.save()' }) },
        content: [{ type: 'text', text: [
          'Execution failed:\nraw-hou gate: blocked BEFORE execution (the verb vocabulary is the primary interface; raw hou is gated).',
          `raw-usage:\n${JSON.stringify(blockedRawUsage, null, 2)}`,
        ].join('\n\n') }],
      },
      {
        kind: 'tool-result', seq: 12, time: 3000,
        call: {
          name: 'houdini_exec',
          argsRaw: JSON.stringify({
            code: 'hou.hipFile.save()',
            allow_raw: '词表没有 HIP 保存动词',
          }),
        },
        content: [{ type: 'text', text: 'Executed successfully.\n\nstdout:\n[gate] raw-hou exemption: 词表没有 HIP 保存动词' }],
      },
      {
        kind: 'tool-result', seq: 13, time: 4000,
        call: { name: 'houdini_exec', argsRaw: JSON.stringify({ code: "layout_nodes('/obj')\nsop_set_output('/obj/bike/OUT')" }) },
        content: [{ type: 'text', text: [
          'Execution failed:\nValueError: display output is ambiguous',
          'rollback:\n{"supported":true,"applied":true,"scope":"Houdini undoable scene edits only"}',
          'verbs (2):\n1. [ok] layout_nodes(["/obj"]) -> {"nodes":12} (2ms)\n2. [FAIL] sop_set_output(["/obj/bike/OUT"]) -> error: ambiguous (0ms)',
        ].join('\n\n') }],
      },
    ] }),
};
const traceTree = view(traceProps);
const traceText = textContent(traceTree).replace(/\s+/g, ' ');
assert.match(traceText, /Gate 拦截/);
assert.match(traceText, /已回滚/);
assert.match(traceText, /执行代码/);
assert.match(traceText, /执行步骤/);
assert.match(traceText, /查看原始工具结果/);
assert.match(traceText, /高级诊断/);
assert(!traceText.includes('成功修改含动词'), 'analysis metrics must not crowd the main timeline');
const snapshot = traceProps.useTrajectory(s=>s);
const entries = view.model(snapshot).entries;
assert.equal(entries[0].rawUsage.gateOutcome, 'read_only');
assert.equal(entries[0].verbs.length, 1);
assert.equal(entries[1].gateBlocked, true);
assert.equal(entries[2].exemptionReason, '词表没有 HIP 保存动词');
assert.equal(entries[3].rollbackApplied, true);

console.log('client launcher-session hint and ledger parser tests passed');
