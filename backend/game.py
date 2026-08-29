from __future__ import annotations

import hashlib
import json
import random
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from pyproj import Transformer
from shapely import maximum_inscribed_circle
from shapely.geometry import Point, mapping, shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform

PIN_COUNT = 5
INITIAL_BUDGET = 10
PIN_BORDER_CLEARANCE_METERS = 200
PIN_BORDER_CLEARANCE_MAX_METERS = 750
PIN_BORDER_CLEARANCE_RATIO = 0.6
GENERATION_VERSION = "daily-districts-v2"
DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "hamburg-stadtteile.geojson"


@dataclass(frozen=True)
class District:
    id: int
    name: str
    bezirk: str
    boundary: dict[str, Any]
    geometry_wgs84: BaseGeometry
    geometry_metric: BaseGeometry
    pin_area_metric: BaseGeometry
    pin_clearance_meters: float


@dataclass(frozen=True)
class ChallengePin:
    index: int
    district: District
    point: Point
    point_metric: Point


@dataclass(frozen=True)
class GuessResult:
    correct: bool
    solved_pin_index: int | None
    distance_km: float | None
    missed_district: dict[str, Any] | None
    budget_remaining: int
    status: str
    reveals: list[dict[str, Any]]


class DistrictCatalog:
    def __init__(self, districts: list[District]) -> None:
        self.districts = districts
        self.by_id = {district.id: district for district in districts}

    @classmethod
    def load(cls, path: Path = DATA_PATH) -> DistrictCatalog:
        document = json.loads(path.read_text(encoding="utf-8"))
        features = document.get("features", [])
        if len(features) != 104:
            raise ValueError(f"Expected 104 districts, found {len(features)}")

        transformer = Transformer.from_crs("EPSG:4326", "EPSG:25832", always_xy=True)
        districts: list[District] = []
        for district_id, feature in enumerate(
            sorted(features, key=lambda item: item["properties"]["name"].casefold()),
            start=1,
        ):
            properties = feature["properties"]
            geometry_wgs84 = shape(feature["geometry"])
            geometry_metric = transform(transformer.transform, geometry_wgs84)
            maximum_clearance = maximum_inscribed_circle(
                geometry_metric, tolerance=1
            ).length
            pin_clearance = max(
                PIN_BORDER_CLEARANCE_METERS,
                min(
                    PIN_BORDER_CLEARANCE_MAX_METERS,
                    maximum_clearance * PIN_BORDER_CLEARANCE_RATIO,
                ),
            )
            pin_area_metric = geometry_metric.buffer(-pin_clearance)
            if pin_area_metric.is_empty:
                raise ValueError(
                    f"District {properties['name']} cannot provide the required Pin clearance"
                )
            districts.append(
                District(
                    id=district_id,
                    name=properties["name"],
                    bezirk=properties["bezirk"],
                    boundary=mapping(geometry_wgs84),
                    geometry_wgs84=geometry_wgs84,
                    geometry_metric=geometry_metric,
                    pin_area_metric=pin_area_metric,
                    pin_clearance_meters=pin_clearance,
                )
            )

        names = {district.name.casefold() for district in districts}
        if len(names) != 104:
            raise ValueError("District names must be unique")
        return cls(districts)


class ChallengeGenerator:
    def __init__(self, catalog: DistrictCatalog) -> None:
        self.catalog = catalog
        self._to_wgs84 = Transformer.from_crs(
            "EPSG:25832", "EPSG:4326", always_xy=True
        )

    def generate(self, challenge_date: date) -> list[ChallengePin]:
        seed_material = f"{GENERATION_VERSION}:{challenge_date.isoformat()}".encode()
        return self._generate(seed_material)

    def generate_seeded(self, seed: str) -> list[ChallengePin]:
        seed_material = f"{GENERATION_VERSION}:custom:{seed}".encode()
        return self._generate(seed_material)

    def _generate(self, seed_material: bytes) -> list[ChallengePin]:
        seed = int.from_bytes(hashlib.sha256(seed_material).digest()[:16], "big")
        rng = random.Random(seed)
        selected = rng.sample(self.catalog.districts, PIN_COUNT)

        pins: list[ChallengePin] = []
        for index, district in enumerate(selected):
            point_metric = self._random_point_in(district.pin_area_metric, rng)
            longitude, latitude = self._to_wgs84.transform(
                point_metric.x, point_metric.y
            )
            pins.append(
                ChallengePin(
                    index=index,
                    district=district,
                    point=Point(longitude, latitude),
                    point_metric=point_metric,
                )
            )
        return pins

    @staticmethod
    def _random_point_in(geometry: BaseGeometry, rng: random.Random) -> Point:
        min_x, min_y, max_x, max_y = geometry.bounds
        for _ in range(20_000):
            point = Point(rng.uniform(min_x, max_x), rng.uniform(min_y, max_y))
            if geometry.contains(point):
                return point
        fallback = geometry.representative_point()
        if not geometry.contains(fallback):
            raise ValueError("Could not place a point inside district geometry")
        return fallback


def reveal(pin: ChallengePin) -> dict[str, Any]:
    return {
        "index": pin.index,
        "district_name": pin.district.name,
        "boundary": pin.district.boundary,
    }


def evaluate_guess(
    pins: list[ChallengePin],
    guessed_district: District,
    solved_pin_indices: set[int],
    budget_remaining: int,
) -> GuessResult:
    unsolved = [pin for pin in pins if pin.index not in solved_pin_indices]
    matching_pin = next(
        (pin for pin in unsolved if pin.district.id == guessed_district.id), None
    )
    next_budget = budget_remaining - 1
    next_solved = set(solved_pin_indices)
    reveals: list[dict[str, Any]] = []

    if matching_pin is not None:
        next_solved.add(matching_pin.index)
        reveals.append(reveal(matching_pin))
        distance_km = None
        missed_district = None
    else:
        distance_km = round(
            min(
                guessed_district.geometry_metric.boundary.distance(pin.point_metric)
                for pin in unsolved
            )
            / 1000,
            1,
        )
        missed_district = {
            "district_id": guessed_district.id,
            "district_name": guessed_district.name,
            "boundary": guessed_district.boundary,
            "distance_km": distance_km,
        }

    finished = next_budget == 0 or len(next_solved) == len(pins)
    if finished:
        revealed_indices = {item["index"] for item in reveals}
        reveals.extend(pin for pin in map(reveal, pins) if pin["index"] not in revealed_indices)

    return GuessResult(
        correct=matching_pin is not None,
        solved_pin_index=matching_pin.index if matching_pin else None,
        distance_km=distance_km,
        missed_district=missed_district,
        budget_remaining=next_budget,
        status="finished" if finished else "in_progress",
        reveals=reveals,
    )
