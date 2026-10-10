/** Original verb receipts are the delivery source, independent of Python __result__.
 * Shared with the generated browser factory; no recursive payload discovery. */
export const NODE_DELIVERY_KIND = 'houdini/node-delivery-v1'

export function nodeDeliveryRows(value: any): any[] {
  if (!value || value.ok !== true || Number(value.outcome?.operations?.failed) > 0
      || !Array.isArray(value.verbs) || value.verbs.some((verb: any) => verb?.ok === false)) return []
  return value.verbs.flatMap((verb: any) =>
    verb?.verb === 'present_nodes' && verb.ok === true
      && verb.result?.kind === NODE_DELIVERY_KIND && Array.isArray(verb.result.nodes)
      ? verb.result.nodes : [])
}
