
import { useCallback, useEffect, useMemo, useState } from "react";

import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  MarkerType,
} from "@xyflow/react";

import {
  Activity,
  AlertTriangle,
  ArrowRight,
  Boxes,
  Database,
  FileDown,
  GitBranch,
  Globe,
  LockKeyhole,
  PanelLeftClose,
  PanelLeftOpen,
  RefreshCw,
  Server,
  ShieldCheck,
  Settings,
  Unlock,
  UserRound,
  Network,
  X,
} from "lucide-react";

import "@xyflow/react/dist/style.css";
import "./App.css";

const API = (import.meta.env.VITE_API_URL || "http://127.0.0.1:8000").replace(/\/$/, "");
const nodePositions = {
  1: { x: 40, y: 190 },
  2: { x: 380, y: 55 },
  3: { x: 710, y: 55 },
  4: { x: 380, y: 340 },
  5: { x: 1080, y: 190 },
};

/* =========================================================
   API HELPER
========================================================= */

async function apiRequest(path, options = {}) {
  const response = await fetch(`${API}${path}`, options);
  const data = await response.json().catch(() => ({}));

  if (!response.ok) {
    throw new Error(
      data.detail || `Request failed with status ${response.status}`
    );
  }

  return data;
}

/* =========================================================
   ASSET ICON HELPER
========================================================= */

function getAssetIcon(type) {
  switch (type?.toLowerCase()) {
    case "account":
      return <UserRound size={19} />;
    case "database":
      return <Database size={19} />;
    case "application":
      return <Globe size={19} />;
    case "server":
      return <Server size={19} />;
    default:
      return <Boxes size={19} />;
  }
}

/* =========================================================
   MAIN APPLICATION
========================================================= */

