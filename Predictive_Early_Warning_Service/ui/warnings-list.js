const API_BASE = window.PEWS_API_BASE || "http://127.0.0.1:8792";
const warningsListEl = document.getElementById("warningsList");
const refreshNoteEl = document.getElementById("refreshNote");

function timeAgo(isoString) {
  const seconds = Math.round((Date.now() - new Date(isoString).getTime()) / 1000);
  if (seconds < 60) return `${seconds}s ago`;
  if (seconds < 3600) return `${Math.round(seconds / 60)}m ago`;
  return `${Math.round(seconds / 3600)}h ago`;
}

function formatInr(value) {
  return `Rs. ${Math.round(value).toLocaleString("en-IN")}`;
}

function renderWarnings(warnings, rankByType) {
  if (!warnings.length) {
    warningsListEl.innerHTML = '<p class="empty-note">No open warnings right now.</p>';
    return;
  }

  // API already sorts newest-first by warning_timestamp (frozen at first
  // detection - see warnings_store.py), so this list order reflects
  // genuinely new detections appearing over time, not a re-shuffle.
  warningsListEl.innerHTML = warnings
    .map((w) => {
      const pct = Math.round(w.prediction_probability * 100);
      const detectedSecondsAgo = (Date.now() - new Date(w.warning_timestamp).getTime()) / 1000;
      const isNew = detectedSecondsAgo < 120;
      const lastSeen = w.last_seen_at || w.warning_timestamp;

      const eligible = w.is_warranty_eligible;
      const eligibilityBadge =
        eligible === true
          ? '<span class="eligibility-badge eligible">Warranty: Yes</span>'
          : eligible === false
            ? '<span class="eligibility-badge not-eligible">Warranty: No</span>'
            : '<span class="eligibility-badge unknown">Warranty: Unknown</span>';

      const rankInfo = rankByType[w.warning_type];
      const impactBadge = rankInfo
        ? `<span class="impact-badge">#${rankInfo.rank} fleet-wide &middot; ${rankInfo.affected_vehicle_count} vehicles &middot; ${formatInr(rankInfo.total_expected_liability_inr)}</span>`
        : "";

      return `
        <div class="warning-card severity-${w.severity}">
          <div class="main">
            <div class="type">
              ${isNew ? '<span class="status-pill OPEN" style="background:rgba(255,107,87,0.25);color:#ff6b57;">NEW</span> ' : ""}
              ${w.warning_type.replaceAll("_", " ")}
              <span class="status-pill ${w.status}">${w.status}</span>
              ${eligibilityBadge}
              ${impactBadge}
            </div>
            <div class="sub">
              Vehicle: ${w.vehicle_id} &middot; Target: ${w.target_metric}
              <br />
              <b>Likely between ${w.forecast_gap_hours ?? 0}h and ${w.forecast_horizon_hours}h from now</b>
              <br />
              First detected: ${timeAgo(w.warning_timestamp)} &middot; Last confirmed: ${timeAgo(lastSeen)}
            </div>
          </div>
          <div class="risk">
            <div class="pct">${pct}%</div>
            <div class="label">Risk</div>
          </div>
          <div>
            <button class="action-btn" onclick="investigate('${w.warning_id}')">Investigate</button>
          </div>
        </div>`;
    })
    .join("");
}

function investigate(warningId) {
  // Opens a SEPARATE screen (new URL/page), per the design: clicking
  // Investigate does not swap content in place on this list page.
  window.location.href = `investigate.html?warning_id=${warningId}`;
}

async function loadRankByType() {
  // Best-effort - the warnings list must still render even if no impact
  // ranking has been computed yet (e.g. right after a fresh deploy,
  // before scheduler.py's first tick) or the fetch fails.
  try {
    const response = await fetch(`${API_BASE}/api/warnings/impact-ranking?limit=100`);
    if (!response.ok) return {};
    const data = await response.json();
    const rankByType = {};
    data.ranked_issues.forEach((issue, index) => {
      rankByType[issue.issue_category] = {
        rank: index + 1,
        affected_vehicle_count: issue.affected_vehicle_count,
        total_expected_liability_inr: issue.total_expected_liability_inr,
      };
    });
    return rankByType;
  } catch (error) {
    return {};
  }
}

async function refresh() {
  try {
    const [warningsResponse, rankByType] = await Promise.all([fetch(`${API_BASE}/api/warnings`), loadRankByType()]);
    if (!warningsResponse.ok) throw new Error(`status ${warningsResponse.status}`);
    const warnings = await warningsResponse.json();
    const open = warnings.filter((w) => w.status !== "RESOLVED" && w.status !== "FALSE_POSITIVE");
    renderWarnings(open, rankByType);
    refreshNoteEl.textContent = `Last updated ${new Date().toLocaleTimeString()}.`;
  } catch (error) {
    warningsListEl.innerHTML = `<p class="empty-note">Could not reach the API at ${API_BASE}: ${error.message}</p>`;
  }
}

refresh();
setInterval(refresh, 10000);
