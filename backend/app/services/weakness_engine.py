
from app.models.database import (
    Asset,
    User,
    Relationship,
    Scenario,
)

from app.services.attack_engine import analyze_scenario


def get_endpoint_name(db, endpoint_type, endpoint_id, endpoint_names=None):
    """Resolve a relationship endpoint to its display name."""

    if endpoint_names is not None:
        name = endpoint_names.get((endpoint_type, endpoint_id))
        if name is not None:
            return name

    if endpoint_type == "asset":
        item = db.query(Asset).filter(
            Asset.id == endpoint_id
        ).first()

    elif endpoint_type == "user":
        item = db.query(User).filter(
            User.id == endpoint_id
        ).first()

    else:
        item = None

    if item:
        return getattr(item, "name", None) or getattr(
            item, "username", f"{endpoint_type} {endpoint_id}"
        )

    return f"{endpoint_type} {endpoint_id}"


def analyze_weaknesses(
    db,
    scenario_id,
    *,
    scenario=None,
    baseline_analysis=None,
    graph_data=None,
):
    """
    Evaluate each relationship by temporarily removing it
    and measuring its effect on paths to sensitive resources.

    The priority score is a VulnWeave demonstration heuristic,
    not an industry-standard vulnerability score.
    """

    if scenario is None:
        scenario = db.query(Scenario).filter(
            Scenario.id == scenario_id
        ).first()

    if not scenario:
        raise ValueError("Scenario not found.")

    baseline = baseline_analysis
    if baseline is None:
        baseline = analyze_scenario(
            db,
            scenario_id,
            save_results=False,
            scenario=scenario,
            graph_data=graph_data,
        )

    baseline_paths = baseline["total_paths"]

    baseline_risk = sum(
        path["risk_score"] for path in baseline["paths"]
    )

    relationships = (
        graph_data["relationships"]
        if graph_data is not None
        else db.query(Relationship).all()
    )
    endpoint_names = (
        graph_data.get("endpoint_names")
        if graph_data is not None
        else None
    )

    findings = []

    for relation in relationships:

        after = analyze_scenario(
            db,
            scenario_id,
            removed_relationship_ids=[relation.id],
            save_results=False,
            scenario=scenario,
            graph_data=graph_data,
        )

        paths_after = after["total_paths"]

        risk_after = sum(
            path["risk_score"] for path in after["paths"]
        )

        blocked_paths = max(0, baseline_paths - paths_after)

        risk_reduction = max(
            0,
            baseline_risk - risk_after,
        )

        path_reduction_percent = (
            blocked_paths / baseline_paths * 100
            if baseline_paths else 0
        )

        risk_reduction_percent = (
            risk_reduction / baseline_risk * 100
            if baseline_risk else 0
        )

        # Equal weighting of path reduction and risk reduction.
        priority_score = round(
            (path_reduction_percent * 0.5)
            + (risk_reduction_percent * 0.5),
            2,
        )

        if priority_score >= 50:
            priority = "High"
        elif priority_score > 0:
            priority = "Medium"
        else:
            priority = "Low"

        findings.append({
            "relationship_id": relation.id,
            "source": get_endpoint_name(
                db,
                relation.source_type,
                relation.source_id,
                endpoint_names,
            ),
            "target": get_endpoint_name(
                db,
                relation.target_type,
                relation.target_id,
                endpoint_names,
            ),
            "description": relation.description,
            "baseline_paths": baseline_paths,
            "remaining_paths": paths_after,
            "blocked_paths": blocked_paths,
            "risk_before": round(baseline_risk, 2),
            "risk_after": round(risk_after, 2),
            "risk_reduction": round(risk_reduction, 2),
            "risk_reduction_percent": round(
                risk_reduction_percent, 2
            ),
            "priority_score": priority_score,
            "priority": priority,
        })

    findings.sort(
        key=lambda item: item["priority_score"],
        reverse=True,
    )

    return {
        "scenario_id": scenario_id,
        "scenario_name": scenario.name,
        "baseline_paths": baseline_paths,
        "baseline_risk": round(baseline_risk, 2),
        "total_relationships_reviewed": len(relationships),
        "findings": findings,
    }
