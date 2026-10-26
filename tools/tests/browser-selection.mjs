export const NATIVE_SELECTION = `(()=>{
  const row=document.querySelector('[data-row-key^="session:"][aria-selected="true"]');
  if(!row)return null;
  return {sessionId:row.getAttribute('data-row-key').slice('session:'.length),
    agentPreset:document.querySelector('[data-houdini-project-label]')?'houdini':'standard'};
})()`

export function nativeSessionSelector(id) {
  return '[data-row-key="session:'+id+'"][aria-selected="true"]'
}

export function nativeSessionSelected(id) {
  return `Boolean(document.querySelector(${JSON.stringify(nativeSessionSelector(id))}))`
}
