from fastapi.testclient import TestClient


def test_explore_districts_returns_public_geometry(client: TestClient) -> None:
    """Explore exposes every named Stadtteil boundary without authentication."""
    response = client.get("/api/explore/districts")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "public, max-age=86400"
    districts = response.json()
    assert len(districts) == 104
    assert all(
        {
            "id",
            "name",
            "bezirk",
            "boundary",
            "fun_facts",
        } == district.keys()
        for district in districts
    )
    assert all(
        district["boundary"]["type"] in {"Polygon", "MultiPolygon"}
        for district in districts
    )
    assert all(
        1 <= len(district["fun_facts"]) <= 5
        and all(isinstance(fact, str) and fact.endswith(".") for fact in district["fun_facts"])
        for district in districts
    )
