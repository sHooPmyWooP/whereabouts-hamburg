#!/usr/bin/env python3
"""Normalize Hamburg's official Stadtteil WFS export into the seed shape
DistrictRepository expects: one Feature per district carrying exactly
{name, bezirk, boundary}, where boundary is the district's polygon geometry.

Source: LGV Hamburg, "Verwaltungsgrenzen" WFS, layer app:stadtteile.
  https://geodienste.hamburg.de/HH_WFS_Verwaltungsgrenzen
License: dl-de/by-2-0 (Datenlizenz Deutschland Namensnennung 2.0). Attribute the LGV.
CRS: output is EPSG:4326 (WGS84) lon/lat, matching GeoJSON conventions. The
Geometry module reprojects to EPSG:25832 for metric distance math.

Refetch the raw source (104 features, ~5.8 MB) with:
  curl "https://geodienste.hamburg.de/HH_WFS_Verwaltungsgrenzen?service=WFS&version=2.0.0&request=GetFeature&typeNames=app:stadtteile&outputFormat=application/geo%2Bjson&srsName=EPSG:4326" -o hamburg-stadtteile.raw.geojson
"""
import json
import pathlib

HERE = pathlib.Path(__file__).parent
RAW = HERE / "hamburg-stadtteile.raw.geojson"
OUT = HERE / "hamburg-stadtteile.geojson"


def main() -> None:
    raw = json.loads(RAW.read_text(encoding="utf-8"))
    features = []
    for feat in raw["features"]:
        props = feat["properties"]
        features.append(
            {
                "type": "Feature",
                "properties": {
                    "name": props["stadtteil_name"],
                    "bezirk": props["bezirk_name"],
                },
                "geometry": feat["geometry"],  # boundary polygon (MultiPolygon, WGS84)
            }
        )

    features.sort(key=lambda f: (f["properties"]["bezirk"], f["properties"]["name"]))

    names = [f["properties"]["name"] for f in features]
    assert len(names) == len(set(names)), "district names must be unique"

    out = {
        "type": "FeatureCollection",
        "metadata": {
            "source": "LGV Hamburg WFS app:stadtteile (Verwaltungsgrenzen)",
            "license": "dl-de/by-2-0",
            "crs": "EPSG:4326",
            "count": len(features),
        },
        "features": features,
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {OUT.name}: {len(features)} districts")


if __name__ == "__main__":
    main()
