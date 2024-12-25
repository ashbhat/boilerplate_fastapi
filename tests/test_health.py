from fastapi.testclient import TestClient

def test_health_check(client: TestClient) -> None:
    """Test the health check endpoint."""
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
