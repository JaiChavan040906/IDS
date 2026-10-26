"""Data warehouse + OLAP endpoints (DWM Module 1). Read-only for analysts and admins;
only an admin can run the ETL job."""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from ids import olap
from ids.api.db import User, audit
from ids.api.security import admin_only, analyst_or_admin, get_db


def warehouse_on(request: Request):
    """The whole warehouse API disappears when the portal runs without the warehouse."""
    if not getattr(request.app.state, "warehouse_enabled", False):
        raise HTTPException(404, "Not Found")


router = APIRouter(prefix="/api/dw", tags=["warehouse"], dependencies=[Depends(warehouse_on)])


def _wh(request: Request) -> str:
    return request.app.state.etl.wh_path


def _guard(fn, *args, **kw):
    try:
        return fn(*args, **kw)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    except olap.QueryError as e:
        raise HTTPException(400, str(e))


@router.get("/overview")
def overview(request: Request, user: User = Depends(analyst_or_admin)):
    etl = request.app.state.etl
    return {**olap.overview(etl.wh_path, etl.oltp_path), "etl": etl.state}


@router.get("/meta")
def meta(user: User = Depends(analyst_or_admin)):
    return olap.meta()


@router.get("/tables")
def tables(request: Request, user: User = Depends(analyst_or_admin)):
    return _guard(olap.tables, _wh(request))


@router.get("/tables/{name}")
def table_sample(name: str, request: Request, limit: int = 8, user: User = Depends(analyst_or_admin)):
    return _guard(olap.sample, _wh(request), name, limit)


class Axis(BaseModel):
    dim: str
    level: str


class Filter(Axis):
    values: list[str]


class OlapIn(BaseModel):
    cube: Literal["flows", "alerts"] = "flows"
    measure: str = "flows"
    rows: Axis
    cols: Axis | None = None
    filters: list[Filter] = []


@router.post("/olap")
def olap_query(body: OlapIn, request: Request, user: User = Depends(analyst_or_admin)):
    return _guard(olap.run_query, _wh(request), body.cube, body.measure, body.rows.model_dump(),
                  body.cols.model_dump() if body.cols else None, [f.model_dump() for f in body.filters])


class CubeIn(BaseModel):
    cube: Literal["flows", "alerts"] = "flows"
    measure: str = "flows"
    x: Axis
    y: Axis
    z: Axis
    filters: list[Filter] = []


@router.post("/cube")
def cube_view(body: CubeIn, request: Request, user: User = Depends(analyst_or_admin)):
    """Data for the 3-D cube picture on the OLAP page."""
    return _guard(olap.run_cube, _wh(request), body.cube, body.measure, body.x.model_dump(),
                  body.y.model_dump(), body.z.model_dump(), [f.model_dump() for f in body.filters])


@router.get("/members")
def members(cube: str, dim: str, level: str, request: Request, user: User = Depends(analyst_or_admin)):
    return _guard(olap.members, _wh(request), cube, dim, level)


@router.get("/compare/{which}")
def compare(which: str, request: Request, user: User = Depends(analyst_or_admin)):
    return _guard(olap.compare, _wh(request), which)


@router.get("/factless")
def factless(request: Request, user: User = Depends(analyst_or_admin)):
    return _guard(olap.factless, _wh(request))


class EtlIn(BaseModel):
    mode: Literal["full", "incremental"]


@router.post("/etl")
def run_etl(body: EtlIn, request: Request, admin: User = Depends(admin_only), db=Depends(get_db)):
    if not request.app.state.etl.start(body.mode):
        raise HTTPException(409, "An ETL job is already running")
    audit(db, admin.username, "warehouse.etl", body.mode)
    db.commit()
    return request.app.state.etl.state
