from fastapi.testclient import TestClient


def test_map_districts_returns_versioned_cacheable_geometry(client: TestClient) -> None:
    """Every map mode can reuse the same immutable Stadtteil geometry."""
    response = client.get("/api/map/districts/v1")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "public, max-age=31536000, immutable"
    districts = response.json()
    assert len(districts) == 104
    assert all(
        {"id", "name", "bezirk", "boundary"} == district.keys()
        for district in districts
    )
    assert all(
        district["boundary"]["type"] in {"Polygon", "MultiPolygon"}
        for district in districts
    )


def test_explore_districts_returns_lightweight_public_facts(client: TestClient) -> None:
    """Explore facts stay separate from the shared geometry payload."""
    response = client.get("/api/explore/districts")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "public, max-age=86400"
    districts = response.json()
    assert len(districts) == 104
    assert all(
        {"id", "name", "bezirk", "fun_facts"} == district.keys()
        for district in districts
    )
    assert all(
        1 <= len(district["fun_facts"]) <= 5
        and all(isinstance(fact, str) and fact.endswith(".") for fact in district["fun_facts"])
        for district in districts
    )
