const API_BASE = window.PEWS_API_BASE || "http://127.0.0.1:8792";

const params = new URLSearchParams(window.location.search);
const warningId = params.get("warning_id");

const predictionTilesEl = document.getElementById("predictionTiles");
const eligibilityTilesEl = document.getElementById("eligibilityTiles");
const eligibilityNotesEl = document.getElementById("eligibilityNotes");
const investigateBtn = document.getElementById("investigateBtn");
const investigateStatusEl = document.getElementById("investigateStatus");
const resultSectionEl = document.getElementById("resultSection");
const investigationTilesEl = document.getElementById("investigationTiles");
const classificationsBodyEl = document.getElementById("classificationsBody");

const explanationSectionEl = document.getElementById("explanationSection");
const explanationLoadingNoteEl = document.getElementById("explanationLoadingNote");
const explanationContentEl = document.getElementById("explanationContent");
const explainWhatsHappeningEl = document.getElementById("explainWhatsHappening");
const explainChainNarrativeEl = document.getElementById("explainChainNarrative");
const explainChainNodesEl = document.getElementById("explainChainNodes");
const explainRootCauseEl = document.getElementById("explainRootCause");
const explainWhatCouldGoWrongEl = document.getElementById("explainWhatCouldGoWrong");
const explainNextStepsEl = document.getElementById("explainNextSteps");
const explainNextStepsNoteEl = document.getElementById("explainNextStepsNote");

const copilotSectionEl = document.getElementById("copilotSection");
const copilotMessagesEl = document.getElementById("copilotMessages");
const copilotDisabledNoteEl = document.getElementById("copilotDisabledNote");
const copilotFormEl = document.getElementById("copilotForm");
const copilotInputEl = document.getElementById("copilotInput");
const copilotSendBtnEl = document.getElementById("copilotSendBtn");
const copilotClearBtnEl = document.getElementById("copilotClearBtn");
const copilotSuggestionsEl = document.getElementById("copilotSuggestions");

let cy = null;
let pollHandle = null;
let currentWarning = null;

const ROLE_COLORS = {
  TARGET: "#ff6b57",
  ROOT_CANDIDATE: "#f2c94c",
  UPSTREAM: "#b57bff",
  DOWNSTREAM: "#4da3ff",
  UNCERTAIN_LINK: "#5a6272",
};

function tile(label, value) {
  return `<div class="tile"><div class="label">${label}</div><div class="value">${value}</div></div>`;
}

async function loadWarning() {
  if (!warningId) {
    predictionTilesEl.innerHTML = '<p class="empty-note">No warning_id in the URL.</p>';
    return;
  }

  const response = await fetch(`${API_BASE}/api/warnings/${warningId}`);
  if (!response.ok) {
    predictionTilesEl.innerHTML = `<p class="empty-note">Could not load warning ${warningId}.</p>`;
    return;
  }

  currentWarning = await response.json();
  const pct = Math.round(currentWarning.prediction_probability * 100);

  predictionTilesEl.innerHTML =
    tile("Warning Type", currentWarning.warning_type.replaceAll("_", " ")) +
    tile("Vehicle", currentWarning.vehicle_id) +
    tile("Target Metric", currentWarning.target_metric) +
    tile("Risk", `${pct}%`) +
    tile("Likely Within", `${currentWarning.forecast_gap_hours ?? 0}h - ${currentWarning.forecast_horizon_hours}h`) +
    tile("Severity", currentWarning.severity) +
    tile("Status", currentWarning.status);

  // Eligibility and fleet-impact rank are both already known at detection
  // time (see scheduler.py) - neither needs LPCMCI, so this doesn't wait
  // on the investigation below.
  renderEligibilityAndImpact(currentWarning);

  // If this warning was already investigated before (possibly in an earlier
  // session, or before an API restart), load that result from durable
  // storage instead of making the user re-run LPCMCI - and this is also
  // what unlocks the Copilot panel.
  await loadExistingInvestigation();
}

function formatInr(value) {
  return `Rs. ${Math.round(value).toLocaleString("en-IN")}`;
}

