
import json
import logging

logger = logging.getLogger(__name__)

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Body,
    Query,
)
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.models.database import (
    SessionLocal,
    Asset,
    Relationship,
    Scenario,
    Permission,
    SimulationResult,
)

from app.schemas.assets import AssetInput
from app.schemas.relationships import RelationshipInput

from app.services.demo_data import seed_demo_data

from app.services.attack_engine import (
    analyze_scenario,
    simulate_defense,
)

from app.services.weakness_engine import analyze_weaknesses
from app.services.report_engine import generate_security_report


router = APIRouter()


# =========================================================
# DATABASE SESSION
# =========================================================

def get_db():
    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()


# =========================================================
# COMMON HELPERS
# =========================================================

def get_scenario_or_404(db: Session, scenario_id: int):
    scenario = db.query(Scenario).filter(
        Scenario.id == scenario_id
    ).first()

    if not scenario:
        raise HTTPException(
            status_code=404,
            detail="Scenario not found.",
        )

    return scenario


def get_asset_or_404(db: Session, asset_id: int):
    asset = db.query(Asset).filter(
        Asset.id == asset_id,
        Asset.is_active == True,
    ).first()

    if not asset:
        raise HTTPException(
            status_code=404,
            detail="Asset not found or inactive.",
        )

    return asset


def get_asset_endpoint_name(
    db: Session,
    endpoint_type: str,
    endpoint_id: int,
):
    if endpoint_type == "asset":
        asset = db.query(Asset).filter(
            Asset.id == endpoint_id,
            Asset.is_active == True,
        ).first()

        return asset.name if asset else f"Unknown Asset ({endpoint_id})"

    return f"Unknown {endpoint_type} ({endpoint_id})"


def parse_relationship_ids(value):
    """
    Safely decode relationship IDs stored as JSON.
    """

    try:
        parsed = json.loads(value or "[]")

        if not isinstance(parsed, list):
            return []

        return [
            int(item)
            for item in parsed
            if isinstance(item, int) and not isinstance(item, bool)
        ]

    except (json.JSONDecodeError, TypeError, ValueError):
        return []


# =========================================================
# DEMO ENVIRONMENT
# =========================================================

@router.post("/demo/seed")
def create_demo_environment(
    db: Session = Depends(get_db),
):
    try:
        return seed_demo_data(db)

    except Exception:
        db.rollback()
        logger.exception("Unable to create demo environment")

        raise HTTPException(
            status_code=500,
            detail="Unable to create demo environment.",
        )


# =========================================================
# ASSET MANAGEMENT
# =========================================================

@router.get("/assets")
def get_assets(
    db: Session = Depends(get_db),
):
    assets = db.query(Asset).filter(
        Asset.is_active == True
    ).all()

    return [
        {
            "id": asset.id,
            "name": asset.name,
            "type": asset.asset_type,
            "asset_type": asset.asset_type,
            "description": asset.description,
            "sensitivity": asset.sensitivity,
            "active": asset.is_active,
        }
        for asset in assets
    ]


@router.post("/assets", status_code=201)
def create_asset(
    payload: AssetInput,
    db: Session = Depends(get_db),
):
    try:
        name = payload.name.strip()

        if len(name) < 2:
            raise HTTPException(
                status_code=422,
                detail="Asset name must contain at least 2 characters.",
            )

        existing = db.query(Asset).filter(
            Asset.name == name,
            Asset.is_active == True,
        ).first()

        if existing:
            raise HTTPException(
                status_code=409,
                detail="An active asset with this name already exists.",
            )

        asset = Asset(
            name=name,
            asset_type=payload.asset_type,
            description=payload.description,
            sensitivity=payload.sensitivity,
            is_active=True,
        )

        db.add(asset)
        db.commit()
        db.refresh(asset)

        return {
            "message": "Asset created successfully.",
            "asset": {
                "id": asset.id,
                "name": asset.name,
                "type": asset.asset_type,
                "asset_type": asset.asset_type,
                "description": asset.description,
                "sensitivity": asset.sensitivity,
                "active": asset.is_active,
            },
        }

    except HTTPException:
        db.rollback()
        raise

    except Exception:
        db.rollback()
        logger.exception("Unable to create asset")

        raise HTTPException(
            status_code=500,
            detail="Unable to create asset.",
        )


