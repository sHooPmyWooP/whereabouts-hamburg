import { useEffect } from 'react'
import type { GeoJsonObject } from 'geojson'
import L from 'leaflet'
import {
  CircleMarker,
  GeoJSON,
  MapContainer,
  TileLayer,
  Tooltip,
  useMap,
  ZoomControl,
} from 'react-leaflet'

export type Pin = {
  index: number
  lat: number
  lng: number
}

export type Reveal = {
  index: number
  district_name: string
  boundary: GeoJsonObject
}

export type MissedDistrict = {
  district_id: number
  district_name: string
  boundary: GeoJsonObject
  distance_km: number
}

type MapViewProps = {
  pins: Pin[]
  reveals: Reveal[]
  missedDistricts: MissedDistrict[]
  solvedPinIndices: number[]
  showPins: boolean
  previewMode: boolean
  annotateMissedDistricts: boolean
}

const HAMBURG_BOUNDS = L.latLngBounds(
  [53.39, 9.72],
  [53.75, 10.32],
)

function MapViewport({
  pins,
  showPins,
  previewMode,
}: Pick<MapViewProps, 'pins' | 'showPins' | 'previewMode'>) {
  const map = useMap()

  useEffect(() => {
    function fitViewport() {
      map.invalidateSize({ animate: false })
      if (showPins && pins.length > 0) {
        const mapSize = map.getSize()
        const desktopPanelWidth = mapSize.x > 720 ? 450 : 0
        const mobilePreviewInset = previewMode && mapSize.x <= 720
          ? Math.round(mapSize.y * 0.54)
          : 48
        const pinBounds = L.latLngBounds(pins.map((pin) => [pin.lat, pin.lng]))
        map.fitBounds(
          pinBounds,
          {
            paddingTopLeft: [desktopPanelWidth + 48, 48],
            paddingBottomRight: [48, mobilePreviewInset],
            maxZoom: 12,
          },
        )
        return
      }
      map.fitBounds(HAMBURG_BOUNDS, { padding: [20, 20] })
    }

    fitViewport()
    map.on('resize', fitViewport)
    return () => {
      map.off('resize', fitViewport)
    }
  }, [map, pins, previewMode, showPins])

  return null
}

export function MapView({
  pins,
  reveals,
  missedDistricts,
  solvedPinIndices,
  showPins,
  previewMode,
  annotateMissedDistricts,
}: MapViewProps) {
  const solved = new Set(solvedPinIndices)

  return (
    <div className="map-surface" aria-label="Map of Hamburg">
      <MapContainer
        center={[53.55, 10]}
        zoom={10}
        minZoom={9}
        maxZoom={16}
        zoomControl={false}
        attributionControl
      >
        <ZoomControl position="topright" />
        <TileLayer
          attribution="Imagery &copy; Esri"
          url="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
        />
        <MapViewport
          pins={pins}
          showPins={showPins}
          previewMode={previewMode}
        />

        {missedDistricts.map((district) => {
          const isFar = district.distance_km >= 5
          return (
            <GeoJSON
              key={`miss-${district.district_id}`}
              data={district.boundary}
              style={{
                color: isFar ? '#b52f36' : '#d66a16',
                fillColor: isFar ? '#d9484f' : '#f08c2e',
                fillOpacity: 0.3,
                opacity: 0.95,
                weight: 2,
              }}
            >
              {annotateMissedDistricts ? (
                <Tooltip
                  permanent
                  direction="center"
                  className={`miss-label${isFar ? ' miss-label--far' : ''}`}
                >
                  <span>{district.district_name}</span>
                  <small>{district.distance_km.toFixed(1)} km</small>
                </Tooltip>
              ) : null}
            </GeoJSON>
          )
        })}

        {reveals.map((item) => (
          <GeoJSON
            key={`${item.index}-${item.district_name}`}
            data={item.boundary}
            style={{
              color: solved.has(item.index) ? '#087f5b' : '#c96f16',
              fillColor: solved.has(item.index) ? '#34b27b' : '#ec9b3b',
              fillOpacity: 0.26,
              opacity: 0.9,
              weight: 2,
            }}
          />
        ))}

        {showPins &&
          pins.map((pin) => {
            const reveal = reveals.find((item) => item.index === pin.index)
            const isSolved = solved.has(pin.index)
            return (
              <CircleMarker
                key={pin.index}
                center={[pin.lat, pin.lng]}
                radius={isSolved ? 10 : 9}
                pathOptions={{
                  color: '#fffdf8',
                  fillColor: isSolved ? '#087f5b' : '#171a1b',
                  fillOpacity: 1,
                  opacity: 1,
                  weight: 3,
                }}
              >
                <Tooltip
                  permanent
                  direction="top"
                  offset={[0, -10]}
                  className={reveal ? 'pin-label pin-label--revealed' : 'pin-label'}
                >
                  {reveal?.district_name ?? pin.index + 1}
                </Tooltip>
              </CircleMarker>
            )
          })}
      </MapContainer>
    </div>
  )
}