async function renderEligibilityAndImpact(warning) {
  const eligible = warning.is_warranty_eligible;
  const eligibilityBadgeClass = eligible === true ? "eligible" : eligible === false ? "not-eligible" : "unknown";
  const eligibilityLabel = eligible === true ? "Yes" : eligible === false ? "No" : "Unknown";

  let impactTile = tile("Fleet Impact Rank", "Not yet ranked");
  let affectedTile = tile("Vehicles Affected (fleet-wide)", "&mdash;");
  let totalTile = tile("Total Expected Liability (fleet-wide)", "&mdash;");

  try {
    const response = await fetch(`${API_BASE}/api/warnings/impact-ranking?limit=100`);
    if (response.ok) {
      const data = await response.json();
      const rank = data.ranked_issues.findIndex((issue) => issue.issue_category === warning.warning_type);
      if (rank !== -1) {
        const issue = data.ranked_issues[rank];
        const escalatedNote = issue.escalated ? ` <span class="impact-badge">ESCALATED</span>` : "";
        impactTile = tile("Fleet Impact Rank", `#${rank + 1}${escalatedNote}`);
        affectedTile = tile("Vehicles Affected (fleet-wide)", issue.affected_vehicle_count);
        totalTile = tile("Total Expected Liability (fleet-wide)", formatInr(issue.total_expected_liability_inr));
      } else {
        impactTile = tile("Fleet Impact Rank", "Not currently ranked (no eligible open warnings of this type)");
      }
    }
  } catch (error) {
    impactTile = tile("Fleet Impact Rank", "Could not load");
  }

  eligibilityTilesEl.innerHTML =
    tile("Warranty Eligible", `<span class="eligibility-badge ${eligibilityBadgeClass}">${eligibilityLabel}</span>`) +
    impactTile +
    affectedTile +
    totalTile;

  eligibilityNotesEl.textContent = warning.eligibility_notes || "No eligibility notes recorded for this warning.";
}

async function loadExistingInvestigation() {
  try {
    const response = await fetch(`${API_BASE}/api/warnings/${warningId}/investigation`);
    if (!response.ok) return;
    const data = await response.json();
    if (data.result) {
      investigateStatusEl.textContent = "Loaded a previous investigation for this warning.";
      renderResult(data.result);
      loadExplanationOnce();
    } else {
      setCopilotEnabled(false);
    }
  } catch (error) {
    setCopilotEnabled(false);
  }
}

async function startInvestigation() {
  investigateBtn.disabled = true;
  investigateStatusEl.textContent = "Starting investigation...";

  try {
    const response = await fetch(`${API_BASE}/api/warnings/${warningId}/investigate`, {
      method: "POST",
    });
    if (!response.ok) throw new Error(`status ${response.status}`);
    const data = await response.json();
    pollJob(data.job_id);
  } catch (error) {
    investigateStatusEl.textContent = `Could not start investigation: ${error.message}`;
    investigateBtn.disabled = false;
  }
}

function pollJob(jobId) {
  if (pollHandle) clearInterval(pollHandle);

  pollHandle = setInterval(async () => {
    try {
      const response = await fetch(`${API_BASE}/api/investigations/${jobId}`);
      if (!response.ok) throw new Error(`status ${response.status}`);
      const job = await response.json();

      if (job.status === "PENDING" || job.status === "RUNNING") {
        const elapsed = Math.round((Date.now() - new Date(job.started_at).getTime()) / 1000);
        investigateStatusEl.textContent = `${job.status} - elapsed ${elapsed}s. LPCMCI is slow; this can take a while.`;
        return;
      }

      clearInterval(pollHandle);
      investigateBtn.disabled = false;

      if (job.status === "COMPLETED") {
        investigateStatusEl.textContent = "Investigation complete.";
        renderResult(job.result);
        pollExplanationUntilReady();
      } else {
        investigateStatusEl.textContent = `Investigation failed: ${job.error || "unknown error"}`;
      }
    } catch (error) {
      clearInterval(pollHandle);
      investigateBtn.disabled = false;
      investigateStatusEl.textContent = `Lost contact with API: ${error.message}`;
    }
  }, 3000);
}