@router.put("/assets/{asset_id}")
def update_asset(
    asset_id: int,
    payload: AssetInput,
    db: Session = Depends(get_db),
):
    try:
        asset = get_asset_or_404(db, asset_id)

        name = payload.name.strip()

        if len(name) < 2:
            raise HTTPException(
                status_code=422,
                detail="Asset name must contain at least 2 characters.",
            )

        duplicate = db.query(Asset).filter(
            Asset.name == name,
            Asset.id != asset_id,
            Asset.is_active == True,
        ).first()

        if duplicate:
            raise HTTPException(
                status_code=409,
                detail="Another active asset already uses this name.",
            )

        asset.name = name
        asset.asset_type = payload.asset_type
        asset.description = payload.description
        asset.sensitivity = payload.sensitivity

        db.commit()
        db.refresh(asset)

        return {
            "message": "Asset updated successfully.",
            "asset": {
                "id": asset.id,
                "name": asset.name,
                "type": asset.asset_type,
                "asset_type": asset.asset_type,
                "description": asset.description,
                "sensitivity": asset.sensitivity,
                "active": asset.is_active,
            },
        }

    except HTTPException:
        db.rollback()
        raise

    except Exception:
        db.rollback()
        logger.exception("Unable to update asset")

        raise HTTPException(
            status_code=500,
            detail="Unable to update asset.",
        )


@router.delete("/assets/{asset_id}")
def delete_asset(
    asset_id: int,
    db: Session = Depends(get_db),
):
    try:
        asset = get_asset_or_404(db, asset_id)

        # Remove relationships connected to this asset.
        db.query(Relationship).filter(
            Relationship.source_type == "asset",
            Relationship.source_id == asset_id,
        ).delete(synchronize_session=False)

        db.query(Relationship).filter(
            Relationship.target_type == "asset",
            Relationship.target_id == asset_id,
        ).delete(synchronize_session=False)

        # Soft-delete the asset.
        asset.is_active = False

        db.commit()

        return {
            "success": True,
            "message": f"Asset {asset_id} deleted successfully.",
        }

    except HTTPException:
        db.rollback()
        raise

    except Exception:
        db.rollback()
        logger.exception("Unable to delete asset")

        raise HTTPException(
            status_code=500,
            detail="Unable to delete asset.",
        )


# =========================================================
# PERMISSION MANAGEMENT
# =========================================================

@router.get("/permissions")
def get_permissions(
    db: Session = Depends(get_db),
):
    permissions = db.query(Permission).all()

    return [
        {
            "id": permission.id,
            "name": permission.name,
            "description": permission.description,
        }
        for permission in permissions
    ]


# =========================================================
# RELATIONSHIP MANAGEMENT
# =========================================================

@router.get("/relationships")
def get_relationships(
    db: Session = Depends(get_db),
):
    relationships = db.query(Relationship).all()

    permissions = {
        permission.id: permission.name
        for permission in db.query(Permission).all()
    }

    return [
        {
            "id": relation.id,
            "source_type": relation.source_type,
            "source_id": relation.source_id,
            "source_name": get_asset_endpoint_name(
                db,
                relation.source_type,
                relation.source_id,
            ),
            "target_type": relation.target_type,
            "target_id": relation.target_id,
            "target_name": get_asset_endpoint_name(
                db,
                relation.target_type,
                relation.target_id,
            ),
            "permission_id": relation.permission_id,
            "permission_name": permissions.get(
                relation.permission_id,
                "Unspecified",
            ),
            "description": relation.description,
        }
        for relation in relationships
    ]


