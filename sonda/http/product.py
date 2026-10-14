from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from sonda.checks.execution import ExecutionService
from sonda.http.access import Access
from sonda.http.errors import HttpError
from sonda.incidents.service import IncidentService


class CheckInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    key: str = Field(min_length=36, max_length=36)

    @field_validator("key")
    @classmethod
    def valid_uuid(cls, value: str) -> str:
        return str(UUID(value))


class MonitorInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    expected_version: int = Field(ge=1)
    enabled: bool | None = None
    fixture_mode: Literal["available", "unavailable"] | None = None


class AcknowledgementInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    expected_version: int = Field(ge=1)
    comment: str = Field(min_length=3, max_length=500)


async def body[Input: BaseModel](request: Request, model: type[Input]) -> Input:
    try:
        return model.model_validate(await request.json())
    except (ValidationError, ValueError):
        raise HttpError(422, "INPUT_INVALID", "Confira os campos e a versão atual.") from None


def product_router(access: Access) -> APIRouter:
    router = APIRouter(prefix="/api")
    execution = ExecutionService(access.db)
    incidents = IncidentService(access.db)

    @router.patch("/monitors/{monitor_id}")
    async def change(request: Request, monitor_id: UUID) -> dict[str, object]:
        await access.authorize(request)
        scope = await access.scope(request)
        fields = await body(request, MonitorInput)
        return await access.monitors.change(
            scope,
            str(monitor_id),
            fields.expected_version,
            enabled=fields.enabled,
            fixture_mode=fields.fixture_mode,
        )

    @router.post("/monitors/{monitor_id}/checks")
    async def check(request: Request, monitor_id: UUID) -> JSONResponse:
        await access.authorize(request)
        scope = await access.scope(request)
        fields = await body(request, CheckInput)
        result = await execution.execute(scope, str(monitor_id), fields.key)
        return JSONResponse(
            jsonable_encoder(result), status_code=202 if result.state == "pending" else 200
        )

    @router.get("/checks/{check_id}")
    async def get_check(request: Request, check_id: UUID) -> JSONResponse:
        scope = await access.scope(request)
        return JSONResponse(
            jsonable_encoder(await execution.checks.get_check(scope, str(check_id)))
        )

    @router.get("/incidents/{incident_id}")
    async def get_incident(request: Request, incident_id: UUID) -> dict[str, object]:
        return await incidents.get(await access.scope(request), str(incident_id))

    @router.post("/incidents/{incident_id}/ack")
    async def acknowledge(request: Request, incident_id: UUID) -> dict[str, object]:
        await access.authorize(request)
        fields = await body(request, AcknowledgementInput)
        return await incidents.acknowledge(
            await access.scope(request), str(incident_id), fields.comment, fields.expected_version
        )

    return router
