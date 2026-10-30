/** One compatibility decision for admission and its user-facing observation. */
import {EXPECTED_EXECUTION_CONTRACT_VERSION,EXPECTED_VERB_CATALOG_HASH} from './generated-verb-contract.js'

export function isExecutionContractCompatible(version:unknown,verbCatalogHash:unknown):boolean {
  return version===EXPECTED_EXECUTION_CONTRACT_VERSION&&verbCatalogHash===EXPECTED_VERB_CATALOG_HASH
}
