from fastapi.testclient import TestClient

from app.main import app


def test_health_reports_dataset_range():
    body = TestClient(app).get("/api/health").json()
    assert body["status"] == "ok"
    assert body["cultures"] == 46792
    assert body["data_start"] == "2023-10-02"
    assert body["data_end"] == "2026-09-27"