@router.post("/relationships", status_code=201)
def create_relationship(
    payload: RelationshipInput,
    db: Session = Depends(get_db),
):
    try:
        if payload.source_id == payload.target_id:
            raise HTTPException(
                status_code=422,
                detail="An asset cannot be connected to itself.",
            )

        source = get_asset_or_404(
            db,
            payload.source_id,
        )

        target = get_asset_or_404(
            db,
            payload.target_id,
        )

        permission = None

        if payload.permission_id is not None:
            permission = db.query(Permission).filter(
                Permission.id == payload.permission_id
            ).first()

            if not permission:
                raise HTTPException(
                    status_code=404,
                    detail="Permission not found.",
                )

        existing = db.query(Relationship).filter(
            Relationship.source_type == "asset",
            Relationship.source_id == payload.source_id,
            Relationship.target_type == "asset",
            Relationship.target_id == payload.target_id,
            Relationship.permission_id == payload.permission_id,
        ).first()

        if existing:
            raise HTTPException(
                status_code=409,
                detail="This relationship already exists.",
            )

        relation = Relationship(
            source_type="asset",
            source_id=payload.source_id,
            target_type="asset",
            target_id=payload.target_id,
            permission_id=payload.permission_id,
            description=(
                payload.description.strip()
                if payload.description
                else ""
            ),
        )

        db.add(relation)
        db.commit()
        db.refresh(relation)

        return {
            "message": "Relationship created successfully.",
            "relationship": {
                "id": relation.id,
                "source_type": relation.source_type,
                "source_id": relation.source_id,
                "source_name": source.name,
                "target_type": relation.target_type,
                "target_id": relation.target_id,
                "target_name": target.name,
                "permission_id": relation.permission_id,
                "permission_name": (
                    permission.name
                    if permission
                    else "Unspecified"
                ),
                "description": relation.description,
            },
        }

    except HTTPException:
        db.rollback()
        raise

    except Exception:
        db.rollback()
        logger.exception("Unable to create relationship")

        raise HTTPException(
            status_code=500,
            detail="Unable to create relationship.",
        )


# =========================================================
# SCENARIO MANAGEMENT
# =========================================================

@router.get("/scenarios")
def get_scenarios(
    db: Session = Depends(get_db),
):
    scenarios = db.query(Scenario).all()

    return [
        {
            "id": scenario.id,
            "name": scenario.name,
            "description": scenario.description,
            "entry_asset_id": scenario.entry_asset_id,
        }
        for scenario in scenarios
    ]


# =========================================================
# ATTACK PATH ANALYSIS
# =========================================================

@router.post("/scenarios/{scenario_id}/analyze")
def run_analysis(
    scenario_id: int,
    db: Session = Depends(get_db),
):
    try:
        return analyze_scenario(
            db,
            scenario_id,
        )

    except ValueError as error:
        raise HTTPException(
            status_code=404,
            detail=str(error),
        )

    except Exception:
        db.rollback()
        logger.exception("Attack path analysis failed")

        raise HTTPException(
            status_code=500,
            detail="Attack path analysis failed.",
        )


# =========================================================
# DEFENSIVE WHAT-IF SIMULATION
# =========================================================

@router.post("/scenarios/{scenario_id}/simulate-defense")
def run_defense_simulation(
    scenario_id: int,
    relationship_ids: list[int] = Body(...),
    db: Session = Depends(get_db),
):
    try:
        if not relationship_ids:
            raise HTTPException(
                status_code=422,
                detail="Select at least one relationship to simulate.",
            )

        if any(
            not isinstance(item, int) or isinstance(item, bool)
            for item in relationship_ids
        ):
            raise HTTPException(
                status_code=422,
                detail="Relationship IDs must be integers.",
            )

        # Remove duplicate IDs while preserving order.
        relationship_ids = list(dict.fromkeys(relationship_ids))

        return simulate_defense(
            db,
            scenario_id,
            relationship_ids,
        )

    except HTTPException:
        db.rollback()
        raise

    except ValueError as error:
        db.rollback()

        raise HTTPException(
            status_code=404,
            detail=str(error),
        )

    except Exception:
        db.rollback()
        logger.exception("Defense simulation failed")

        raise HTTPException(
            status_code=500,
            detail="Defense simulation failed.",
        )