function renderResult(result) {
  resultSectionEl.style.display = "block";
  setCopilotEnabled(true);

  const roleCounts = {};
  result.classifications.forEach((c) => {
    roleCounts[c.role] = (roleCounts[c.role] || 0) + 1;
  });

  investigationTilesEl.innerHTML =
    tile("Panel shape (T, N)", result.panel_shape.join(" x ")) +
    tile("Root-cause candidates", roleCounts.ROOT_CANDIDATE || 0) +
    tile("Upstream", roleCounts.UPSTREAM || 0) +
    tile("Downstream", roleCounts.DOWNSTREAM || 0) +
    tile("Uncertain-direction links", roleCounts.UNCERTAIN_LINK || 0);

  const roleByVarName = {};
  result.classifications.forEach((c) => {
    roleByVarName[c.var_name] = c;
  });

  // Only draw nodes that are TARGET, or reachable to/from it (skip UNRELATED,
  // same declutter principle used in Causal_Discovery_Service/test_ui).
  const visibleRoles = new Set(["TARGET", "ROOT_CANDIDATE", "UPSTREAM", "DOWNSTREAM", "UNCERTAIN_LINK"]);
  const visibleNodeIds = new Set(
    result.classifications.filter((c) => visibleRoles.has(c.role)).map((c) => c.var_name)
  );

  const nodes = result.graph.nodes
    .filter((n) => visibleNodeIds.has(n.var_name))
    .map((n) => {
      const classification = roleByVarName[n.var_name];
      const hopLabel = classification.hops != null ? ` (${classification.hops} hop${classification.hops === 1 ? "" : "s"})` : "";
      return {
        data: {
          id: n.var_name,
          label: `${n.metric}${hopLabel}`,
          role: classification.role,
        },
      };
    });

  // The same underlying relationship can appear twice in the raw edge list
  // (once as A->B, once as B->A at the same lag) - LPCMCI reports it from
  // both variables' perspective. Merge these into a single line per
  // (pair, lag), same principle used in Causal_Discovery_Service/test_ui,
  // so the graph doesn't show two overlapping arrows for one relationship.
  const mergedByKey = new Map();
  result.graph.edges
    .filter((e) => e.source !== e.target && visibleNodeIds.has(e.source) && visibleNodeIds.has(e.target))
    .forEach((e) => {
      const key = [e.source, e.target].sort().join("~~") + `@lag${e.lag}`;
      const existing = mergedByKey.get(key);
      if (!existing || Math.abs(e.strength) > Math.abs(existing.strength)) {
        mergedByKey.set(key, e);
      }
    });

  const edges = Array.from(mergedByKey.values()).map((e, index) => ({
    data: {
      id: `e${index}`,
      source: e.source,
      target: e.target,
      label: `${e.edge_mark} lag=${e.lag}`,
    },
  }));

  if (cy) cy.destroy();

  cy = cytoscape({
    container: document.getElementById("cy"),
    elements: [...nodes, ...edges],
    style: [
      {
        selector: "node",
        style: {
          "background-color": (el) => ROLE_COLORS[el.data("role")] || "#1c2733",
          "border-color": "#e8ebf1",
          "border-width": 1,
          label: "data(label)",
          color: "#0b0e14",
          "font-size": 9,
          "font-weight": "bold",
          "text-wrap": "wrap",
          "text-valign": "center",
          "text-halign": "center",
          shape: "round-rectangle",
          width: 110,
          height: 44,
        },
      },
      {
        selector: "node[role = 'UNCERTAIN_LINK']",
        style: { color: "#e8ebf1" },
      },
      {
        selector: "edge",
        style: {
          width: 2,
          "line-color": "#5a6272",
          "target-arrow-color": "#5a6272",
          "target-arrow-shape": "triangle",
          "curve-style": "bezier",
          label: "data(label)",
          "font-size": 8,
          color: "#8b93a5",
        },
      },
    ],
    layout: { name: "breadthfirst", directed: true, padding: 30, spacingFactor: 1.3 },
  });

  classificationsBodyEl.innerHTML = result.classifications
    .filter((c) => visibleRoles.has(c.role))
    .sort((a, b) => (a.hops ?? -1) - (b.hops ?? -1))
    .map(
      (c) =>
        `<tr><td>${c.var_name}</td><td><span class="role-chip ${c.role}">${c.role.replaceAll("_", " ")}</span></td><td>${c.hops ?? "-"}</td></tr>`
    )
    .join("");
}

// ---------------------------------------------------------------------
// AI Explanation
// ---------------------------------------------------------------------

const CHAIN_ROLE_ICON = {
  ROOT_CANDIDATE: "🔴",
  UPSTREAM: "🔵",
  TARGET: "🎯",
  DOWNSTREAM: "⚠️",
  UNCERTAIN_LINK: "❓",
};

function renderExplanation(result) {
  explanationLoadingNoteEl.style.display = "none";
  explanationContentEl.style.display = "block";

  explainWhatsHappeningEl.textContent = result.whats_happening;
  explainChainNarrativeEl.textContent = result.chain_narrative;
  explainRootCauseEl.textContent = result.root_cause_summary;
  explainWhatCouldGoWrongEl.textContent = result.what_could_go_wrong;

  explainChainNodesEl.innerHTML = result.chain_nodes
    .map(
      (n) => `
        <div class="chain-node">
          <span class="chain-node-icon">${n.role_icon || CHAIN_ROLE_ICON[n.role] || ""}</span>
          <div class="chain-node-body">
            <div class="chain-node-title">${n.metric} <span class="role-chip ${n.role}">${n.role_label}</span></div>
            <div class="chain-node-desc">${n.explanation}</div>
          </div>
        </div>`
    )
    .join("");

  if (result.next_steps && result.next_steps.length > 0) {
    explainNextStepsEl.innerHTML = result.next_steps.map((s) => `<li>${s}</li>`).join("");
    explainNextStepsNoteEl.style.display = "none";
  } else {
    explainNextStepsEl.innerHTML = "";
    explainNextStepsNoteEl.textContent = "No recommended actions are defined for this warning type yet.";
    explainNextStepsNoteEl.style.display = "block";
  }

  if (result.next_steps_source === "fallback_menu") {
    explainNextStepsNoteEl.textContent =
      "Showing the standard action list for this warning type - the AI-ranked version wasn't available.";
    explainNextStepsNoteEl.style.display = "block";
  }
}

