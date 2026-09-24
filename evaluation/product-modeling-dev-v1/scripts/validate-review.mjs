import fs from 'node:fs'
import { validateReviewResult } from './review.mjs'

const files = process.argv.slice(2)
if (!files.length || files.some(file => file.startsWith('--'))) {
  process.stderr.write('usage: node validate-review.mjs <review-result.json> [more-review-results.json ...]\n')
  process.exit(2)
}

for (const file of files) {
  try {
    const review = JSON.parse(fs.readFileSync(file, 'utf8'))
    validateReviewResult(review)
    process.stdout.write(`validated review: ${file}\n`)
  } catch (error) {
    process.stderr.write(`invalid review: ${file}: ${error.message}\n`)
    process.exitCode = 1
  }
}
