#!/usr/bin/env node

import { existsSync, readFileSync, readdirSync, statSync } from 'node:fs'
import { dirname, isAbsolute, join, relative, resolve, sep } from 'node:path'
import { fileURLToPath } from 'node:url'

function parseArgs(argv) {
  const out = { json: false, strict: false, root: null }
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i]
    if (arg === '--json') out.json = true
    else if (arg === '--strict') out.strict = true
    else if (arg === '--root') out.root = argv[++i]
    else throw new Error(`unknown argument: ${arg}`)
  }
  return out
}

function walkFiles(dir) {
  if (!existsSync(dir)) return []
  const out = []
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const path = join(dir, entry.name)
    if (entry.isDirectory()) out.push(...walkFiles(path))
    else if (entry.isFile()) out.push(path)
  }
  return out
}

function parseSkill(markdown) {
  const match = markdown.match(/^---\r?\n([\s\S]*?)\r?\n---\r?\n([\s\S]*)$/)
  if (!match) return { name: null, description: null, body: markdown, frontmatter: false }
  return {
    name: match[1].match(/^name:\s*(.+)$/m)?.[1]?.trim() ?? null,
    description: match[1].match(/^description:\s*(.+)$/m)?.[1]?.trim() ?? null,
    body: match[2],
    frontmatter: true,
  }
}

function markdownLinks(text) {
  const links = []
  for (const match of text.matchAll(/\[[^\]]*\]\(([^)]+)\)/g)) {
    const raw = match[1].trim().replace(/^<|>$/g, '')
    if (!raw || /^(?:https?:|mailto:|#)/i.test(raw)) continue
    links.push(raw.split('#', 1)[0])
  }
  return links
}

function inside(root, path) {
  const rel = relative(root, path)
  return rel === '' || (!rel.startsWith(`..${sep}`) && rel !== '..' && !isAbsolute(rel))
}

function reachableMarkdown(skillDir, startFile, issues) {
  const seen = new Set()
  const queue = [startFile]
  while (queue.length) {
    const file = queue.shift()
    const key = resolve(file)
    if (seen.has(key) || !existsSync(key)) continue
    seen.add(key)
    const text = readFileSync(key, 'utf8')
    for (const link of markdownLinks(text)) {
      const target = resolve(dirname(key), link)
      if (!inside(skillDir, target)) {
        issues.push({ code: 'LINK_ESCAPES_SKILL', file: relative(skillDir, key), link })
        continue
      }
      if (!existsSync(target)) {
        issues.push({ code: 'MISSING_LINK', file: relative(skillDir, key), link })
      } else if (statSync(target).isFile() && target.toLowerCase().endsWith('.md')) {
        queue.push(target)
      }
    }
  }
  return seen
}

const args = parseArgs(process.argv.slice(2))
const scriptDir = dirname(fileURLToPath(import.meta.url))
const root = resolve(args.root ?? join(scriptDir, '..', '..', '..'))
const skillsRoot = join(root, 'skills')
const registryPath = join(root, 'src', 'skill.ts')
const issues = []
const warnings = []

if (!existsSync(skillsRoot)) throw new Error(`skills directory not found: ${skillsRoot}`)
if (!existsSync(registryPath)) throw new Error(`skill registry not found: ${registryPath}`)

const registryText = readFileSync(registryPath, 'utf8')
const registrations = [...registryText.matchAll(/\{\s*name:\s*'([^']+)'\s*,\s*dir:\s*'([^']+)'\s*\}/g)]
  .map((match) => ({ name: match[1], dir: match[2] }))
const regByDir = new Map(registrations.map((item) => [item.dir, item]))

const dirs = readdirSync(skillsRoot, { withFileTypes: true })
  .filter((entry) => entry.isDirectory())
  .map((entry) => entry.name)
  .sort()

const skills = []
const names = new Map()
for (const dir of dirs) {
  const skillDir = join(skillsRoot, dir)
  const skillFile = join(skillDir, 'SKILL.md')
  if (!existsSync(skillFile)) {
    issues.push({ code: 'MISSING_SKILL_MD', skill: dir })
    continue
  }
  const parsed = parseSkill(readFileSync(skillFile, 'utf8'))
  if (!parsed.frontmatter) issues.push({ code: 'BAD_FRONTMATTER', skill: dir })
  if (parsed.name !== dir) issues.push({ code: 'NAME_DIR_MISMATCH', skill: dir, name: parsed.name })
  if (!parsed.description) issues.push({ code: 'MISSING_DESCRIPTION', skill: dir })
  if (parsed.description?.includes('\n')) issues.push({ code: 'MULTILINE_DESCRIPTION', skill: dir })
  if (parsed.name) {
    if (names.has(parsed.name)) issues.push({ code: 'DUPLICATE_NAME', skill: dir, other: names.get(parsed.name) })
    else names.set(parsed.name, dir)
  }

  const reachable = reachableMarkdown(skillDir, skillFile, issues)
  const referenceFiles = walkFiles(join(skillDir, 'references'))
    .filter((file) => file.toLowerCase().endsWith('.md'))
  const orphanReferences = referenceFiles
    .filter((file) => !reachable.has(resolve(file)))
    .map((file) => relative(skillDir, file).replaceAll('\\', '/'))
  for (const file of orphanReferences) warnings.push({ code: 'ORPHAN_REFERENCE', skill: dir, file })

  const registration = regByDir.get(dir) ?? null
  if (!registration) issues.push({ code: 'UNREGISTERED_SKILL', skill: dir })
  else if (registration.name !== parsed.name) {
    issues.push({ code: 'REGISTRATION_NAME_MISMATCH', skill: dir, registered: registration.name, name: parsed.name })
  }
  if (parsed.body.length > 12000) warnings.push({ code: 'LARGE_ENTRYPOINT', skill: dir, chars: parsed.body.length })

  skills.push({
    dir,
    name: parsed.name,
    description: parsed.description,
    entrypointChars: parsed.body.length,
    referenceCount: referenceFiles.length,
    orphanReferences,
    registered: Boolean(registration),
  })
}

for (const registration of registrations) {
  if (!dirs.includes(registration.dir)) {
    issues.push({ code: 'REGISTERED_DIR_MISSING', ...registration })
  }
}

const report = {
  schemaVersion: 1,
  root,
  summary: {
    skills: skills.length,
    registrations: registrations.length,
    issues: issues.length,
    warnings: warnings.length,
  },
  skills,
  registrations,
  issues,
  warnings,
}

if (args.json) {
  process.stdout.write(`${JSON.stringify(report, null, 2)}\n`)
} else {
  console.log(`Houdini skills: ${skills.length}; registrations: ${registrations.length}; issues: ${issues.length}; warnings: ${warnings.length}`)
  for (const skill of skills) {
    console.log(`- ${skill.name ?? skill.dir}: ${skill.entrypointChars} chars, ${skill.referenceCount} refs, registered=${skill.registered}`)
  }
  for (const issue of issues) console.log(`ERROR ${issue.code}: ${JSON.stringify(issue)}`)
  for (const warning of warnings) console.log(`WARN  ${warning.code}: ${JSON.stringify(warning)}`)
}

if (args.strict && issues.length) process.exitCode = 1
