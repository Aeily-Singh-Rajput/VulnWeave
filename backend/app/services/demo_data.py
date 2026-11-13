
from app.models.database import (
    User,
    Asset,
    Permission,
    Relationship,
    Scenario,
)


def seed_demo_data(db):
    """Create a fictional environment for VulnWeave demonstrations."""

    existing = db.query(Scenario).filter(
        Scenario.name == "VulnWeave Demo Environment"
    ).first()

    if existing:
        return {
            "message": "Demo environment already exists.",
            "scenario_id": existing.id,
        }

    # Demo user
    user = User(
        username="demo_admin",
        email="demo_admin@vulnweave.local",
        role="administrator",
    )

    # Demo assets
    account = Asset(
        name="Compromised User Account",
        asset_type="account",
        description="Simulated compromised account",
        sensitivity="low",
    )

    web_app = Asset(
        name="Web Application",
        asset_type="application",
        description="Internal web application",
        sensitivity="medium",
    )

    app_server = Asset(
        name="Application Server",
        asset_type="server",
        description="Application processing server",
        sensitivity="medium",
    )

    backup_server = Asset(
        name="Backup Server",
        asset_type="server",
        description="Backup environment",
        sensitivity="medium",
    )

    database = Asset(
        name="Customer Database",
        asset_type="database",
        description="Fictional sensitive customer records",
        sensitivity="critical",
    )

    db.add_all([
        user,
        account,
        web_app,
        app_server,
        backup_server,
        database,
    ])
    db.flush()

    # Permissions
    read_permission = Permission(
        name="Read Access",
        description="Allows reading a resource",
    )

    admin_permission = Permission(
        name="Administrative Access",
        description="Allows administrative access",
    )

    db.add_all([read_permission, admin_permission])
    db.flush()

    # Directed relationships: source -> target
    connections = [
        Relationship(
            source_type="asset",
            source_id=account.id,
            target_type="asset",
            target_id=web_app.id,
            permission_id=read_permission.id,
            description="Account can access web application",
        ),
        Relationship(
            source_type="asset",
            source_id=web_app.id,
            target_type="asset",
            target_id=app_server.id,
            permission_id=admin_permission.id,
            description="Web application can access application server",
        ),
        Relationship(
            source_type="asset",
            source_id=app_server.id,
            target_type="asset",
            target_id=database.id,
            permission_id=read_permission.id,
            description="Application server can access customer database",
        ),
        Relationship(
            source_type="asset",
            source_id=account.id,
            target_type="asset",
            target_id=backup_server.id,
            permission_id=read_permission.id,
            description="Account can access backup server",
        ),
        Relationship(
            source_type="asset",
            source_id=backup_server.id,
            target_type="asset",
            target_id=database.id,
            permission_id=admin_permission.id,
            description="Backup server can access customer database",
        ),
    ]

    db.add_all(connections)
    db.flush()

    scenario = Scenario(
        name="VulnWeave Demo Environment",
        description=(
            "Synthetic environment for demonstrating "
            "attack path discovery and defensive simulation."
        ),
        entry_asset_id=account.id,
    )

    db.add(scenario)
    db.commit()

    return {
        "message": "Demo environment created successfully.",
        "scenario_id": scenario.id,
        "entry_asset": account.name,
        "assets_created": 5,
        "relationships_created": 5,
    }
