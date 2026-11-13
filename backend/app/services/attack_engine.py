
import json
import networkx as nx

from app.models.database import (
    User,
    Asset,
    Relationship,
    Scenario,
    AttackPath,
    SimulationResult,
)


def build_graph(db, removed_relationship_ids=None, graph_data=None):
    """Build a directed graph from the synthetic database environment."""

    removed_ids = set(removed_relationship_ids or [])
    graph = nx.DiGraph()

    if graph_data is None:
        users = db.query(User).filter(User.is_active == True).all()
        assets = db.query(Asset).filter(Asset.is_active == True).all()
        relationships = db.query(Relationship).all()
    else:
        users = graph_data["users"]
        assets = graph_data["assets"]
        relationships = graph_data["relationships"]

    # Add active users as graph nodes.
    for user in users:
        graph.add_node(
            ("user", user.id),
            label=user.username,
            node_type="user",
            sensitivity="low",
        )

    # Add active assets as graph nodes.
    for asset in assets:
        graph.add_node(
            ("asset", asset.id),
            label=asset.name,
            node_type=asset.asset_type,
            sensitivity=asset.sensitivity,
        )

    # Add permitted connections as directed edges.
    for relation in relationships:
        if relation.id in removed_ids:
            continue

        source = (relation.source_type, relation.source_id)
        target = (relation.target_type, relation.target_id)

        if source in graph and target in graph:
            graph.add_edge(
                source,
                target,
                relationship_id=relation.id,
                permission_id=relation.permission_id,
                description=relation.description or "Access relationship",
            )

    return graph


def calculate_risk(path, graph):
    """Calculate a demonstration risk score between 0 and 100."""

    sensitivity_weights = {
        "low": 10,
        "medium": 30,
        "high": 70,
        "critical": 100,
    }

    target_sensitivity = graph.nodes[path[-1]].get(
        "sensitivity", "low"
    )

    sensitivity_score = sensitivity_weights.get(
        target_sensitivity, 10
    )

    # Shorter paths are considered easier to exploit in this demo.
    hop_count = max(len(path) - 1, 1)
    path_factor = max(0.5, 1 - (hop_count - 1) * 0.1)

    return round(min(100, sensitivity_score * path_factor), 2)


def analyze_scenario(
    db,
    scenario_id,
    removed_relationship_ids=None,
    save_results=True,
    *,
    scenario=None,
    graph_data=None,
):
    """Find paths from a scenario's entry asset to sensitive assets."""

    if scenario is None:
        scenario = db.query(Scenario).filter(
            Scenario.id == scenario_id
        ).first()

    if not scenario:
        raise ValueError("Scenario not found.")

    if not scenario.entry_asset_id:
        raise ValueError("Scenario has no entry asset.")

    graph = build_graph(
        db,
        removed_relationship_ids,
        graph_data=graph_data,
    )

    start_node = ("asset", scenario.entry_asset_id)

    if start_node not in graph:
        raise ValueError("Scenario entry asset is missing or inactive.")

    sensitive_nodes = [
        node
        for node, data in graph.nodes(data=True)
        if data.get("sensitivity") in ("high", "critical")
        and node != start_node
    ]

    discovered_paths = []

    for target in sensitive_nodes:
        paths = nx.all_simple_paths(
            graph,
            source=start_node,
            target=target,
            cutoff=8,
        )

        for path in paths:
            labels = [
                graph.nodes[node]["label"]
                for node in path
            ]

            discovered_paths.append({
                "nodes": [
                    {
                        "type": node[0],
                        "id": node[1],
                        "label": graph.nodes[node]["label"],
                    }
                    for node in path
                ],
                "labels": labels,
                "risk_score": calculate_risk(path, graph),
                "target_sensitivity": graph.nodes[target][
                    "sensitivity"
                ],
            })

    discovered_paths.sort(
        key=lambda item: item["risk_score"],
        reverse=True,
    )

    if save_results:
        for item in discovered_paths:
            record = AttackPath(
                scenario_id=scenario_id,
                path_data=json.dumps(item["nodes"]),
                risk_score=item["risk_score"],
            )
            db.add(record)

        db.commit()

    return {
        "scenario_id": scenario_id,
        "scenario_name": scenario.name,
        "entry_asset": graph.nodes[start_node]["label"],
        "total_paths": len(discovered_paths),
        "total_risk": round(
            sum(item["risk_score"] for item in discovered_paths),
            2,
        ),
        "paths": discovered_paths,
    }