async function loadExplanationOnce() {
  explanationSectionEl.style.display = "block";
  try {
    const response = await fetch(`${API_BASE}/api/warnings/${warningId}/explanation`);
    if (!response.ok) return;
    const data = await response.json();
    if (data.result) renderExplanation(data.result);
  } catch (error) {
    // Best-effort - the causal graph and Copilot above remain usable either way.
  }
}

function pollExplanationUntilReady() {
  explanationSectionEl.style.display = "block";
  explanationLoadingNoteEl.style.display = "block";
  explanationContentEl.style.display = "none";

  let attempts = 0;
  const maxAttempts = 20; // ~60s - the report is generated right after the investigation, one extra LLM call

  const handle = setInterval(async () => {
    attempts += 1;
    try {
      const response = await fetch(`${API_BASE}/api/warnings/${warningId}/explanation`);
      if (response.ok) {
        const data = await response.json();
        if (data.result) {
          clearInterval(handle);
          renderExplanation(data.result);
          return;
        }
      }
    } catch (error) {
      // keep retrying until maxAttempts
    }

    if (attempts >= maxAttempts) {
      clearInterval(handle);
      explanationLoadingNoteEl.textContent = "Could not generate an AI explanation for this investigation.";
    }
  }, 3000);
}

// ---------------------------------------------------------------------
// Copilot
// ---------------------------------------------------------------------

function setCopilotEnabled(enabled) {
  copilotSectionEl.style.display = "block";
  copilotInputEl.disabled = !enabled;
  copilotSendBtnEl.disabled = !enabled;
  copilotDisabledNoteEl.style.display = enabled ? "none" : "block";
  copilotSuggestionsEl.style.display = enabled ? "flex" : "none";

  if (enabled) {
    loadCopilotHistory();
  } else {
    copilotMessagesEl.innerHTML = "";
  }
}

function appendBubble(role, text) {
  const bubble = document.createElement("div");
  bubble.className = `copilot-bubble ${role}`;
  bubble.textContent = text;
  copilotMessagesEl.appendChild(bubble);
  copilotMessagesEl.scrollTop = copilotMessagesEl.scrollHeight;
  return bubble;
}

async function loadCopilotHistory() {
  try {
    const response = await fetch(`${API_BASE}/api/warnings/${warningId}/copilot/history`);
    if (!response.ok) throw new Error(`status ${response.status}`);
    const data = await response.json();
    copilotMessagesEl.innerHTML = "";
    data.turns.forEach((turn) => appendBubble(turn.role, turn.content));
  } catch (error) {
    // History is a convenience, not required for asking new questions -
    // fail quietly and leave the message list as-is.
  }
}

async function sendCopilotMessage(text) {
  copilotInputEl.disabled = true;
  copilotSendBtnEl.disabled = true;

  appendBubble("user", text);
  const pending = appendBubble("pending", "Thinking...");

  try {
    const response = await fetch(`${API_BASE}/api/warnings/${warningId}/copilot/ask`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: text }),
    });
    const data = await response.json().catch(() => ({}));
    pending.remove();

    if (!response.ok) {
      throw new Error(data.detail || `status ${response.status}`);
    }
    appendBubble("assistant", data.reply);
  } catch (error) {
    pending.remove();
    appendBubble("error", `Could not get a reply: ${error.message}`);
  } finally {
    copilotInputEl.disabled = false;
    copilotSendBtnEl.disabled = false;
    copilotInputEl.focus();
  }
}

copilotFormEl.addEventListener("submit", (event) => {
  event.preventDefault();
  const text = copilotInputEl.value.trim();
  if (!text) return;
  copilotInputEl.value = "";
  sendCopilotMessage(text);
});

copilotSuggestionsEl.addEventListener("click", (event) => {
  const chip = event.target.closest(".suggestion-chip");
  if (!chip) return;
  sendCopilotMessage(chip.dataset.q);
});

copilotClearBtnEl.addEventListener("click", async () => {
  try {
    await fetch(`${API_BASE}/api/warnings/${warningId}/copilot`, { method: "DELETE" });
  } catch (error) {
    // best-effort
  }
  copilotMessagesEl.innerHTML = "";
});

investigateBtn.addEventListener("click", startInvestigation);
loadWarning();
