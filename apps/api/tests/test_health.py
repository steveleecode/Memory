from collections.abc import Iterator
from contextlib import contextmanager

from fastapi.testclient import TestClient

from app.api.health import ReadinessChecker, get_readiness_checker
from app.core.settings import Settings
from app.main import create_app


class PassingReadinessChecker(ReadinessChecker):
    async def database(self) -> bool:
        return True

    async def redis(self) -> bool:
        return True

    async def object_storage(self) -> bool:
        return True


class FailingReadinessChecker(ReadinessChecker):
    async def database(self) -> bool:
        return False

    async def redis(self) -> bool:
        return True

    async def object_storage(self) -> bool:
        return True


@contextmanager
def client_with_checker(checker: ReadinessChecker) -> Iterator[TestClient]:
    app = create_app()
    app.dependency_overrides[get_readiness_checker] = lambda: checker
    with TestClient(app) as client:
        yield client


def test_health() -> None:
    app = create_app()
    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "memory-api"}


def test_local_vite_origin_can_preflight_api_requests() -> None:
    app = create_app()
    with TestClient(app) as client:
        response = client.options(
            "/auth/sign-in",
            headers={
                "Origin": "http://127.0.0.1:5174",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:5174"
    assert "POST" in response.headers["access-control-allow-methods"]


def test_ready_when_dependencies_pass() -> None:
    with client_with_checker(PassingReadinessChecker(settings=Settings())) as client:
        response = client.get("/ready")

    assert response.status_code == 200
    assert response.json()["status"] == "ready"
    assert response.json()["checks"] == {
        "database": True,
        "redis": True,
        "object_storage": True,
    }


def test_ready_reports_not_ready_when_dependency_fails() -> None:
    with client_with_checker(FailingReadinessChecker(settings=Settings())) as client:
        response = client.get("/ready")

    assert response.status_code == 200
    assert response.json()["status"] == "not_ready"
    assert response.json()["checks"]["database"] is False
