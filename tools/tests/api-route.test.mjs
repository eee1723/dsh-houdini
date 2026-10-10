import assert from 'node:assert/strict'
import {configuredProviders,configuredApiRoutes} from '../../lib/api-route.js'

const configured={api:'openai-completions',baseURL:'https://gateway.example/v1',apiKeyEnv:'GATEWAY_KEY'}
const catalog={apiKeyEnv:'OPENAI_KEY'}
const context={
  llm:{listProviders:()=>[{id:'custom',name:'Gateway'},{id:'openai',name:'OpenAI'},{id:'account',name:'Account'}],
    listConfigurableProviders:()=>[
      {provider:'custom',displayName:'Configured gateway',settingsNs:'pi',settingsPath:['providers','custom'],declared:true},
      {provider:'openai',displayName:'OpenAI',settingsNs:'pi',settingsPath:['providers','openai']},
      {provider:'anthropic',displayName:'Anthropic',settingsNs:'pi',settingsPath:['providers','anthropic']},
      {provider:'unconfigured',displayName:'Dormant catalog entry',settingsNs:'pi',settingsPath:['providers','unconfigured']},
      {provider:'broken',displayName:'Needs repair',settingsNs:'pi',settingsPath:['providers','broken'],error:'Catalog entry needs repair'},
    ]},
  settings:{describe:()=>[{ns:'pi',value:{providers:{custom:configured,openai:catalog,
    anthropic:{api:'anthropic-messages',baseURL:'https://anthropic.example'},broken:{apiKeyEnv:'BROKEN_KEY'}}}}]},
}
context.get=name=>context[name]
const providers=configuredProviders(context)
assert.deepEqual(providers.map(row=>row.provider),['custom','openai','anthropic','broken','account'])
assert.equal(providers[0].displayName,'Configured gateway')
assert.equal(providers[1].registered,true)
assert.equal(providers[1].profile.baseURL,undefined,'do not invent an endpoint absent from DSH settings')
assert.equal(providers[2].registered,false,'stored inactive providers remain visible')
assert.equal(providers[3].error,'Catalog entry needs repair')
assert.equal(providers[4].configured,false,'registered account routes remain visible without a settings profile')
assert.deepEqual(configuredApiRoutes(context).map(row=>row.provider),['custom'],'image/audio API routes keep explicit protocol and endpoint requirements')
providers[0].profile.apiKeyEnv='changed'
assert.equal(configured.apiKeyEnv,'GATEWAY_KEY','the directory returns detached configuration')
console.log('DSH provider join: configured catalog/custom/inactive/adapter routes, dormant exclusion and explicit API route compatibility passed')
