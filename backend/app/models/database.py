
import os
from datetime import datetime

from dotenv import load_dotenv
from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    String,
    Boolean,
    DateTime,
    ForeignKey,
    Text,
    Float,
)
from sqlalchemy.engine import URL
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

from app.database.connection import DRIVER, DB_PROVIDER

SERVER = os.getenv("DB_SERVER", "localhost")
DATABASE = os.getenv("DB_NAME", "VulnWeaveDB")
load_dotenv()


def build_database_url():
    if DB_PROVIDER == "azure":
        username = os.getenv("AZURE_SQL_USERNAME")
        password = os.getenv("AZURE_SQL_PASSWORD")
        server = os.getenv("AZURE_SQL_SERVER")
        database = os.getenv("AZURE_SQL_DATABASE")

        if not all([username, password, server, database]):
            raise ValueError("Azure SQL configuration is incomplete. Check backend/.env.")

        return URL.create(
            "mssql+pyodbc",
            username=username,
            password=password,
            host=server,
            port=1433,
            database=database,
            query={
                "driver": DRIVER,
                "Encrypt": "yes",
                "TrustServerCertificate": "no",
                "Connection Timeout": "30",
            },
        )

    if DB_PROVIDER == "local":
        return URL.create(
            "mssql+pyodbc",
            host=SERVER,
            database=DATABASE,
            query={
                "driver": DRIVER,
                "trusted_connection": "yes",
                "TrustServerCertificate": "yes",
            },
        )

    raise ValueError("Invalid DB_PROVIDER. Choose 'local' or 'azure'.")


engine = create_engine(
    build_database_url(),
    pool_pre_ping=True,
    fast_executemany=True,
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)

Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(100), unique=True, nullable=False)
    email = Column(String(150), unique=True)
    role = Column(String(50), default="user")
    is_active = Column(Boolean, default=True)


class Asset(Base):
    __tablename__ = "assets"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(150), nullable=False)
    asset_type = Column(String(50), nullable=False)
    description = Column(Text)
    sensitivity = Column(String(30), default="medium")
    is_active = Column(Boolean, default=True)


class Permission(Base):
    __tablename__ = "permissions"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    description = Column(Text)


class Relationship(Base):
    __tablename__ = "relationships"

    id = Column(Integer, primary_key=True, index=True)
    source_type = Column(String(30), nullable=False)
    source_id = Column(Integer, nullable=False)
    target_type = Column(String(30), nullable=False)
    target_id = Column(Integer, nullable=False)
    permission_id = Column(
        Integer,
        ForeignKey("permissions.id"),
        nullable=True,
    )
    description = Column(Text)


class Scenario(Base):
    __tablename__ = "scenarios"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(150), nullable=False)
    description = Column(Text)
    entry_asset_id = Column(Integer, ForeignKey("assets.id"))
    created_at = Column(DateTime, default=datetime.utcnow)


class AttackPath(Base):
    __tablename__ = "attack_paths"

    id = Column(Integer, primary_key=True, index=True)
    scenario_id = Column(Integer, ForeignKey("scenarios.id"))
    path_data = Column(Text, nullable=False)
    risk_score = Column(Float, default=0.0)
    discovered_at = Column(DateTime, default=datetime.utcnow)


class DefensiveChange(Base):
    __tablename__ = "defensive_changes"

    id = Column(Integer, primary_key=True, index=True)
    scenario_id = Column(Integer, ForeignKey("scenarios.id"))
    relationship_id = Column(
        Integer,
        ForeignKey("relationships.id"),
    )
    change_type = Column(String(50), nullable=False)
    description = Column(Text)


class SimulationResult(Base):
    __tablename__ = "simulation_results"

    id = Column(Integer, primary_key=True, index=True)
    scenario_id = Column(Integer, ForeignKey("scenarios.id"))

    before_path_count = Column(Integer, default=0)
    after_path_count = Column(Integer, default=0)
    blocked_paths = Column(Integer, default=0)

    selected_relationship_ids = Column(Text, nullable=True)
    before_risk_total = Column(Float, default=0.0)
    after_risk_total = Column(Float, default=0.0)

    created_at = Column(DateTime, default=datetime.utcnow)


def create_tables():
    Base.metadata.create_all(bind=engine)