function App() {
  /* ----------------------- STATE ------------------------ */

    /* ---------------- THEME & NAVIGATION ---------------- */

  const [theme, setTheme] = useState(() => {
    return localStorage.getItem("vulnweave-theme") || "light";
  });

  const [activePage, setActivePage] = useState("overview");
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

  useEffect(() => {
    localStorage.setItem("vulnweave-theme", theme);
  }, [theme]);
  
  const [assets, setAssets] = useState([]);
  const [relationships, setRelationships] = useState([]);
  const [scenarios, setScenarios] = useState([]);

  const [scenarioId, setScenarioId] = useState("");

  // Multiple relationship selection for defensive simulations
  const [selectedRelationshipIds, setSelectedRelationshipIds] =
    useState([]);

  // Saved simulation history
  const [simulationHistory, setSimulationHistory] = useState([]);
  const [historyLoading, setHistoryLoading] = useState(false);

  const [selectedAssetId, setSelectedAssetId] = useState(null);
  const [isTopologyLocked, setIsTopologyLocked] = useState(true);

  const [assetModalOpen, setAssetModalOpen] = useState(false);
  const [editingAssetId, setEditingAssetId] = useState(null);
  const [assetSaving, setAssetSaving] = useState(false);
  const [assetFormError, setAssetFormError] = useState("");

  const [assetForm, setAssetForm] = useState({
    name: "",
    asset_type: "server",
    description: "",
    sensitivity: "medium",
  });

  const [analysis, setAnalysis] = useState(null);
  const [simulation, setSimulation] = useState(null);
  const [weaknessReport, setWeaknessReport] = useState(null);

  const [apiConnected, setApiConnected] = useState(false);
  const [loading, setLoading] = useState(false);
  const [weaknessLoading, setWeaknessLoading] = useState(false);
  const [reportLoading, setReportLoading] = useState(false);
  const [error, setError] = useState("");

  /* ------------------- LOAD DATA ------------------------ */

  const refreshWorkspace = useCallback(async () => {
    setLoading(true);
    setError("");

    try {
      const [health, assetData, relationData, scenarioData] =
        await Promise.all([
          apiRequest("/health"),
          apiRequest("/assets"),
          apiRequest("/relationships"),
          apiRequest("/scenarios"),
        ]);

      setApiConnected(health.success === true);
      setAssets(assetData);
      setRelationships(relationData);
      setScenarios(scenarioData);

      setScenarioId((current) => current || String(scenarioData[0]?.id ?? ""));
    } catch (err) {
      setApiConnected(false);
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refreshWorkspace();
  }, [refreshWorkspace]);

  /* ---------------- SIMULATION HISTORY ------------------ */

  const loadSimulationHistory = useCallback(async () => {
    if (!scenarioId) {
      setSimulationHistory([]);
      return;
    }

    setHistoryLoading(true);

    try {
      const result = await apiRequest(
        `/scenarios/${scenarioId}/simulations`
      );

      setSimulationHistory(result.simulations || []);
    } catch (err) {
      setError(`Unable to load simulation history: ${err.message}`);
    } finally {
      setHistoryLoading(false);
    }
  }, [scenarioId]);

  useEffect(() => {
    loadSimulationHistory();
  }, [loadSimulationHistory]);

  /* ---------------- SELECTED ASSET ---------------------- */

  const selectedAsset = useMemo(
    () => assets.find((asset) => asset.id === selectedAssetId) || null,
    [assets, selectedAssetId]
  );

  /* ---------------- ATTACK PATHS ------------------------ */

  const activePaths = simulation
    ? simulation.remaining_paths || []
    : analysis?.paths || [];

  const highlightedEdgeIds = useMemo(() => {
    const ids = new Set();

    activePaths.forEach((path) => {
      const pathNodes = path.nodes || [];

      for (let index = 0; index < pathNodes.length - 1; index += 1) {
        const source = pathNodes[index];
        const target = pathNodes[index + 1];

        const relation = relationships.find(
          (item) =>
            item.source_type === source.type &&
            item.source_id === source.id &&
            item.target_type === target.type &&
            item.target_id === target.id
        );

        if (relation) {
          ids.add(relation.id);
        }
      }
    });

    return ids;
  }, [activePaths, relationships]);

  /* --------------- RELATIONSHIP HELPERS ----------------- */

  const getRelationshipLabel = (relation) => {
    const source =
      assets.find((asset) => asset.id === relation.source_id)?.name ||
      `Asset ${relation.source_id}`;

    const target =
      assets.find((asset) => asset.id === relation.target_id)?.name ||
      `Asset ${relation.target_id}`;

    return `${source} → ${target}`;
  };

  const getRelationshipPriority = (relationshipId) => {
    const finding = weaknessReport?.findings?.find(
      (item) => item.relationship_id === relationshipId
    );

    return finding?.priority || "Not assessed";
  };

  const getRelationshipPermission = (relation) =>
    relation.permission_name || "Unspecified";

  /* ---------------- MULTI-SELECTION HELPERS ------------- */

  const toggleRelationshipSelection = (relationshipId) => {
    setSelectedRelationshipIds((current) =>
      current.includes(relationshipId)
        ? current.filter((id) => id !== relationshipId)
        : [...current, relationshipId]
    );
  };

  const selectAllRelationships = () => {
    setSelectedRelationshipIds(
      relationships.map((item) => item.id)
    );
  };

  const clearRelationshipSelection = () => {
    setSelectedRelationshipIds([]);
  };

  /* ---------------- ASSET RELATIONSHIPS ----------------- */

  const incomingRelationships = useMemo(() => {
    if (!selectedAsset) return [];

    return relationships.filter(
      (relation) =>
        relation.target_type === "asset" &&
        relation.target_id === selectedAsset.id
    );
  }, [selectedAsset, relationships]);

  const outgoingRelationships = useMemo(() => {
    if (!selectedAsset) return [];

    return relationships.filter(
      (relation) =>
        relation.source_type === "asset" &&
        relation.source_id === selectedAsset.id
    );
  }, [selectedAsset, relationships]);

  /* ------------------- GRAPH NODES ---------------------- */

  const graphNodes = useMemo(
    () =>
      assets.map((asset, index) => {
        const position = nodePositions[asset.id] || {
          x: 80 + (index % 3) * 330,
          y: 100 + Math.floor(index / 3) * 230,
        };

        const isSelected = selectedAssetId === asset.id;

        return {
          id: `asset-${asset.id}`,
          position,
          type: "default",
          draggable: !isTopologyLocked,
          selectable: true,
          focusable: true,
          data: {
            label: (
              <div
                className={`asset-node ${asset.sensitivity} ${
                  isSelected ? "selected" : ""
                }`}
                role="button"
                tabIndex={0}
                title={`Click to inspect ${asset.name}`}
                aria-label={`Inspect ${asset.name}`}
              >
                <div className="asset-node-icon">
                  {getAssetIcon(asset.asset_type || asset.type)}
                </div>

                <div className="asset-node-info">
                  <strong>{asset.name}</strong>
                  <span>{asset.asset_type || asset.type}</span>
                </div>

                <span className={`sensitivity-pill ${asset.sensitivity}`}>
                  {asset.sensitivity}
                </span>
              </div>
            ),
          },
          style: {
            width: 245,
            padding: 0,
            border: "none",
            background: "transparent",
            boxShadow: "none",
          },
        };
      }),
    [assets, selectedAssetId, isTopologyLocked]
  );

  /* ------------------- GRAPH EDGES ---------------------- */

  const graphEdges = useMemo(() => {
    const removedIds = new Set(simulation?.removed_relationship_ids || []);

    const findingsById = new Map(
      (weaknessReport?.findings || []).map((finding) => [
        finding.relationship_id,
        finding,
      ])
    );

    return relationships.map((relation) => {
      const isRemoved = removedIds.has(relation.id);
      const isHighlighted = highlightedEdgeIds.has(relation.id);

      const isSelectedConnection =
        selectedAssetId !== null &&
        ((relation.source_type === "asset" &&
          relation.source_id === selectedAssetId) ||
          (relation.target_type === "asset" &&
            relation.target_id === selectedAssetId));

      const priority = findingsById.get(relation.id)?.priority;

      let color = "#9aa7b8";

      if (isRemoved) color = "#a5aebd";
      else if (isSelectedConnection) color = "#4f9382";
      else if (priority === "High") color = "#d65c5c";
      else if (priority === "Medium") color = "#d69b65";
      else if (isHighlighted) color = "#4f9382";

      let label = "";

      if (isRemoved) label = "RESTRICTED";
      else if (priority === "High") label = "HIGH RISK";
      else if (priority === "Medium") label = "MEDIUM RISK";
      else if (isHighlighted) label = "ATTACK PATH";

      return {
        id: `relationship-${relation.id}`,
        source: `asset-${relation.source_id}`,
        target: `asset-${relation.target_id}`,
        type: "smoothstep",
        animated: isHighlighted && !isRemoved,
        label,
        labelStyle: {
          fill: "#657184",
          fontSize: 10,
          fontWeight: 700,
        },
        style: {
          stroke: color,
          strokeWidth: isSelectedConnection
            ? 4
            : isHighlighted
              ? 3
              : 2,
          strokeDasharray: isRemoved ? "7 5" : "0",
          opacity: isRemoved ? 0.55 : 1,
        },
        markerEnd: {
          type: MarkerType.ArrowClosed,
          color,
        },
      };
    });
  }, [
    relationships,
    highlightedEdgeIds,
    simulation,
    weaknessReport,
    selectedAssetId,
  ]);

  /* --------------- ATTACK PATH ANALYSIS ----------------- */

  const runAnalysis = async () => {
    if (!scenarioId) {
      setError("Please select a scenario.");
      return;
    }

    setLoading(true);
    setError("");
    setSimulation(null);

    try {
      const result = await apiRequest(
        `/scenarios/${scenarioId}/analyze`,
        { method: "POST" }
      );

      setAnalysis(result);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  /* ---------------- DEFENSIVE SIMULATION ---------------- */

  const runSimulation = async () => {
    if (!scenarioId) {
      setError("Please select a scenario.");
      return;
    }

    if (selectedRelationshipIds.length === 0) {
      setError("Select at least one relationship to restrict.");
      return;
    }

    setLoading(true);
    setError("");

    try {
      const result = await apiRequest(
        `/scenarios/${scenarioId}/simulate-defense`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(selectedRelationshipIds),
        }
      );

      setSimulation(result);

      // Update history independently. A history-refresh failure
      // should not undo a successful simulation.
      try {
        const history = await apiRequest(
          `/scenarios/${scenarioId}/simulations`
        );

        setSimulationHistory(history.simulations || []);
      } catch (historyError) {
        setError(
          `Simulation completed, but history could not refresh: ${historyError.message}`
        );
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  /* ---------------- WEAKNESS ASSESSMENT ----------------- */

  const runWeaknessAssessment = async () => {
    if (!scenarioId) {
      setError("Please select a scenario.");
      return;
    }

    setWeaknessLoading(true);
    setError("");

    try {
      const result = await apiRequest(
        `/scenarios/${scenarioId}/weaknesses`
      );

      setWeaknessReport(result);
    } catch (err) {
      setError(err.message);
    } finally {
      setWeaknessLoading(false);
    }
  };

  /* ---------------- PDF REPORT DOWNLOAD --------------- */

  const downloadSecurityReport = async () => {
    if (!scenarioId) {
      setError("Please select a scenario.");
      return;
    }

    setReportLoading(true);
    setError("");

    try {
      const response = await fetch(
        `${API}/scenarios/${scenarioId}/report`
      );

      if (!response.ok) {
        let message = `Report download failed (${response.status})`;

        try {
          const data = await response.json();
          message = data.detail || message;
        } catch {
          // Keep the default message.
        }

        throw new Error(message);
      }

      const pdfBlob = await response.blob();
      const downloadUrl = window.URL.createObjectURL(pdfBlob);

      const link = document.createElement("a");
      link.href = downloadUrl;
      link.download = `VulnWeave_Security_Report_${scenarioId}.pdf`;

      document.body.appendChild(link);
      link.click();
      link.remove();

      window.setTimeout(() => {
        window.URL.revokeObjectURL(downloadUrl);
      }, 1000);
    } catch (err) {
      setError(err.message);
    } finally {
      setReportLoading(false);
    }
  };

  /* ---------------- ASSET MANAGEMENT -------------------- */

  const openAddAsset = () => {
    setEditingAssetId(null);
    setAssetFormError("");

    setAssetForm({
      name: "",
      asset_type: "server",
      description: "",
      sensitivity: "medium",
    });

    setError("");
    setAssetModalOpen(true);
  };

  const openEditAsset = (asset) => {
    setEditingAssetId(asset.id);
    setAssetFormError("");

    setAssetForm({
      name: asset.name,
      asset_type: asset.asset_type || asset.type || "server",
      description: asset.description || "",
      sensitivity: asset.sensitivity || "medium",
    });

    setError("");
    setAssetModalOpen(true);
  };

  const closeAssetModal = () => {
    if (assetSaving) return;

    setAssetModalOpen(false);
    setAssetFormError("");
  };

  const saveAsset = async (event) => {
    event.preventDefault();
    setAssetFormError("");

    const cleanName = assetForm.name.trim();

    if (cleanName.length < 2) {
      setAssetFormError(
        "Asset name must contain at least 2 characters."
      );
      return;
    }

    setAssetSaving(true);
    setError("");

    try {
      const payload = {
        name: cleanName,
        asset_type: assetForm.asset_type,
        description: assetForm.description.trim(),
        sensitivity: assetForm.sensitivity,
      };

      const isEditing = editingAssetId !== null;

      const result = await apiRequest(
        isEditing ? `/assets/${editingAssetId}` : "/assets",
        {
          method: isEditing ? "PUT" : "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        }
      );

      setAssetModalOpen(false);
      setAssetFormError("");

      if (result.asset?.id) {
        setSelectedAssetId(result.asset.id);
      }

      await refreshWorkspace();

      if (result.asset?.id) {
        setSelectedAssetId(result.asset.id);
      }
    } catch (err) {
      setAssetFormError(
        err.message || "Unable to save the asset."
      );
    } finally {
      setAssetSaving(false);
    }
  };

  /* ---------------- RESET ANALYSIS ---------------------- */

  const resetAnalysis = () => {
    setAnalysis(null);
    setSimulation(null);
    setError("");
  };

  /* ---------------- DASHBOARD VALUES ------------------- */

  const currentPathCount = simulation
    ? simulation.after
    : analysis?.total_paths ?? 0;

  const highestRisk = activePaths.length
    ? Math.max(
        ...activePaths.map((path) => Number(path.risk_score) || 0)
      )
    : 0;
  const latestSimulation = simulationHistory[0] || null;
  const defenseSummary = simulation || latestSimulation;

  const pageTitles = {
    overview: "Overview",
    topology: "System Topology",
    analysis: "Attack Path Analysis",
    defense: "Defense Simulation",
    weakness: "Weakness Assessment",
    history: "Simulation History",
    reports: "Reports",
    settings: "Settings",
  };

  const pageHeadings = {
    overview: "Security posture at a glance",
    topology: "Assets and relationships",
    analysis: "Explore reachable paths",
    defense: "Model defensive changes",
    weakness: "Prioritize high-impact access",
    history: "Recorded simulation outcomes",
    reports: "Scenario security report",
    settings: "Appearance preferences",
  };

  const isOverview = activePage === "overview";
  const showWorkspace = [
    "overview",
    "topology",
    "analysis",
    "defense",
  ].includes(activePage);

  const handleScenarioChange = (event) => {
    setScenarioId(event.target.value);
    resetAnalysis();
    setWeaknessReport(null);
    setSelectedAssetId(null);
    setSelectedRelationshipIds([]);
  };

  const renderScenarioSelect = (id) => (
    <label className="scenario-picker" htmlFor={id}>
      <span>Scenario</span>
      <select id={id} value={scenarioId} onChange={handleScenarioChange}>
        {scenarios.map((scenario) => (
          <option key={scenario.id} value={scenario.id}>
            {scenario.name}
          </option>
        ))}
      </select>
    </label>
  );

  /* ======================================================
     USER INTERFACE
  ====================================================== */

  return (
<div className="app-shell" data-theme={theme}>
        {/* HEADER */}

      {/* SIDEBAR + MAIN LAYOUT */}

<div className={`app-layout ${sidebarCollapsed ? "sidebar-collapsed" : ""}`}>
  <aside className="sidebar">
    <div className="sidebar-brand">
      <div className="brand-icon">
        <Network size={23} />
      </div>

      {!sidebarCollapsed && (
        <div>
          <h2>VulnWeave</h2>
          <span>ATTACK PATH INTELLIGENCE</span>
        </div>
      )}

    </div>

    <div className="sidebar-section-label">
      {!sidebarCollapsed && "WORKSPACE"}
    </div>

    <nav className="sidebar-nav">
      {[
        { id: "overview", label: "Overview", icon: Activity },
        { id: "topology", label: "System Topology", icon: Network },
        { id: "analysis", label: "Attack Path Analysis", icon: GitBranch },
        { id: "defense", label: "Defense Simulation", icon: ShieldCheck },
        { id: "weakness", label: "Weakness Assessment", icon: AlertTriangle },
        { id: "history", label: "Simulation History", icon: RefreshCw },
        { id: "reports", label: "Reports", icon: FileDown },
      ].map((item) => {
        const Icon = item.icon;

        return (
          <button
            type="button"
            key={item.id}
            className={`sidebar-nav-item ${activePage === item.id ? "active" : ""}`}
            onClick={() => setActivePage(item.id)}
            title={item.label}
            aria-label={item.label}
            aria-current={activePage === item.id ? "page" : undefined}
          >
            <Icon size={19} />
            {!sidebarCollapsed && <span>{item.label}</span>}
          </button>
        );
      })}
    </nav>

    <div className="sidebar-bottom">
      <div className="sidebar-bottom-actions">
        <button
          type="button"
          className="sidebar-toggle"
          onClick={() => setSidebarCollapsed((value) => !value)}
          title={sidebarCollapsed ? "Expand dashboard" : "Collapse dashboard"}
          aria-label={sidebarCollapsed ? "Expand dashboard" : "Collapse dashboard"}
        >
          {sidebarCollapsed ? (
            <PanelLeftOpen size={18} />
          ) : (
            <PanelLeftClose size={18} />
          )}
        </button>
        <button
          type="button"
          className={`sidebar-nav-item ${activePage === "settings" ? "active" : ""}`}
          onClick={() => setActivePage("settings")}
          title="Settings"
          aria-label="Settings"
          aria-current={activePage === "settings" ? "page" : undefined}
        >
          <Settings size={19} />
          {!sidebarCollapsed && <span>Settings</span>}
        </button>
      </div>
    </div>
  </aside>

  <div className="main-area">
    <header className="topbar">
      <div>
        <span className="topbar-caption">SECURITY OPERATIONS</span>
        <h2>{pageTitles[activePage]}</h2>
      </div>

      <div className="header-actions">
        <div className="connection-status">
          <span className={`status-dot ${apiConnected ? "online" : "offline"}`} />
          {apiConnected ? "API Connected" : "API Disconnected"}
        </div>

        <button
          className="refresh-button"
          onClick={refreshWorkspace}
          disabled={loading}
        >
          <RefreshCw size={16} />
          Refresh
        </button>
      </div>
    </header>

      <main className="page-content">
        <section className="page-intro">
          <p className="eyebrow">
            {isOverview ? "SECURITY POSTURE" : "WORKSPACE"}
          </p>
          <h1>{pageHeadings[activePage]}</h1>
          <p className="subtitle">
            {isOverview
              ? "A clear view of your assets, attack paths, and defensive posture."
              : activePage === "topology"
                ? "Inspect assets, relationships, and exposure paths across your environment."
                : activePage === "analysis"
                  ? "Review reachable paths and their risk using the selected scenario."
                  : activePage === "defense"
                    ? "Select relationships to restrict and compare the resulting paths and risk."
                    : activePage === "weakness"
                      ? "Rank access relationships by their simulated impact on attack paths."
                      : activePage === "history"
                        ? "Review saved defensive simulations and their recorded outcomes."
                        : activePage === "reports"
                          ? "Generate and download the security report for the selected scenario."
                          : activePage === "settings"
                            ? "Choose how the VulnWeave workspace appears on this device."
                            : ""}
          </p>
        </section>

        {/* GENERAL ERROR */}

        {error && (
          <div className="error-message">
            <AlertTriangle size={17} />
            {error}
          </div>
        )}

        {/* STATISTICS */}

        {isOverview && <section className="stats-grid">
          <div className="stat-card">
            <div className="stat-icon sage">
              <Boxes size={20} />
            </div>

            <div>
              <span>Active Assets</span>
              <strong>{assets.length}</strong>
            </div>
          </div>

          <div className="stat-card">
            <div className="stat-icon mint">
              <GitBranch size={20} />
            </div>

            <div>
              <span>Attack Paths</span>
              <strong>
                {analysis || simulation ? currentPathCount : "—"}
              </strong>
            </div>
          </div>

          <div className="stat-card">
            <div className="stat-icon amber">
              <Activity size={20} />
            </div>

            <div>
              <span>Overall Risk Score</span>
              <strong>
                {analysis || simulation ? highestRisk : "—"}
                {(analysis || simulation) && <small>/100</small>}
              </strong>
            </div>
          </div>

          <div className="stat-card">
            <div className="stat-icon slate">
              <RefreshCw size={20} />
            </div>

            <div>
              <span>Latest Simulation</span>
              <strong className="stat-card-latest">
                {historyLoading
                  ? "Loading"
                  : latestSimulation
                    ? `#${latestSimulation.simulation_id}`
                    : "None"}
              </strong>
            </div>
          </div>
        </section>}

        {/* MAIN WORKSPACE */}

        {showWorkspace && <section className={`workspace-grid ${isOverview ? "overview-layout" : ""} ${activePage === "topology" ? "topology-layout" : ""} ${activePage === "topology" && !selectedAsset ? "topology-no-inspector" : ""}`}>
          {/* ENVIRONMENT GRAPH */}

          {(isOverview || activePage === "topology") && <div className="panel graph-panel">
            <div className="panel-heading">
              <div>
                <h3>System topology</h3>
                <p>
                  {isOverview
                    ? "Preview of assets and their access relationships"
                    : "Inspect assets, relationships, and potential access paths"}
                </p>
              </div>

              <div className="topology-heading-actions">
                {activePage === "topology" && (
                  <button
                    type="button"
                    className="add-asset-button"
                    onClick={openAddAsset}
                  >
                    <Boxes size={16} />
                    Add Asset
                  </button>
                )}
                {isOverview && (
                  <button
                    type="button"
                    className="text-button topology-view-button"
                    onClick={() => setActivePage("topology")}
                  >
                    View topology
                    <ArrowRight size={14} />
                  </button>
                )}
                <button
                  type="button"
                  className={`topology-lock-button${isTopologyLocked ? " locked" : " unlocked"}`}
                  aria-pressed={isTopologyLocked}
                  onClick={() => setIsTopologyLocked((locked) => !locked)}
                >
                  {isTopologyLocked ? (
                    <LockKeyhole size={15} />
                  ) : (
                    <Unlock size={15} />
                  )}
                  {isTopologyLocked ? "Locked" : "Unlocked"}
                </button>
                <span className="live-tag">LIVE DATA</span>
              </div>
            </div>

            <div className="graph-wrapper">
              {assets.length > 0 ? (
                <ReactFlow
                  nodes={graphNodes}
                  edges={graphEdges}
                  fitView
                  fitViewOptions={{ padding: 0.18 }}
                  nodesDraggable={!isTopologyLocked}
                  nodesConnectable={false}
                  elementsSelectable={!isTopologyLocked}
                  panOnDrag={!isTopologyLocked}
                  zoomOnScroll={!isTopologyLocked}
                  preventScrolling={!isTopologyLocked}
                  zoomOnPinch={!isTopologyLocked}
                  zoomOnDoubleClick={!isTopologyLocked}
                  onNodeClick={(_, node) => {
                    const assetId = Number(
                      node.id.replace("asset-", "")
                    );

                    setSelectedAssetId(assetId);
                  }}
                  onPaneClick={() => setSelectedAssetId(null)}
                  proOptions={{ hideAttribution: true }}
                >
                  <Background />
                  <Controls
                    showZoom={!isTopologyLocked}
                    showFitView={!isTopologyLocked}
                    showInteractive={false}
                  />

                  <MiniMap
                    pannable={!isTopologyLocked}
                    zoomable={!isTopologyLocked}
                    nodeColor={(node) => {
                      const asset = assets.find(
                        (item) => `asset-${item.id}` === node.id
                      );

                      return asset?.sensitivity === "critical"
                        ? "#dc7777"
                        : asset?.sensitivity === "high"
                          ? "#d69b65"
                          : "#8bbfb2";
                    }}
                  />
                </ReactFlow>
              ) : (
                <div className="empty-graph">
                  <Network size={38} />
                  <p>No assets available</p>
                  <span>Check your backend connection.</span>
                </div>
              )}
            </div>

            <div className="graph-legend">
              <div>
                <span className="legend-dot low" />
                Standard asset
              </div>

              <div>
                <span className="legend-dot critical" />
                Critical asset
              </div>

              <div>
                <span className="legend-line active" />
                Discovered path
              </div>

              <div>
                <span className="legend-line high-risk" />
                High-risk connection
              </div>

              <div>
                <span className="legend-line medium-risk" />
                Medium-risk connection
              </div>

              <div>
                <span className="legend-line restricted" />
                Restricted connection
              </div>
            </div>
          </div>}

          {/* RIGHT SIDEBAR */}

          {((activePage === "analysis" || activePage === "defense") ||
            (activePage === "topology" && selectedAsset)) && <aside className="right-panel">
            {/* SIMULATION CONTROLS */}

            {activePage !== "topology" && <div className="panel control-panel">
              <div className="panel-heading">
                <div>
                  <h3>
                    {activePage === "defense"
                      ? "Defense simulation"
                      : "Attack path analysis"}
                  </h3>
                  <p>
                    {activePage === "defense"
                      ? "Select relationships and simulate defensive changes"
                      : "Choose a scenario and review reachable attack paths"}
                  </p>
                </div>

                <ShieldCheck size={21} className="heading-icon" />
              </div>

              {renderScenarioSelect("scenario")}

              {activePage !== "defense" && (
                <button
                  className="primary-button"
                  onClick={runAnalysis}
                  disabled={loading || !scenarioId}
                >
                  <Network size={17} />
                  Analyze attack paths
                </button>
              )}

              {activePage !== "analysis" && <>
              <div className="section-divider" />

              {/* MULTIPLE DEFENSIVE CHANGES */}

              <div className="defense-selection-header">
                <div>
                  <h4>
                    {activePage === "defense"
                      ? "Choose relationships to restrict"
                      : "Defense Simulation"}
                  </h4>

                  <p className="control-description">
                    Select multiple access relationships to restrict together.
                  </p>
                </div>

                <span className="selection-count">
                  {selectedRelationshipIds.length} selected
                </span>
              </div>

              <div className="selection-actions">
                <button
                  type="button"
                  className="text-button"
                  onClick={selectAllRelationships}
                  disabled={relationships.length === 0}
                >
                  Select all
                </button>

                <button
                  type="button"
                  className="text-button"
                  onClick={clearRelationshipSelection}
                  disabled={selectedRelationshipIds.length === 0}
                >
                  Clear selection
                </button>
              </div>

              <div className="relationship-checkbox-list">
                {relationships.length > 0 ? (
                  relationships.map((relation) => (
                    <label
                      className="relationship-checkbox"
                      key={relation.id}
                    >
                      <input
                        type="checkbox"
                        checked={selectedRelationshipIds.includes(
                          relation.id
                        )}
                        onChange={() =>
                          toggleRelationshipSelection(relation.id)
                        }
                      />

                      <span className="relationship-checkbox-content">
                        <strong>
                          {getRelationshipLabel(relation)}
                        </strong>

                        <small>
                          {getRelationshipPermission(relation)}
                          {" · "}
                          ID {relation.id}
                        </small>
                      </span>
                    </label>
                  ))
                ) : (
                  <p className="inspector-empty">
                    No relationships available.
                  </p>
                )}
              </div>

              <button
                className="secondary-button"
                onClick={runSimulation}
                disabled={
                  loading ||
                  !scenarioId ||
                  selectedRelationshipIds.length === 0
                }
              >
                <LockKeyhole size={17} />
                Simulate selected defenses
              </button>
              </>}
            </div>}

            {/* ASSET INSPECTOR */}

            {activePage === "topology" && selectedAsset && (
              <div className="panel asset-inspector">
                <div className="panel-heading">
                  <div>
                    <h3>Asset Inspector</h3>
                    <p>
                      Selected asset and its access relationships
                    </p>
                  </div>

                  <button
                    className="inspector-close"
                    onClick={() => setSelectedAssetId(null)}
                    title="Close inspector"
                    aria-label="Close asset inspector"
                  >
                    <X size={17} />
                  </button>
                </div>

                <div className="inspected-asset">
                  <div
                    className={`stat-icon ${
                      selectedAsset.sensitivity === "critical"
                        ? "orange"
                        : "blue"
                    }`}
                  >
                    {getAssetIcon(
                      selectedAsset.asset_type || selectedAsset.type
                    )}
                  </div>

                  <div className="inspected-asset-info">
                    <strong>{selectedAsset.name}</strong>
                    <span>
                      {selectedAsset.asset_type || selectedAsset.type}
                    </span>
                  </div>

                  <span
                    className={`sensitivity-pill ${selectedAsset.sensitivity}`}
                  >
                    {selectedAsset.sensitivity}
                  </span>
                </div>

                <button
                  className="edit-asset-button"
                  onClick={() => openEditAsset(selectedAsset)}
                >
                  Edit Selected Asset
                </button>

                <div className="inspector-section">
                  <h4>
                    Incoming access ({incomingRelationships.length})
                  </h4>

                  {incomingRelationships.length > 0 ? (
                    incomingRelationships.map((relation) => (
                      <div
                        className="inspector-relationship"
                        key={relation.id}
                      >
                        <strong>
                          {getRelationshipLabel(relation)}
                        </strong>

                        <span>
                          Permission: {getRelationshipPermission(relation)}
                        </span>

                        <span>
                          Priority: {getRelationshipPriority(relation.id)}
                        </span>

                        <p>
                          {relation.description ||
                            "No description available."}
                        </p>
                      </div>
                    ))
                  ) : (
                    <p className="inspector-empty">
                      No incoming access relationships.
                    </p>
                  )}
                </div>

                <div className="inspector-section">
                  <h4>
                    Outgoing access ({outgoingRelationships.length})
                  </h4>

                  {outgoingRelationships.length > 0 ? (
                    outgoingRelationships.map((relation) => (
                      <div
                        className="inspector-relationship"
                        key={relation.id}
                      >
                        <strong>
                          {getRelationshipLabel(relation)}
                        </strong>

                        <span>
                          Permission: {getRelationshipPermission(relation)}
                        </span>

                        <span>
                          Priority: {getRelationshipPriority(relation.id)}
                        </span>

                        <p>
                          {relation.description ||
                            "No description available."}
                        </p>
                      </div>
                    ))
                  ) : (
                    <p className="inspector-empty">
                      No outgoing access relationships.
                    </p>
                  )}
                </div>
              </div>
            )}

            {/* ANALYSIS RESULTS */}

            {activePage !== "topology" && <div className="panel results-panel">
              <div className="panel-heading">
                <div>
                  <h3>
                    {activePage === "defense"
                      ? "Simulation results"
                      : "Attack path results"}
                  </h3>
                  <p>
                    {simulation
                      ? "Current paths and risk after selected defenses"
                      : "Reachable paths and their risk"}
                  </p>
                </div>

                <Activity size={19} className="heading-icon" />
              </div>

              {/* SIMULATION PATH COMPARISON */}

              {simulation && (
                <div className="simulation-summary">
                  <div>
                    <span>Paths before</span>
                    <strong>{simulation.before}</strong>
                  </div>

                  <ArrowRight size={17} />

                  <div>
                    <span>Paths after</span>
                    <strong>{simulation.after}</strong>
                  </div>

                  <div className="blocked-count">
                    <span>Blocked</span>
                    <strong>{simulation.blocked}</strong>
                  </div>
                </div>
              )}

              {/* AGGREGATE RISK COMPARISON */}

              {simulation && (
                <div className="risk-comparison">
                  <h4>Aggregate risk comparison</h4>

                  <div className="risk-comparison-row">
                    <span>Before</span>
                    <strong>
                      {simulation.before_risk_total ?? 0}
                    </strong>
                  </div>

                  <div className="risk-comparison-row">
                    <span>After</span>
                    <strong>
                      {simulation.after_risk_total ?? 0}
                    </strong>
                  </div>

                  <div className="risk-comparison-row">
                    <span>Risk reduction</span>
                    <strong>
                      {simulation.risk_reduction ?? 0}
                      {" "}
                      ({simulation.risk_reduction_percent ?? 0}%)
                    </strong>
                  </div>

                  <p>
                    Restricted relationships:{" "}
                    {(simulation.removed_relationship_ids || []).join(", ") ||
                      "None"}
                  </p>
                </div>
              )}

              {/* ATTACK PATH LIST */}

              {activePaths.length > 0 ? (
                <div className="path-list">
                  {activePaths.map((path, index) => (
                    <div className="path-item" key={index}>
                      <div className="path-item-header">
                        <span>PATH {index + 1}</span>

                        <span
                          className={
                            path.risk_score >= 80
                              ? "risk-high"
                              : "risk-medium"
                          }
                        >
                          {path.risk_score}/100
                        </span>
                      </div>

                      <div className="path-steps">
                        {path.labels.map((label, step) => (
                          <div className="path-step" key={step}>
                            <span>{label}</span>

                            {step < path.labels.length - 1 && (
                              <ArrowRight size={13} />
                            )}
                          </div>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="empty-results">
                  <GitBranch size={28} />

                  <strong>
                    {activePage === "defense"
                      ? "No simulation available"
                      : "No analysis available"}
                  </strong>

                  <span>
                    {activePage === "defense"
                      ? "Run a defensive simulation to compare before-and-after paths and risk."
                      : "Run attack-path analysis to see reachable resources and risk levels."}
                  </span>
                </div>
              )}

              {activePaths.length > 0 && (
                <div className="highest-risk">
                  <span>Highest remaining path risk</span>
                  <strong>{highestRisk}/100</strong>
                </div>
              )}
            </div>}
          </aside>}
        </section>}

        {isOverview && (
          <>
            <section className="panel overview-summary-panel">
              <div className="panel-heading">
                <div>
                  <h3>Attack Path Summary</h3>
                  <p>Current reachable paths and their highest observed risk.</p>
                </div>
                <button
                  type="button"
                  className="text-button summary-link"
                  onClick={() => setActivePage("analysis")}
                >
                  Open analysis
                  <ArrowRight size={14} />
                </button>
              </div>

              {analysis || simulation ? (
                <>
                  <div className="overview-metrics">
                    <div>
                      <span>Reachable paths</span>
                      <strong>{currentPathCount}</strong>
                    </div>
                    <div>
                      <span>Highest path risk</span>
                      <strong>{activePaths.length ? `${highestRisk}/100` : "—"}</strong>
                    </div>
                  </div>
                  {activePaths.length > 0 ? (
                    <div className="summary-path-list">
                      {activePaths.slice(0, 3).map((path, index) => (
                        <div className="summary-path-row" key={index}>
                          <span>
                            Path {index + 1}: {path.labels.join(" → ")}
                          </span>
                          <strong>{path.risk_score}/100</strong>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="overview-empty">
                      No reachable attack paths are reported for this result.
                    </p>
                  )}
                </>
              ) : (
                <p className="overview-empty">
                  Run attack path analysis to see reachable paths and risk.
                </p>
              )}
            </section>

            <section className="panel overview-summary-panel">
              <div className="panel-heading">
                <div>
                  <h3>Defense Simulation Summary</h3>
                  <p>Latest available before-and-after simulation results.</p>
                </div>
                <button
                  type="button"
                  className="text-button summary-link"
                  onClick={() => setActivePage("defense")}
                >
                  Open defense simulation
                  <ArrowRight size={14} />
                </button>
              </div>

              {defenseSummary ? (
                <div className="overview-metrics defense-summary-metrics">
                  <div>
                    <span>Paths before</span>
                    <strong>{defenseSummary.before}</strong>
                  </div>
                  <div>
                    <span>Paths after</span>
                    <strong>{defenseSummary.after}</strong>
                  </div>
                  <div>
                    <span>Paths blocked</span>
                    <strong>{defenseSummary.blocked}</strong>
                  </div>
                  <div>
                    <span>Risk reduction</span>
                    <strong>
                      {defenseSummary.risk_reduction_percent == null
                        ? "Not recorded"
                        : `${defenseSummary.risk_reduction_percent}%`}
                    </strong>
                  </div>
                </div>
              ) : (
                <p className="overview-empty">
                  No simulation results are available for this scenario yet.
                </p>
              )}
            </section>

            <section className="panel recent-activity-panel">
              <div className="panel-heading">
                <div>
                  <h3>Recent Activity</h3>
                  <p>Latest saved simulations for the selected scenario.</p>
                </div>
                <button
                  type="button"
                  className="text-button summary-link"
                  onClick={() => setActivePage("history")}
                >
                  View history
                  <ArrowRight size={14} />
                </button>
              </div>

              {simulationHistory.length > 0 ? (
                <div className="recent-activity-list">
                  {simulationHistory.slice(0, 3).map((item) => (
                    <div className="recent-activity-item" key={item.simulation_id}>
                      <div>
                        <strong>Simulation #{item.simulation_id}</strong>
                        <span>
                          {item.created_at
                            ? new Date(item.created_at).toLocaleString()
                            : "Date unavailable"}
                        </span>
                      </div>
                      <p>
                        {item.before} paths before <ArrowRight size={13} />{" "}
                        {item.after} after · {item.blocked} blocked
                      </p>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="overview-empty">
                  No saved simulations are available for this scenario.
                </p>
              )}
            </section>

            <section className="panel quick-actions-panel">
              <div className="panel-heading">
                <div>
                  <h3>Quick Actions</h3>
                  <p>Continue to a workflow.</p>
                </div>
              </div>
              <div className="overview-quick-actions">
                <button type="button" onClick={() => setActivePage("analysis")}>
                  <Network size={18} />
                  <span>
                    <strong>Run analysis</strong>
                    <small>Review attack paths</small>
                  </span>
                  <ArrowRight size={15} />
                </button>
                <button type="button" onClick={() => setActivePage("defense")}>
                  <ShieldCheck size={18} />
                  <span>
                    <strong>Simulate defenses</strong>
                    <small>Model relationship restrictions</small>
                  </span>
                  <ArrowRight size={15} />
                </button>
                <button type="button" onClick={() => setActivePage("reports")}>
                  <FileDown size={18} />
                  <span>
                    <strong>Generate report</strong>
                    <small>Download the scenario PDF</small>
                  </span>
                  <ArrowRight size={15} />
                </button>
              </div>
            </section>
          </>
        )}

        {/* CRITICAL WEAKNESS ASSESSMENT */}

        {activePage === "weakness" && <section className="panel weakness-panel">
          <div className="weakness-heading">
            <div>
              <p className="eyebrow">SECURITY INTELLIGENCE</p>

              <h3>Critical Weakness Assessment</h3>

              <p className="subtitle">
                Rank access relationships by their impact on attack paths.
              </p>
            </div>

            <div className="weakness-actions">
              {renderScenarioSelect("weakness-scenario")}
              <button
                className="assessment-button"
                onClick={runWeaknessAssessment}
                disabled={weaknessLoading || !scenarioId}
              >
                <ShieldCheck size={17} />
                {weaknessLoading ? "Analyzing..." : "Run Assessment"}
              </button>

            </div>
          </div>

          {weaknessReport && (
            <>
              <div className="weakness-summary">
                <div>
                  <span>Relationships Reviewed</span>
                  <strong>
                    {weaknessReport.total_relationships_reviewed}
                  </strong>
                </div>

                <div>
                  <span>Baseline Attack Paths</span>
                  <strong>{weaknessReport.baseline_paths}</strong>
                </div>

                <div>
                  <span>Aggregate Baseline Risk</span>
                  <strong>{weaknessReport.baseline_risk}</strong>
                </div>
              </div>

              <div className="weakness-table-wrapper">
                <table className="weakness-table">
                  <thead>
                    <tr>
                      <th>Relationship</th>
                      <th>Paths Blocked</th>
                      <th>Risk Reduction</th>
                      <th>Priority Score</th>
                      <th>Priority</th>
                    </tr>
                  </thead>

                  <tbody>
                    {weaknessReport.findings.map((finding) => (
                      <tr key={finding.relationship_id}>
                        <td>
                          <strong>{finding.source}</strong>

                          <span className="relationship-arrow">
                            → {finding.target}
                          </span>
                        </td>

                        <td>{finding.blocked_paths}</td>

                        <td>
                          {finding.risk_reduction}

                          <span className="reduction-percent">
                            ({finding.risk_reduction_percent}%)
                          </span>
                        </td>

                        <td>
                          <strong>
                            {finding.priority_score}/100
                          </strong>
                        </td>

                        <td>
                          <span
                            className={`priority-badge ${finding.priority.toLowerCase()}`}
                          >
                            {finding.priority}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <p className="assessment-disclaimer">
                Priority scores represent simulated relationship impact.
                They are not CVSS vulnerability scores.
              </p>
            </>
          )}

          {!weaknessReport && !weaknessLoading && (
            <div className="weakness-empty">
              <AlertTriangle size={25} />

              <strong>No assessment generated yet</strong>

              <span>
                Run the assessment to identify and prioritize high-impact
                access relationships.
              </span>
            </div>
          )}

          {weaknessLoading && (
            <div className="loading-text">
              Analyzing access relationships...
            </div>
          )}
        </section>}

      {/* SIMULATION HISTORY */}

        {activePage === "history" && <section className="panel simulation-history-panel">
          <div className="panel-heading">
            <div>
              <h3>Simulation history</h3>
              <p>Previously saved defensive configurations</p>
            </div>

            <div className="history-heading-actions">
              {renderScenarioSelect("history-scenario")}
              <button
                className="refresh-button"
                onClick={loadSimulationHistory}
                disabled={historyLoading || !scenarioId}
              >
                <RefreshCw size={15} />
                Refresh
              </button>
            </div>
          </div>

          {historyLoading ? (
            <div className="loading-text">
              Loading simulation history...
            </div>
          ) : simulationHistory.length > 0 ? (
            <div className="simulation-history-list">
              {simulationHistory.map((item) => {
                // Older records do not contain saved relationship IDs
                // or risk totals. Do not present missing data as zero risk.
                const hasSavedDetails =
                  Array.isArray(item.removed_relationship_ids) &&
                  item.removed_relationship_ids.length > 0;

                return (
                  <div
                    className="simulation-history-item"
                    key={item.simulation_id}
                  >
                    <div className="history-item-top">
                      <strong>
                        Simulation #{item.simulation_id}
                      </strong>

                      <span>
                        {item.created_at
                          ? new Date(item.created_at).toLocaleString()
                          : "Date unavailable"}
                      </span>
                    </div>

                    <div className="history-item-stats">
                      <div>
                        <small>Before</small>
                        <strong>{item.before}</strong>
                      </div>

                      <div>
                        <small>After</small>
                        <strong>{item.after}</strong>
                      </div>

                      <div>
                        <small>Blocked</small>
                        <strong>{item.blocked}</strong>
                      </div>

                      <div>
                        <small>Risk reduction</small>
                        <strong>
                          {hasSavedDetails
                            ? `${item.risk_reduction_percent ?? 0}%`
                            : "Not recorded"}
                        </strong>
                      </div>
                    </div>

                    <div className="history-item-bottom">
                      <span>
                        Restricted IDs:{" "}
                        {hasSavedDetails
                          ? item.removed_relationship_ids.join(", ")
                          : "Not recorded"}
                      </span>

                      {!hasSavedDetails && (
                        <span className="legacy-history-tag">
                          Legacy record
                        </span>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          ) : (
            <div className="weakness-empty">
              <GitBranch size={25} />

              <strong>No simulations saved yet</strong>

              <span>
                Run a defensive simulation to create your first history
                record.
              </span>
            </div>
          )}
        </section>}

        {activePage === "reports" && (
          <section className="panel reports-panel">
            <div className="panel-heading">
              <div>
                <h3>Reports</h3>
                <p>Download a security report for the selected scenario.</p>
              </div>
              {renderScenarioSelect("report-scenario")}
            </div>
            <div className="report-card-content">
              <div>
                <strong>Security assessment report</strong>
                <span>
                  {scenarioId
                    ? `Scenario ${scenarioId}`
                    : "Select a scenario to generate a report"}
                </span>
              </div>
              <button
                className="download-button"
                onClick={downloadSecurityReport}
                disabled={reportLoading || !scenarioId}
              >
                <FileDown size={17} />
                {reportLoading ? "Generating..." : "Download PDF"}
              </button>
            </div>
          </section>
        )}

        {activePage === "settings" && (
          <section className="panel settings-panel">
            <div className="panel-heading">
              <div>
                <h3>Appearance</h3>
                <p>Choose a visual theme for this browser.</p>
              </div>
            </div>
            <fieldset className="theme-options">
              <legend>Color theme</legend>
              {[
                { id: "light", label: "Light", detail: "Bright workspace" },
                { id: "dark", label: "Dark", detail: "Low-light workspace" },
                { id: "hybrid", label: "Hybrid", detail: "Dark navigation, light workspace" },
              ].map((option) => (
                <label className="theme-option" key={option.id}>
                  <input
                    type="radio"
                    name="theme"
                    value={option.id}
                    checked={theme === option.id}
                    onChange={() => setTheme(option.id)}
                  />
                  <span className={`theme-swatch ${option.id}`} />
                  <span className="theme-option-copy">
                    <strong>{option.label}</strong>
                    <small>{option.detail}</small>
                  </span>
                </label>
              ))}
            </fieldset>
          </section>
        )}


        {/* ADD / EDIT ASSET MODAL */}

        {assetModalOpen && (
          <div className="modal-overlay">
            <div
              className="asset-modal"
              role="dialog"
              aria-modal="true"
              aria-labelledby="asset-modal-title"
            >
              <div className="modal-header">
                <div>
                  <p className="eyebrow">ASSET MANAGEMENT</p>

                  <h3 id="asset-modal-title">
                    {editingAssetId !== null
                      ? "Edit Asset"
                      : "Add New Asset"}
                  </h3>
                </div>

                <button
                  type="button"
                  className="inspector-close"
                  onClick={closeAssetModal}
                  disabled={assetSaving}
                  title="Close form"
                  aria-label="Close asset form"
                >
                  <X size={18} />
                </button>
              </div>

              <form onSubmit={saveAsset}>
                {assetFormError && (
                  <div className="asset-form-error" role="alert">
                    <AlertTriangle size={16} />
                    <span>{assetFormError}</span>
                  </div>
                )}

                <label htmlFor="asset-name">Asset Name</label>

                <input
                  id="asset-name"
                  type="text"
                  name="name"
                  placeholder="e.g. Internal Web Server"
                  value={assetForm.name}
                  onChange={(event) => {
                    setAssetForm({
                      ...assetForm,
                      name: event.target.value,
                    });

                    setAssetFormError("");
                  }}
                  maxLength={150}
                  required
                />

                <label htmlFor="asset-type">Asset Type</label>

                <select
                  id="asset-type"
                  value={assetForm.asset_type}
                  onChange={(event) =>
                    setAssetForm({
                      ...assetForm,
                      asset_type: event.target.value,
                    })
                  }
                >
                  <option value="account">User Account</option>
                  <option value="application">Application</option>
                  <option value="server">Server</option>
                  <option value="database">Database</option>
                  <option value="device">Device</option>
                  <option value="cloud">Cloud Resource</option>
                  <option value="service">Service</option>
                  <option value="workstation">Workstation</option>
                </select>

                <label htmlFor="asset-description">Description</label>

                <textarea
                  id="asset-description"
                  placeholder="Describe the purpose of this asset..."
                  value={assetForm.description}
                  onChange={(event) =>
                    setAssetForm({
                      ...assetForm,
                      description: event.target.value,
                    })
                  }
                  maxLength={1000}
                  rows={3}
                />

                <label htmlFor="asset-sensitivity">
                  Sensitivity Level
                </label>

                <select
                  id="asset-sensitivity"
                  value={assetForm.sensitivity}
                  onChange={(event) =>
                    setAssetForm({
                      ...assetForm,
                      sensitivity: event.target.value,
                    })
                  }
                >
                  <option value="low">Low</option>
                  <option value="medium">Medium</option>
                  <option value="high">High</option>
                  <option value="critical">Critical</option>
                </select>

                <div className="modal-actions">
                  <button
                    type="button"
                    className="cancel-button"
                    onClick={closeAssetModal}
                    disabled={assetSaving}
                  >
                    Cancel
                  </button>

                  <button
                    type="submit"
                    className="save-asset-button"
                    disabled={assetSaving}
                  >
                    {assetSaving
                      ? "Saving..."
                      : editingAssetId !== null
                        ? "Save Changes"
                        : "Create Asset"}
                  </button>
                </div>
              </form>
            </div>
          </div>
        )}

        {/* FOOTER */}

        <footer className="footer">
          <span>VulnWeave 1.0.0</span>

          <span>
            Synthetic environment · Controlled security simulation
          </span>
        </footer>
              </main>
    </div>
  </div>
</div>
  );
}

export default App;