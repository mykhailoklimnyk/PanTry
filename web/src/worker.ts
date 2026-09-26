
interface Env {
  ASSETS: { fetch(request: Request): Promise<Response> }
  API_ORIGIN: string
  API_SECRET: string
}

const PROXY_HEADER = 'x-komora-proxy'

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url)
    if (!url.pathname.startsWith('/api/')) return env.ASSETS.fetch(request)

    if (!env.API_ORIGIN) {
      return Response.json(
        { detail: 'Воркер не знає, куди проксіювати: не заданий API_ORIGIN.' },
        { status: 503 },
      )
    }

    const target = new URL(url.pathname + url.search, env.API_ORIGIN)
    const headers = new Headers(request.headers)
    headers.set(PROXY_HEADER, env.API_SECRET)
    headers.set('host', target.host)

    return fetch(
      new Request(target, {
        method: request.method,
        headers,
        body: request.body,
        redirect: 'manual',
      }),
    )
  },
}
