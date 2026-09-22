// Causal Discovery Service - Test UI frontend logic.
//
// Talks only to the separate test_ui API (api/main.py), never to the
// existing backend. If you change the API port in run_test_ui.sh, update
// API_BASE below to match.
const API_BASE = window.CAUSAL_TEST_API_BASE || "http://127.0.0.1:8790";

const runBtn = document.getElementById("runBtn");
const statusLine = document.getElementById("statusLine");
const runTilesEl = document.getElementById("runTiles");
const panelTilesEl = document.getElementById("panelTiles");
const entityChipsEl = document.getElementById("entityChips");
const edgesTableWrap = document.getElementById("edgesTableWrap");
const graphSummaryEl = document.getElementById("graphSummary");
const isolatedNodesEl = document.getElementById("isolatedNodes");
const minStrengthInput = document.getElementById("minStrength");
const showSelfLoopsInput = document.getElementById("showSelfLoops");

let cy = null;
let pollHandle = null;
let lastGraph = null; // the raw graph from the most recently completed run

function tile(label, value, sub) {
  const subHtml = sub ? `<div class="sub">${sub}</div>` : "";
  return `<div class="tile"><div class="label">${label}</div><div class="value">${value}</div>${subHtml}</div>`;
}

function setStatus(status, message) {
  statusLine.innerHTML = `<span class="status-pill ${status}">${status}</span> ${message}`;
}

async function startRun() {
  const domain = document.getElementById("domain").value;
  const maxEntities = parseInt(document.getElementById("maxEntities").value, 10) || 3;
  const tauMaxRaw = document.getElementById("tauMax").value;
  const pcAlphaRaw = document.getElementById("pcAlpha").value;

  const body = { max_entities: maxEntities };
  if (tauMaxRaw !== "") body.tau_max = parseInt(tauMaxRaw, 10);
  if (pcAlphaRaw !== "") body.pc_alpha = parseFloat(pcAlphaRaw);

  runBtn.disabled = true;
  setStatus("PENDING", "Starting run...");

  try {
    const response = await fetch(`${API_BASE}/api/${domain}/run`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });

    if (!response.ok) {
      const text = await response.text();
      throw new Error(`API returned ${response.status}: ${text}`);
    }

    const data = await response.json();
    pollRun(data.run_id);
  } catch (error) {
    setStatus("FAILED", `Could not start run: ${error.message}. Is the API running on ${API_BASE}?`);
    runBtn.disabled = false;
  }
}

function pollRun(runId) {
  if (pollHandle) clearInterval(pollHandle);

  pollHandle = setInterval(async () => {
    try {
      const response = await fetch(`${API_BASE}/api/runs/${runId}`);
      if (!response.ok) throw new Error(`status ${response.status}`);
      const job = await response.json();

      if (job.status === "PENDING" || job.status === "RUNNING") {
        const elapsedSec = Math.round((Date.now() - new Date(job.started_at).getTime()) / 1000);
        setStatus(job.status, `Run ${job.run_id.slice(0, 8)} - elapsed ${elapsedSec}s. LPCMCI is slow; this can take a while.`);
        return;
      }

      clearInterval(pollHandle);
      runBtn.disabled = false;

      if (job.status === "COMPLETED") {
        setStatus("COMPLETED", `Run ${job.run_id.slice(0, 8)} finished.`);
        renderRun(job);
      } else {
        setStatus("FAILED", `Run ${job.run_id.slice(0, 8)} failed: ${job.error || "unknown error"}`);
      }
    } catch (error) {
      clearInterval(pollHandle);
      runBtn.disabled = false;
      setStatus("FAILED", `Lost contact with API: ${error.message}`);
    }
  }, 2000);
}

function renderRun(job) {
  const summary = job.summary || {};
  const graph = job.graph || { nodes: [], edges: [] };
  lastGraph = graph;

  runTilesEl.innerHTML =
    tile("Run ID", job.run_id.slice(0, 12)) +
    tile("Domain", job.domain) +
    tile("tau_min / tau_max", `${job.config_used.tau_min} / ${job.config_used.tau_max}`) +
    tile("pc_alpha", job.config_used.pc_alpha) +
    tile("Window", `${summary.window_start ? summary.window_start.slice(0, 16) : "?"} &rarr; ${summary.window_end ? summary.window_end.slice(0, 16) : "?"}`) +
    tile("Edges found", graph.edges.length);

  panelTilesEl.innerHTML =
    tile("Entities considered", summary.entities_considered ?? "-") +
    tile("Entities selected", (summary.entities_selected || []).length) +
    tile("Raw rows fetched", summary.raw_row_count ?? "-") +
    tile("Panel shape (T, N)", (summary.panel_shape || []).join(" x ")) +
    tile("Dropped (near-constant)", (summary.columns_dropped_near_constant || []).length) +
    tile("Missing data %", summary.missing_data_pct_after_interpolation ?? "-");

  entityChipsEl.innerHTML = (summary.entities_selected || [])
    .map((id) => `<span class="chip">${id}</span>`)
    .join("");

  renderGraph(graph);
  renderEdgesTable(graph);
}

