import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database.connection import test_connection
from app.models.database import create_tables
from app.api.routes import router

app = FastAPI(
    title="VulnWeave",
    description="Attack Path Analysis and Defensive Optimization System",
    version="1.0.0",
)

frontend_origins = [
    origin.strip().rstrip("/")
    for origin in os.getenv("FRONTEND_URL", "").split(",")
    if origin.strip()
]

# Allow the React frontend to communicate with FastAPI.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
        *frontend_origins,
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.get("/")
def home():
    return {
        "project": "VulnWeave",
        "status": "Backend running",
        "version": "1.0.0",
    }


@app.get("/health")
def health():
    return test_connection()


@app.post("/database/initialize")
def initialize_database():
    try:
        create_tables()

        return {
            "success": True,
            "message": "All database tables created successfully.",
        }

    except Exception as error:
        return {
            "success": False,
            "error": str(error),
        }