# =========================================================
# SIMULATION HISTORY
# =========================================================

@router.get("/scenarios/{scenario_id}/simulations")
def get_simulation_history(
    scenario_id: int,
    db: Session = Depends(get_db),
):
    scenario = get_scenario_or_404(
        db,
        scenario_id,
    )

    results = (
        db.query(SimulationResult)
        .filter(
            SimulationResult.scenario_id == scenario_id
        )
        .order_by(
            SimulationResult.created_at.desc()
        )
        .all()
    )

    history = []

    for result in results:
        relationship_ids = parse_relationship_ids(
            result.selected_relationship_ids
        )

        risk_before = float(
            result.before_risk_total or 0
        )

        risk_after = float(
            result.after_risk_total or 0
        )

        reduction = max(
            0,
            risk_before - risk_after,
        )

        history.append({
            "simulation_id": result.id,
            "scenario_id": result.scenario_id,
            "before": result.before_path_count or 0,
            "after": result.after_path_count or 0,
            "blocked": result.blocked_paths or 0,
            "before_risk_total": risk_before,
            "after_risk_total": risk_after,
            "risk_reduction": reduction,
            "risk_reduction_percent": (
                round(
                    reduction / risk_before * 100,
                    2,
                )
                if risk_before > 0
                else 0
            ),
            "removed_relationship_ids": relationship_ids,
            "created_at": (
                result.created_at.isoformat()
                if result.created_at
                else None
            ),
        })

    return {
        "scenario_id": scenario_id,
        "scenario_name": scenario.name,
        "total_simulations": len(history),
        "simulations": history,
    }


# =========================================================
# WEAKNESS DETECTION AND PRIORITIZATION
# =========================================================

@router.get("/scenarios/{scenario_id}/weaknesses")
def get_weaknesses(
    scenario_id: int,
    db: Session = Depends(get_db),
):
    try:
        return analyze_weaknesses(
            db,
            scenario_id,
        )

    except ValueError as error:
        raise HTTPException(
            status_code=404,
            detail=str(error),
        )

    except Exception:
        db.rollback()
        logger.exception("Weakness analysis failed")

        raise HTTPException(
            status_code=500,
            detail="Weakness analysis failed.",
        )


# =========================================================
# PDF SECURITY REPORT
# =========================================================

@router.get("/scenarios/{scenario_id}/report")
def download_security_report(
    scenario_id: int,
    simulation_id: int | None = Query(
        default=None,
        description="Optional saved simulation ID.",
    ),
    db: Session = Depends(get_db),
):
    try:
        scenario = get_scenario_or_404(
            db,
            scenario_id,
        )

        simulation = None
        if simulation_id is not None:
            if simulation_id <= 0:
                raise HTTPException(
                    status_code=422,
                    detail="Simulation ID must be a positive integer.",
                )

            simulation = db.query(SimulationResult).filter(
                SimulationResult.id == simulation_id,
                SimulationResult.scenario_id == scenario_id,
            ).first()

            if not simulation:
                raise HTTPException(
                    status_code=404,
                    detail="Simulation not found for this scenario.",
                )

        pdf_bytes = generate_security_report(
            db,
            scenario_id,
            simulation_id=simulation_id,
            scenario_record=scenario,
            simulation_record=simulation,
        )

        if simulation_id is not None:
            filename = (
                f"VulnWeave_Simulation_Report_"
                f"{scenario_id}_{simulation_id}.pdf"
            )
        else:
            filename = (
                f"VulnWeave_Security_Report_{scenario_id}.pdf"
            )

        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": (
                    f'attachment; filename="{filename}"'
                )
            },
        )

    except HTTPException:
        raise

    except ValueError as error:
        raise HTTPException(
            status_code=404,
            detail=str(error),
        )

    except Exception:
        db.rollback()
        logger.exception("Security report generation failed")

        raise HTTPException(
            status_code=500,
            detail="Security report generation failed.",
        )
