/** Read-only input for the local Desktop compatibility automation. */
import {readFile} from 'node:fs/promises'
import {pathToFileURL} from 'node:url'
import {parseArgs} from 'node:util'
import {load as parseYaml} from 'js-yaml'
import semver from 'semver'

const registry = 'https://registry.npmjs.org/@deepseek-ai%2fdsh'
const releases = 'https://api.github.com/repos/deepseek-ai/deepseek-harness/releases'
const feeds = 'https://download.deepseek.com/dsh-desk/feeds/win-x64'
const channels = ['stable', 'nightly']

async function request(url) {
  const response = await fetch(url, {signal: AbortSignal.timeout(20000)})
  if (!response.ok) throw Error(`HTTP ${response.status} from ${url}`)
  return response
}

async function githubReleases() {
  const rows = []
  for (let page = 1; ; page++) {
    const response = await request(`${releases}?per_page=100&page=${page}`)
    const items = await response.json()
    for (const release of items) {
      if (!release.draft && release.tag_name.startsWith('dsh-v'))
        rows.push({version: release.tag_name.slice(5), date: release.published_at, url: release.html_url})
    }
    if (!response.headers.get('link')?.includes('rel="next"')) return rows
  }
}

async function npmReleases() {
  const packument = await (await request(registry)).json()
  return Object.keys(packument.versions).map(version => ({version, date: packument.time[version]}))
}

async function desktopRelease(channel) {
  const url = `${feeds}/${channel}.yml`
  const feed = parseYaml(await (await request(url)).text())
  const installer = feed.files?.find(file => new URL(file.url, url).pathname.endsWith('.exe'))
  if (!semver.valid(feed.version) || !installer?.sha512 || !Number.isFinite(Date.parse(feed.releaseDate)))
    throw Error('Incomplete Windows Desktop update feed: ' + url)
  return [{version: feed.version, date: new Date(feed.releaseDate).toISOString(),
    url: new URL(installer.url, url).href, sha512: installer.sha512}]
}

// A package or GitHub tag can precede Desktop, and two releases may land between checks.
export function collectTargets(sources, since, verified) {
  const cutoff = Date.parse(since)
  if (!Number.isFinite(cutoff)) throw Error('Use an ISO timestamp for --since')
  const targets = new Map()
  for (const [source, rows] of Object.entries(sources)) {
    for (const {version, date, ...detail} of rows) {
      if (verified.has(version) || !semver.valid(version)) continue
      const target = targets.get(version) ?? {version, sources: {}}
      target.sources[source] = {date, ...detail}
      targets.set(version, target)
    }
  }
  return [...targets.values()]
    .filter(target => Object.values(target.sources).some(row => Date.parse(row.date) >= cutoff))
    .sort((a, b) => semver.compare(a.version, b.version))
}

async function main() {
  const {values} = parseArgs({options: {since: {type: 'string'}}})
  if (!values.since || !Number.isFinite(Date.parse(values.since))) throw Error('Usage: node tools/check-dsh-updates.mjs --since <ISO timestamp>')
  const policy = JSON.parse(await readFile(new URL('../dsh-runtime-compatibility.json', import.meta.url), 'utf8'))
  const readers = {github: githubReleases, npm: npmReleases,
    ...Object.fromEntries(channels.map(name => [name, () => desktopRelease(name)]))}
  const sources = {}, errors = {}
  await Promise.all(Object.entries(readers).map(async ([name, read]) => {
    try { sources[name] = await read() }
    catch (error) { errors[name] = error.message }
  }))
  const verified = new Set(policy.releases.map(row => row.dshVersion))
  const targets = collectTargets(sources, values.since, verified)
  const desktop = Object.fromEntries(channels.filter(name => sources[name]).map(name => [name, sources[name][0].version]))
  console.log(JSON.stringify({since: values.since, desktop, targets, errors}, null, 2))
  if (Object.keys(errors).length) process.exitCode = 1
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) await main()
