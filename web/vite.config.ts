import { execSync } from 'node:child_process'

import { svelte } from '@sveltejs/vite-plugin-svelte'
import { defineConfig } from 'vite'


function shell(command: string): string {
  try {
    return execSync(command, { encoding: 'utf-8', stdio: ['ignore', 'pipe', 'ignore'] }).trim()
  } catch {
    return ''
  }
}

function commit(): string {
  return process.env.GITHUB_SHA || shell('git rev-parse HEAD')
}

function repoUrl(): string {
  const server = process.env.GITHUB_SERVER_URL
  const repo = process.env.GITHUB_REPOSITORY
  if (server && repo) return `${server}/${repo}`
  const origin = shell('git remote get-url origin')
  if (!origin) return ''
  return origin
    .replace(/^git@([^:]+):/, 'https://$1/')
    .replace(/\.git$/, '')
}

function uiVersion(): string {
  const now = new Date()
  const pad = (value: number) => String(value).padStart(2, '0')
  const date = `${now.getFullYear()}.${pad(now.getMonth() + 1)}.${pad(now.getDate())}`
  return `${date}-${pad(now.getHours())}${pad(now.getMinutes())}`
}

export default defineConfig({
  plugins: [svelte()],
  define: {
    __BUILD_COMMIT__: JSON.stringify(commit()),
    __BUILD_REPO__: JSON.stringify(repoUrl()),
    __BUILD_VERSION__: JSON.stringify(uiVersion()),
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    target: 'baseline-widely-available',
  },
})