def simulate_defense(db, scenario_id, relationship_ids):
    """
    Simulate multiple defensive restrictions together.

    The original relationships are never modified or deleted.
    Each simulation is stored independently.
    """

    # Validate the input.
    if not isinstance(relationship_ids, (list, tuple)):
        raise ValueError("Relationship IDs must be provided as a list.")

    if not relationship_ids:
        raise ValueError("Select at least one relationship to restrict.")

    if any(
        isinstance(item, bool)
        or not isinstance(item, int)
        or item <= 0
        for item in relationship_ids
    ):
        raise ValueError("All relationship IDs must be positive integers.")

    # Remove duplicate IDs while preserving their order.
    selected_ids = list(dict.fromkeys(relationship_ids))

    # Validate scenario and calculate the original environment.
    before = analyze_scenario(
        db,
        scenario_id,
        save_results=False,
    )

    # Ensure all selected relationships exist.
    existing_relationships = db.query(Relationship).filter(
        Relationship.id.in_(selected_ids)
    ).all()

    existing_ids = {
        relationship.id for relationship in existing_relationships
    }

    missing_ids = set(selected_ids) - existing_ids

    if missing_ids:
        raise ValueError(
            f"Relationship(s) not found: {sorted(missing_ids)}"
        )

    # Ensure selected relationships are connected to active graph nodes.
    graph = build_graph(db)

    active_relationship_ids = {
        data["relationship_id"]
        for _, _, data in graph.edges(data=True)
        if "relationship_id" in data
    }

    inactive_ids = set(selected_ids) - active_relationship_ids

    if inactive_ids:
        raise ValueError(
            "Selected relationship(s) are not part of the active "
            f"environment: {sorted(inactive_ids)}"
        )

    # Analyze the environment with ALL selected restrictions together.
    after = analyze_scenario(
        db,
        scenario_id,
        removed_relationship_ids=selected_ids,
        save_results=False,
    )

    # Calculate path and aggregate risk differences.
    blocked = max(
        0,
        before["total_paths"] - after["total_paths"],
    )

    risk_reduction = round(
        max(0, before["total_risk"] - after["total_risk"]),
        2,
    )

    if before["total_risk"] > 0:
        risk_reduction_percent = round(
            (risk_reduction / before["total_risk"]) * 100,
            2,
        )
    else:
        risk_reduction_percent = 0.0

    # Save this simulation independently.
    result = SimulationResult(
        scenario_id=scenario_id,
        before_path_count=before["total_paths"],
        after_path_count=after["total_paths"],
        blocked_paths=blocked,
        selected_relationship_ids=json.dumps(selected_ids),
        before_risk_total=before["total_risk"],
        after_risk_total=after["total_risk"],
    )

    try:
        db.add(result)
        db.commit()
        db.refresh(result)
    except Exception:
        db.rollback()
        raise

    return {
        "simulation_id": result.id,
        "scenario_id": scenario_id,
        "before": before["total_paths"],
        "after": after["total_paths"],
        "blocked": blocked,
        "before_risk_total": before["total_risk"],
        "after_risk_total": after["total_risk"],
        "risk_reduction": risk_reduction,
        "risk_reduction_percent": risk_reduction_percent,
        "removed_relationship_ids": selected_ids,
        "remaining_paths": after["paths"],
    }
