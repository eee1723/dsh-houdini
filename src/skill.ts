import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import type { Context } from '@deepseek-ai/cordis'

interface SkillRegistryLike {
  register(skill: {
    name: string
    description: string
    source: string
    provider?: string
    content: string
    path?: string
    resourceBase?: { kind: 'directory'; path: string }
  }): () => void
}

type ContextWithSkills = Context & { skills: SkillRegistryLike }

const SKILLS = [
  { name: 'houdini-trace-analysis', dir: 'houdini-trace-analysis' },
  { name: 'houdini-sop-workflow', dir: 'houdini-sop-workflow' },
  { name: 'houdini-solaris-karma-workflow', dir: 'houdini-solaris-karma-workflow' },
  { name: 'houdini-rig-animation-workflow', dir: 'houdini-rig-animation-workflow' },
  { name: 'houdini-skill-governance', dir: 'houdini-skill-governance' },
  { name: 'houdini-video-tutorial', dir: 'houdini-video-tutorial' },
] as const

function parseSkill(markdown: string, expectedName: string): { description: string; content: string } {
  const match = markdown.match(/^---\r?\n([\s\S]*?)\r?\n---\r?\n([\s\S]*)$/)
  if (!match) throw new Error(`${expectedName}: SKILL.md frontmatter is missing or malformed`)
  const name = match[1].match(/^name:\s*(.+)$/m)?.[1]?.trim()
  const description = match[1].match(/^description:\s*(.+)$/m)?.[1]?.trim()
  if (name !== expectedName || !description) {
    throw new Error(`${expectedName}: frontmatter name/description is invalid`)
  }
  return { description, content: match[2].trim() }
}

const DEFINITIONS = SKILLS.map(({ name, dir }) => {
  const url = new URL(`../skills/${dir}/SKILL.md`, import.meta.url)
  return {
    name,
    url,
    dir: fileURLToPath(new URL(`../skills/${dir}/`, import.meta.url)),
    ...parseSkill(readFileSync(url, 'utf8'), name),
  }
})

/** Register packaged dsh-houdini skills in the plugin's current scope. */
export function registerBundledSkills(ctx: Context): void {
  const skills = (ctx as ContextWithSkills).skills
  for (const definition of DEFINITIONS) {
    skills.register({
      name: definition.name,
      description: definition.description,
      source: 'bundled',
      provider: 'dsh-houdini',
      content: definition.content,
      path: fileURLToPath(definition.url),
      resourceBase: { kind: 'directory', path: definition.dir },
    })
  }
}
