import logging
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from app.api import routes, incidents, navigation, sos
from app.services.routing_service import RoutingServiceError

logging.basicConfig(level=logging.INFO)
app = FastAPI(title="SENTINEL Module 2 - Safe Routes & Adaptive Rerouting")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.exception_handler(RoutingServiceError)
async def routing_error(_: Request, exc: RoutingServiceError):
    return JSONResponse(status_code=502, content={"detail": str(exc)})

for r in (routes.router, incidents.router, navigation.router, sos.router):
    app.include_router(r)

@app.get("/health")
def health(): return {"ok": True}
