import { useEffect, useRef, useState } from 'react'
import type { GeoJsonObject } from 'geojson'
import L from 'leaflet'
import { Compass, Home, MapPinned, X } from 'lucide-react'
import { GeoJSON, MapContainer, TileLayer, Tooltip } from 'react-leaflet'
import { apiFetch } from './api'

type ExploreDistrict = {
  id: number
  name: string
  bezirk: string
  boundary: GeoJsonObject
}

type ExploreAppProps = {
  onHome: () => void
}

const HAMBURG_BOUNDS = L.latLngBounds(
  [53.39, 9.72],
  [53.75, 10.32],
)

function ExploreBoundary({
  district,
  selected,
  onSelect,
}: {
  district: ExploreDistrict
  selected: boolean
  onSelect: (district: ExploreDistrict) => void
}) {
  const layerRef = useRef<L.GeoJSON | null>(null)

  useEffect(() => {
    const cleanups: Array<() => void> = []
    layerRef.current?.eachLayer((layer) => {
      if (!(layer instanceof L.Path)) return
      const element = layer.getElement()
      if (!element) return
      element.setAttribute('role', 'button')
      element.setAttribute('tabindex', '0')
      element.setAttribute('aria-label', `${district.name}, ${district.bezirk}`)
      const handleKeyDown = (event: Event) => {
        if (!(event instanceof KeyboardEvent) || (event.key !== 'Enter' && event.key !== ' ')) return
        event.preventDefault()
        onSelect(district)
      }
      element.addEventListener('keydown', handleKeyDown)
      cleanups.push(() => element.removeEventListener('keydown', handleKeyDown))
    })
    return () => cleanups.forEach((cleanup) => cleanup())
  }, [district, onSelect])

  return (
    <GeoJSON
      ref={layerRef}
      data={district.boundary}
      style={{
        color: selected ? '#075f47' : '#e8eee9',
        fillColor: selected ? '#18a573' : '#dce4df',
        fillOpacity: selected ? 0.58 : 0.08,
        opacity: selected ? 1 : 0.72,
        weight: selected ? 4 : 1.25,
      }}
      eventHandlers={{ click: () => onSelect(district) }}
    >
      {selected ? (
        <Tooltip permanent direction="center" className="explore-label">
          {district.name}
        </Tooltip>
      ) : null}
    </GeoJSON>
  )
}

/** Let visitors freely inspect Hamburg and reveal Stadtteil names by selection. */
export function ExploreApp({ onHome }: ExploreAppProps) {
  const [districts, setDistricts] = useState<ExploreDistrict[]>([])
  const [selected, setSelected] = useState<ExploreDistrict | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    apiFetch<ExploreDistrict[]>('/api/explore/districts')
      .then((result) => {
        if (!cancelled) setDistricts(result)
      })
      .catch((reason: unknown) => {
        if (!cancelled) setError(reason instanceof Error ? reason.message : 'The map could not be loaded.')
      })
    return () => {
      cancelled = true
    }
  }, [])

  const unselectedDistricts = districts.filter((district) => district.id !== selected?.id)

  return (
    <main className="explore-shell">
      <div className="map-surface explore-map" aria-label="Interactive map of Hamburg Stadtteile">
        <MapContainer
          bounds={HAMBURG_BOUNDS}
          boundsOptions={{ padding: [24, 24] }}
          minZoom={9}
          maxZoom={16}
          zoomControl={false}
          attributionControl
        >
          <TileLayer
            attribution="Imagery &copy; Esri"
            url="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
          />
          {unselectedDistricts.map((district) => (
            <ExploreBoundary key={district.id} district={district} selected={false} onSelect={setSelected} />
          ))}
          {selected ? (
            <ExploreBoundary key={selected.id} district={selected} selected onSelect={setSelected} />
          ) : null}
        </MapContainer>
      </div>

      <header className="brand-bar explore-brand">
        <button className="brand-home" type="button" onClick={onHome} aria-label="Return to mode selection" title="Home">
          <Home size={17} aria-hidden="true" />
        </button>
        <span className="brand-mark"><Compass size={18} strokeWidth={2.4} /></span>
        <span>Hamburg Explore</span>
      </header>

      <aside className={selected ? 'explore-card explore-card--selected' : 'explore-card'} aria-live="polite">
        {error ? (
          <p className="notice notice--error" role="alert">{error}</p>
        ) : selected ? (
          <>
            <button className="explore-card__close" type="button" onClick={() => setSelected(null)} aria-label="Clear selected Stadtteil">
              <X size={17} aria-hidden="true" />
            </button>
            <p className="eyebrow">Stadtteil</p>
            <h1>{selected.name}</h1>
            <p>{selected.bezirk}</p>
          </>
        ) : (
          <>
            <MapPinned size={24} aria-hidden="true" />
            <p className="eyebrow">Explore Hamburg</p>
            <h1>{districts.length === 0 ? 'Loading map…' : 'Pick a Stadtteil'}</h1>
            <p>Move around the map and select any boundary to reveal its name.</p>
          </>
        )}
      </aside>
    </main>
  )
}