// ---------------------------------------------------------------------
// Graph cleanup helpers
//
// The raw edge list from LPCMCI mixes three different kinds of edges that
// read very differently on a canvas:
//   - self-loops (source === target): a variable correlating with its own
//     past value. Real information, but not a relationship BETWEEN two
//     different things, so it doesn't need a loop arc cluttering the view.
//   - mirrored pairs (A->B and B->A at the same lag): the same underlying
//     relationship reported from both variables' point of view. Drawing
//     both as separate arrows looks like "two edges" for one relationship.
//   - genuine cross-variable edges: what the graph is actually for.
//
// This groups the raw edges into those three buckets so the canvas only
// draws the third kind, while the first two are summarized instead of
// silently dropped.
// ---------------------------------------------------------------------

function splitEdges(edges) {
  const selfLoopByNode = new Map(); // node -> strongest self-loop edge
  const crossByKey = new Map(); // canonical pair+lag -> strongest edge

  for (const edge of edges) {
    if (edge.source === edge.target) {
      const existing = selfLoopByNode.get(edge.source);
      if (!existing || Math.abs(edge.strength) > Math.abs(existing.strength)) {
        selfLoopByNode.set(edge.source, edge);
      }
      continue;
    }

    const pairKey = [edge.source, edge.target].sort().join("~~") + `@lag${edge.lag}`;
    const existing = crossByKey.get(pairKey);
    if (!existing || Math.abs(edge.strength) > Math.abs(existing.strength)) {
      crossByKey.set(pairKey, edge);
    }
  }

  return {
    selfLoopByNode,
    crossEdges: Array.from(crossByKey.values()),
    mirroredMergedCount: edges.filter((e) => e.source !== e.target).length - crossByKey.size,
  };
}

