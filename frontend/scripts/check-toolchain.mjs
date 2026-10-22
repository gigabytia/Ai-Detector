import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

const root = new URL('../', import.meta.url)
const pkg = JSON.parse(readFileSync(new URL('package.json', root), 'utf8'))
const lock = JSON.parse(readFileSync(new URL('package-lock.json', root), 'utf8'))
const [major, minor, patch] = process.versions.node.split('.').map(Number)
const supported =
  (major === 22 && (minor > 22 || (minor === 22 && patch >= 2))) ||
  major > 24 ||
  (major === 24 && minor >= 15)
const expected = {
  '@vue/eslint-config-typescript': '14.9.0',
  eslint: '10.12.0',
  'eslint-plugin-vue': '10.11.1',
}
const problems = []
if (!supported)
  problems.push(`Node ${process.versions.node} is unsupported; install ^22.22.2 or >=24.15.0.`)
for (const [name, version] of Object.entries(expected)) {
  if (
    pkg.devDependencies[name] !== version ||
    lock.packages[''].devDependencies[name] !== version ||
    lock.packages[`node_modules/${name}`]?.version !== version
  )
    problems.push(`${name} must be pinned to ${version} in package.json and package-lock.json.`)
}
if (process.env.npm_config_legacy_peer_deps === 'true' || process.env.npm_config_force === 'true')
  problems.push(
    'Do not use --force or --legacy-peer-deps. Restore the versioned package.json and lockfile, then run npm ci.',
  )
if (problems.length) {
  console.error(problems.join('\n'))
  process.exitCode = 1
} else
  console.log(
    `Toolchain PASS: supported Node; coherent pinned ESLint trio (${fileURLToPath(root)}).`,
  )
