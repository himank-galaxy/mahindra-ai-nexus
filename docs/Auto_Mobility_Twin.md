# Auto Mobility Twin: current implementation

The mobility screen discovers numeric business measures from the live PostgreSQL
`mobility_timeseries` schema. It excludes keys, foreign keys, identifiers,
provenance, and ground-truth fields. Missing/non-finite and constant measures are
excluded from each analysis with reasons in the response. There is no fixed node
list or permissible-direction whitelist in the active discovery path.

Counts and INR amounts are summed nationally. Known regional averages use their
event-count weights; other numeric measures use an explicitly labelled regional
mean. Raw booking amounts are labelled Booking Value, not Revenue. Raw measured
columns replace the former fixed set of 11 derived funnel metrics. Newly added
numeric business columns are discovered on the next background check. Unit and
desirability conventions affect formatting only; unknown desirability is neutral.

Each stored observation is a trailing 12-hour aggregate. The loader selects the
last national tick near the end of each closed sampling period (within five
minutes of the boundary). Partial regional snapshots and incomplete periods are
excluded. Missing periods split the history into separate continuous segments.
Tigramite receives those segments in multiple-dataset mode; no lag crosses a gap.
Segments shorter than `2*tau_max + 3` observations are excluded. The minimum
observation floor applies after lag warm-up is removed from each segment.

PCMCI uses analytic partial correlation, positive lags, all non-self directions,
and Benjamini-Hochberg correction over the complete tested hypothesis family.
Edges require adjusted q at or below the configured alpha and absolute strength
at least 0.12. The manufacturing and telematics engines are unchanged. No edge
is invented to connect the graph. Only measures that participate in at least one
retained relationship are rendered; isolated measures are counted in metadata and
hidden to keep the graph readable. Cycles are condensed for layout purposes only;
feedback arrows retain their actual directions. Multiple lags have separate curved
tests internally, while the graph shows the single lag with the strongest adjusted
evidence for each directed pair.

The current source was tested at alpha values from 0.01 through 0.50. Alpha 0.30
retained 26 edges and connected 25 of 28 discovered measures; 0.40 added edges
without connecting any additional measure, so 0.30 is the configured default.
The value remains environment-overridable as the history and feature set grow.

The refresh loop checks hourly by default and fingerprints the sampled input.
It recomputes only when that input or the analysis settings change, usually at
the default 12-hour sampling cadence. Data corrections and late arrivals are
therefore recognised even within the same clock period. Computation runs in a
thread and swaps an immutable snapshot only after success. A failed refresh
preserves the previous snapshot and exposes a stale status and explanation.

`GET /api/v1/mobility-twin/graph` returns nodes, full edge evidence, health cards,
dynamic canvas dimensions, and coverage/freshness metadata together. Health cards
highlight the five most connected measures, with stable ties. The browser polls
this endpoint every five minutes. Node detail requests and chat carry the
displayed `snapshot_id`; an expired version returns HTTP 409 and prompts a graph
refetch. A node that disappears is replaced by an available selection. Initial
analysis failure returns a readable HTTP 503, displayed with a retry control.

Node investigations are constructed from the measured evidence for any feature;
they do not depend on an LLM or a fixed action menu. Chat receives the selected
snapshot, actual variable count, source provenance, gap information, and previous
graph comparison. The LLM only explains this evidence. Without a configured LLM,
chat explicitly returns the available evidence rather than a generic canned
answer. No intervention effect or regional ranking is estimated.

The current and prior snapshots remain process-local; restarting the backend
resets graph comparison history. Chat history remains in PostgreSQL. Synthetic
historical and live data generators are unchanged; discovered relationships
describe that synthetic dataset and are not proof of real business causation.

Frontend changes are confined to `routes/mobility-twin.tsx` and the dedicated
`hooks/use-mobility-twin.ts`. Other screens and their shared hooks are untouched.

Validation: `DEBUG=false .venv-linux/bin/pytest tests/api/test_mobility.py
tests/ai/causal/test_mobility_dynamic.py` from `backend`, plus frontend TypeScript,
lint, production build, browser interaction checks, and a read-only database run.


Workspace redesign (2026-09-09): the Mobility route now uses React Flow with
ELK layered layout, a horizontal KPI strip, measured sparklines, domain filters,
search/reveal, cycle-safe upstream/downstream focus, viewport controls, and a
pannable minimap. Four detail cards reuse the snapshot-bound node API. Chat is
a closed-by-default Sheet; its request carries domain/focus and validated visible
metric keys. Labels for source provenance and implementation algorithm are omitted
from the workspace presentation; provenance remains intact in backend evidence.
No live-data claim is substituted. Shared application-shell questions are unchanged.
Analysis remains process-local; this UI change adds no persistence migration.
Recommendations remain evidence-based investigations, without estimated impact.
