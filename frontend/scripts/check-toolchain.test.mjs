import assert from 'node:assert/strict'
import { mkdtempSync, mkdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { spawnSync } from 'node:child_process'
import test from 'node:test'

const names = {
  '@vue/eslint-config-typescript': '14.9.0',
  eslint: '10.12.0',
  'eslint-plugin-vue': '10.11.1',
}
function probe(edit = () => {}, flags = {}) {
  const root = mkdtempSync(join(tmpdir(), 'Ai Detector toolchain '))
  try {
    mkdirSync(join(root, 'scripts'))
    writeFileSync(
      join(root, 'scripts/check-toolchain.mjs'),
      readFileSync(new URL('./check-toolchain.mjs', import.meta.url)),
    )
    const pkg = { devDependencies: { ...names } }
    const lock = {
      packages: {
        '': { devDependencies: { ...names } },
        ...Object.fromEntries(
          Object.entries(names).map(([name, version]) => [`node_modules/${name}`, { version }]),
        ),
      },
    }
    edit(pkg, lock)
    writeFileSync(join(root, 'package.json'), JSON.stringify(pkg))
    writeFileSync(join(root, 'package-lock.json'), JSON.stringify(lock))
    return spawnSync(process.execPath, [join(root, 'scripts/check-toolchain.mjs')], {
      cwd: tmpdir(),
      env: {
        ...process.env,
        npm_config_force: 'false',
        npm_config_legacy_peer_deps: 'false',
        ...flags,
      },
      encoding: 'utf8',
    })
  } finally {
    rmSync(root, { recursive: true, force: true })
  }
}

test('coherent pins work from another cwd and a path with spaces', () => {
  assert.equal(probe().status, 0)
})
test('old Vue config is rejected', () => {
  const r = probe((pkg) => {
    pkg.devDependencies['@vue/eslint-config-typescript'] = '14.0.1'
  })
  assert.equal(r.status, 1)
  assert.match(r.stderr, /14.9.0/)
})
test('ESLint9 instead of the tested ESLint10 is rejected', () => {
  assert.equal(
    probe((pkg) => {
      pkg.devDependencies.eslint = '9.39.5'
    }).status,
    1,
  )
})
test('lock resolved version mismatch is rejected', () => {
  assert.equal(
    probe((pkg, lock) => {
      lock.packages['node_modules/eslint-plugin-vue'].version = '9.33.0'
    }).status,
    1,
  )
})
test('lock root declaration mismatch is rejected', () => {
  assert.equal(
    probe((pkg, lock) => {
      lock.packages[''].devDependencies.eslint = '^10.12.0'
    }).status,
    1,
  )
})
test('legacy peer bypass is rejected', () => {
  assert.equal(probe(undefined, { npm_config_legacy_peer_deps: 'true' }).status, 1)
})
test('force bypass is rejected', () => {
  assert.equal(probe(undefined, { npm_config_force: 'true' }).status, 1)
})
