const TILE_CACHE = 'hamburg-map-tiles-v1'
const TILE_METADATA_CACHE = 'hamburg-map-tile-metadata-v1'
const TILE_CACHE_PREFIXES = ['hamburg-map-tiles-', 'hamburg-map-tile-metadata-']
const MAX_TILE_ENTRIES = 500
const MAX_TILE_AGE_MS = 30 * 24 * 60 * 60 * 1000

self.addEventListener('install', () => {
  self.skipWaiting()
})

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys()
      .then((names) => Promise.all(
        names
          .filter((name) => (
            TILE_CACHE_PREFIXES.some((prefix) => name.startsWith(prefix))
            && name !== TILE_CACHE
            && name !== TILE_METADATA_CACHE
          ))
          .map((name) => caches.delete(name)),
      ))
      .then(() => self.clients.claim()),
  )
})

self.addEventListener('fetch', (event) => {
  if (event.request.method !== 'GET' || !isEsriTile(event.request.url)) return
  event.respondWith(loadTile(event.request))
})

function isEsriTile(requestUrl) {
  const url = new URL(requestUrl)
  return url.hostname === 'server.arcgisonline.com'
    && /\/MapServer\/tile\/\d+\/\d+\/\d+$/.test(url.pathname)
}

function metadataRequest(tileUrl) {
  return new Request(`${self.location.origin}/__map_tile_metadata__/${encodeURIComponent(tileUrl)}`)
}

async function readMetadata(metadataCache, tileUrl) {
  const response = await metadataCache.match(metadataRequest(tileUrl))
  return response ? response.json() : null
}

async function storeTile(tileCache, metadataCache, request, response) {
  const metadata = {
    url: request.url,
    cachedAt: Date.now(),
  }
  await Promise.all([
    tileCache.put(request, response),
    metadataCache.put(
      metadataRequest(request.url),
      new Response(JSON.stringify(metadata), { headers: { 'Content-Type': 'application/json' } }),
    ),
  ])
  await trimTileCache(tileCache, metadataCache)
}

async function trimTileCache(tileCache, metadataCache) {
  const metadataKeys = await metadataCache.keys()
  if (metadataKeys.length <= MAX_TILE_ENTRIES) return

  const entries = (await Promise.all(metadataKeys.map(async (key) => {
    const response = await metadataCache.match(key)
    return response ? { key, ...(await response.json()) } : null
  }))).filter(Boolean)

  entries.sort((left, right) => left.cachedAt - right.cachedAt)
  const excess = entries.slice(0, Math.max(0, entries.length - MAX_TILE_ENTRIES))
  await Promise.all(excess.flatMap((entry) => [
    tileCache.delete(entry.url),
    metadataCache.delete(entry.key),
  ]))
}

async function loadTile(request) {
  const [tileCache, metadataCache] = await Promise.all([
    caches.open(TILE_CACHE),
    caches.open(TILE_METADATA_CACHE),
  ])
  const [cachedTile, metadata] = await Promise.all([
    tileCache.match(request),
    readMetadata(metadataCache, request.url),
  ])
  const fresh = cachedTile
    && metadata
    && Date.now() - metadata.cachedAt < MAX_TILE_AGE_MS

  if (fresh) return cachedTile

  try {
    const response = await fetch(request)
    if (response.ok || response.type === 'opaque') {
      await storeTile(tileCache, metadataCache, request, response.clone())
    }
    return response
  } catch (error) {
    if (cachedTile) return cachedTile
    throw error
  }
}