function renderGraph(graph) {
  const minStrength = parseFloat(minStrengthInput.value) || 0;
  const showSelfLoops = showSelfLoopsInput.checked;

  const { selfLoopByNode, crossEdges, mirroredMergedCount } = splitEdges(graph.edges);

  const visibleCrossEdges = crossEdges.filter((e) => Math.abs(e.strength) >= minStrength);

  const connectedNodeIds = new Set();
  visibleCrossEdges.forEach((e) => {
    connectedNodeIds.add(e.source);
    connectedNodeIds.add(e.target);
  });

  const isolatedNodes = graph.nodes.filter((n) => !connectedNodeIds.has(n.var_name));
  const canvasNodes = graph.nodes.filter((n) => connectedNodeIds.has(n.var_name));

  // --- Summary line: what got cleaned up and why ---
  const hiddenBelowThreshold = crossEdges.length - visibleCrossEdges.length;
  graphSummaryEl.innerHTML =
    `Showing <b>${visibleCrossEdges.length}</b> of ${crossEdges.length} cross-variable relationships` +
    (mirroredMergedCount > 0 ? ` (${mirroredMergedCount} mirrored duplicate${mirroredMergedCount === 1 ? "" : "s"} merged)` : "") +
    (hiddenBelowThreshold > 0 ? ` &middot; ${hiddenBelowThreshold} hidden below the strength filter` : "") +
    (selfLoopByNode.size > 0 && !showSelfLoops
      ? ` &middot; ${selfLoopByNode.size} self-loop${selfLoopByNode.size === 1 ? "" : "s"} summarized on node labels instead of drawn as loops`
      : "") +
    (isolatedNodes.length > 0 ? ` &middot; ${isolatedNodes.length} variable${isolatedNodes.length === 1 ? "" : "s"} with no cross-variable link listed below` : "");

  // --- Isolated-node chip list (kept off the canvas so it doesn't sprawl) ---
  isolatedNodesEl.innerHTML = isolatedNodes
    .map((n) => {
      const selfEdge = selfLoopByNode.get(n.var_name);
      const selfNote = selfEdge ? ` (self r=${selfEdge.strength.toFixed(2)}, lag ${selfEdge.lag})` : " (no relationships found)";
      return `<span class="chip">${n.entity_id}||${n.metric}${selfNote}</span>`;
    })
    .join("");

  const elements = [
    ...canvasNodes.map((node) => {
      const selfEdge = selfLoopByNode.get(node.var_name);
      const label =
        selfEdge && showSelfLoops
          ? `${node.entity_id}\n${node.metric}`
          : selfEdge
          ? `${node.entity_id}\n${node.metric}\n(self r=${selfEdge.strength.toFixed(2)})`
          : `${node.entity_id}\n${node.metric}`;
      return { data: { id: node.var_name, label } };
    }),
    ...visibleCrossEdges.map((edge, index) => ({
      data: {
        id: `cross-${index}`,
        source: edge.source,
        target: edge.target,
        label: `${edge.edge_mark} lag=${edge.lag}`,
        sign: edge.strength >= 0 ? "pos" : "neg",
        width: 1 + Math.min(Math.abs(edge.strength), 1) * 5,
      },
    })),
    ...(showSelfLoops
      ? canvasNodes
          .filter((n) => selfLoopByNode.has(n.var_name))
          .map((n, index) => {
            const edge = selfLoopByNode.get(n.var_name);
            return {
              data: {
                id: `self-${index}`,
                source: n.var_name,
                target: n.var_name,
                label: `self lag=${edge.lag}`,
                sign: edge.strength >= 0 ? "pos" : "neg",
                width: 1,
              },
              classes: "self-loop",
            };
          })
      : []),
  ];

  if (cy) cy.destroy();

  cy = cytoscape({
    container: document.getElementById("cy"),
    elements,
    style: [
      {
        selector: "node",
        style: {
          "background-color": "#1c2733",
          "border-color": "#4da3ff",
          "border-width": 1.5,
          label: "data(label)",
          color: "#e8ebf1",
          "font-size": 9,
          "text-wrap": "wrap",
          "text-valign": "center",
          "text-halign": "center",
          shape: "round-rectangle",
          width: 100,
          height: 46,
        },
      },
      {
        selector: "edge",
        style: {
          width: "data(width)",
          opacity: 0.85,
          "line-color": "#ff6b57",
          "target-arrow-color": "#ff6b57",
          "target-arrow-shape": "triangle",
          "curve-style": "bezier",
          label: "data(label)",
          "font-size": 8,
          color: "#8b93a5",
        },
      },
      {
        selector: "edge[sign = 'neg']",
        style: { "line-color": "#4da3ff", "target-arrow-color": "#4da3ff" },
      },
      {
        selector: "edge.self-loop",
        style: {
          "curve-style": "bezier",
          "loop-direction": "0deg",
          "loop-sweep": "45deg",
          opacity: 0.5,
        },
      },
    ],
    layout: {
      name: "cose",
      animate: false,
      padding: 40,
      nodeRepulsion: 12000,
      idealEdgeLength: 140,
      avoidOverlap: true,
    },
  });
}

function renderEdgesTable(graph) {
  if (!graph.edges.length) {
    edgesTableWrap.innerHTML = '<p class="empty-note">No edges were kept by LPCMCI for this run (try a lower pc_alpha, or more data).</p>';
    return;
  }

  const rows = [...graph.edges]
    .sort((a, b) => Math.abs(b.strength) - Math.abs(a.strength))
    .map((edge) => {
      const signClass = edge.strength >= 0 ? "sign-pos" : "sign-neg";
      const signLabel = edge.strength >= 0 ? "+" : "-";
      const selfTag = edge.source === edge.target ? '<span class="chip" style="margin-left:6px;">self-loop</span>' : "";
      return `<tr>
        <td>${edge.source}</td>
        <td>${edge.target}${selfTag}</td>
        <td>${edge.lag}</td>
        <td class="${signClass}">${signLabel}</td>
        <td>${edge.strength.toFixed(3)}</td>
        <td>${edge.p_value.toExponential(2)}</td>
        <td>${edge.edge_mark}</td>
      </tr>`;
    })
    .join("");

  edgesTableWrap.innerHTML = `
    <table>
      <thead>
        <tr><th>Source</th><th>Target</th><th>Lag</th><th>Sign</th><th>Strength</th><th>p-value</th><th>Edge mark</th></tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>`;
}

function reRenderGraphOnly() {
  if (lastGraph) renderGraph(lastGraph);
}

runBtn.addEventListener("click", startRun);
minStrengthInput.addEventListener("input", reRenderGraphOnly);
showSelfLoopsInput.addEventListener("change", reRenderGraphOnly);
