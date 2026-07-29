import asyncio
from dataclasses import dataclass
from typing import Annotated

import boto3
from botocore.config import Config
from fastapi import APIRouter, Depends, status
from pydantic import BaseModel
from redis.asyncio import Redis

from app.core.settings import Settings, get_settings
from app.db.session import check_database

router = APIRouter(tags=["system"])


class HealthResponse(BaseModel):
    status: str
    service: str


class ReadinessChecks(BaseModel):
    database: bool
    redis: bool
    object_storage: bool


class ReadinessResponse(BaseModel):
    status: str
    checks: ReadinessChecks


@dataclass(frozen=True)
class ReadinessChecker:
    settings: Settings

    async def database(self) -> bool:
        return await check_database()

    async def redis(self) -> bool:
        redis = Redis.from_url(self.settings.redis_url)
        try:
            return bool(await redis.ping())
        except Exception:
            return False
        finally:
            await redis.aclose()

    async def object_storage(self) -> bool:
        client = boto3.client(
            "s3",
            endpoint_url=self.settings.s3_endpoint_url,
            aws_access_key_id=self.settings.s3_access_key_id,
            aws_secret_access_key=self.settings.s3_secret_access_key,
            config=Config(signature_version="s3v4"),
        )
        try:
            await asyncio.to_thread(client.head_bucket, Bucket=self.settings.s3_bucket)
        except Exception:
            return False
        return True


def get_readiness_checker(settings: Annotated[Settings, Depends(get_settings)]) -> ReadinessChecker:
    return ReadinessChecker(settings=settings)


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok", service="memory-api")


@router.get("/ready", response_model=ReadinessResponse, status_code=status.HTTP_200_OK)
async def ready(
    checker: Annotated[ReadinessChecker, Depends(get_readiness_checker)],
) -> ReadinessResponse:
    checks = ReadinessChecks(
        database=await checker.database(),
        redis=await checker.redis(),
        object_storage=await checker.object_storage(),
    )
    is_ready = checks.database and checks.redis and checks.object_storage
    return ReadinessResponse(status="ready" if is_ready else "not_ready", checks=checks)
