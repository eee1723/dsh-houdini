/** Safe UI values and the sole protected account record. Never export a token through Remote. */
export const PROVIDER = 'chatgpt-subscription'
export const OWNER = 'chatgpt-subscription'
export const RESOURCE = 'https://api.openai.com/v1'
export const ISSUER = 'https://auth.openai.com'
export const PLAN_SCOPE = 'chatgpt.tokens.use.direct'
export type Identity = {subject:string;name?:string;email?:string}
export type Tokens = {accessToken:string;refreshToken?:string;expiresAt:number;earliestRefreshAt?:string|number}
export type PendingTokens = {tokens:Tokens;scopes:string[];idToken:string;receivedAt:number;nonce?:string}
export type Account = {id:string;label:string;clientId?:string;identity?:Identity;idToken?:string;status:'disconnected'|'connected'|'reauth_required';scopes:string[];tokens?:Tokens;pending?:PendingTokens;revision:number;connectionRevision?:number;planNoticeAcknowledged?:boolean}
export type AccountState = {version:1;hostId:string;activeId?:string;accounts:Account[]}
export type AccountView = {id:string;label:string;status:Account['status'];sharing:boolean;identity?:Identity;active:boolean;verificationPending:boolean;needsPlanNotice:boolean}
export type LoginView = {attemptId:string;status:'pending'|'authorized'|'cancelled'|'failed';message?:string;launchUrl?:string;error?:{code:string;message:string}}
export type ModelView = {id:string;name:string;supported:boolean;unsupportedReason?:string}
export type AccountGeneration = {accountId:string;connectionRevision:number}
export type StatusView = {provider:string;accounts:AccountView[];activeAccountId:string|null;login:LoginView|null;models:ModelView[];catalogRead:boolean;protection:string;usageUrl:string;note:string}
export interface Protector {readonly id:string;protect(bytes:Uint8Array):Promise<Uint8Array>;unprotect(bytes:Uint8Array):Promise<Uint8Array>}
export type Fetcher = typeof fetch
