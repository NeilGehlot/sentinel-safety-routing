import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api import routes, incidents, navigation, sos

logging.basicConfig(level=logging.INFO)
app = FastAPI(title="SENTINEL Module 2 - Safe Routes & Adaptive Rerouting")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
for r in (routes.router, incidents.router, navigation.router, sos.router):
    app.include_router(r)

@app.get("/health")
def health(): return {"ok": True}
