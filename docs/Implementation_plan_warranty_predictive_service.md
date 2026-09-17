# Plan: Warranty Predictive Service — RAG Layer + Clustered Predictive Model

## Implementation status: COMPLETE

Both parts are built and verified end-to-end against real data in
`Warranty_Predictive_Service/` (new standalone service, as decided
below). Key real results from verification:

- **RAG layer**: 74 documents indexed (8 global + 22 surveyor reports +
  22 policy certificates + 22 NCB statements). Category-scoped questions
  correctly retrieve only the relevant document(s); vehicle/claim-scoped
  questions correctly retrieve that vehicle's real documents. Verified
  against the real LLM gateway with all three of this plan's test
  questions, correctly grounded, no invented facts.
- **Predictive model**: 19 of 20 clusters trained (`SEATING` correctly
  skipped - zero real positive examples, logged not crashed). Clusters
  with fewer than 5 real positive examples are marked `low_confidence`
  in every prediction they produce, rather than presented at face value
  - this surfaced a real, honest finding: 2 of the 19 trained clusters
  (`STEEL_BODY_PANELS`, `PAINT_COATINGS`) saturate near P=1.0 for nearly
  every vehicle due to `class_weight="balanced"` reweighting on only 1-2
  positives, and are flagged accordingly rather than hidden.
- **Eligibility gate**: verified against the real telematics-correlated
  accident vehicle from this session's earlier work
  (`VEHUNIT_SYN_0001275`) - correctly excluded via the driving-behavior
  check, citing the real injected impact-g reading against the fleet's
  self-calibrated 95th-percentile threshold.
- **Fleet ranking**: `FASTENER_LOOSENESS` (HIGH severity) correctly
  escalates from raw rupee-rank #29 to displayed rank #1, exactly as
  section 5's escalation rule specifies.
- **Performance**: fleet-wide scoring batched per cluster (~19 model
  calls instead of ~25,000) - full tick in ~74s (1,348 vehicles); the
  API never recomputes live (measured naive per-request cost: ~46s) -
  `scheduler.py` computes once per tick and caches the ranking, the API
  only reads it (~30ms response time).

## Context

This closes out `docs/data_required_for_warranty_predictive_model.md` — the
plan for a "cluster of related issues, not one model per issue" warranty
predictive model, with a financial-impact ranking and a real
warranty/insurance-eligibility gate. All 11 real documents and the real
accident/insurance data described in that plan now exist. What's left is
the two pieces that actually turn that data into a working system:

1. **A RAG layer** so a predicted issue (or a claim question) retrieves the
   exact relevant clause from the document corpus, instead of a copilot
   having to paraphrase raw data.
2. **The actual predictive model** — trained classifiers, one per
   `supplier_component_category` cluster (19 clusters), each predicting a
   probability for every issue in that cluster at once (true shared
   multi-label learning, not 26 separate single-issue models relabeled
   as "clusters" — that would not honor the original ask), turned into a
   ranked, eligibility-gated, rupee-denominated priority list.

**Architecture decision (confirmed with user):** build both as a new
standalone service, `Warranty_Predictive_Service/`, mirroring
`Predictive_Early_Warning_Service` (PEWS) exactly — own venv-less reuse
of `Causal_Discovery_Service/.venv`, own config/training/scheduler/API,
reads the existing CSVs and the document-generator code directly. **Not**
integrated into the backend's Warranty & Quality module: that module
already has a large (3,439-line), different early-warning mechanism
(causal-evidence-chain based, live-replay-Postgres-integrated), and
`insurance_claims`/the document corpus aren't wired into the backend's
DB at all — integrating there would mean new alembic migrations +
replay-source wiring + real risk of conflicting with the existing
engine, for a much larger and riskier change than the value it adds
right now. PEWS's proven architecture is a near-exact fit for this
domain already.

**Confirmed by exploration, not assumed:**
- PEWS's real pattern (`train_model.py`, `features.py`,
  `training_data.py`, `scheduler.py`, `warnings_store.py`,
  `pews_config.py`): one `RandomForestClassifier` per target, mean/min/
  max/trend windowed features, time-based train/test split with a
  gap window between feature-time and label-time to avoid leakage,
  `joblib` persistence bundling the model with its exact feature-column
  list, an async scheduler tick loop, one JSON file per output record.
- **No vector search/embeddings exist anywhere in this project** — it's
  an explicit, documented convention: "context-window RAG, not
  vector-database RAG," already used successfully twice (PEWS Copilot,
  Mobility Copilot). The new RAG layer follows the same convention:
  deterministic category-tagged retrieval, not an embedding index.
- The backend has two independent LLM clients (PEWS's own
  `copilot/llm_client.py`, and `backend/app/ai/llm/provider.py`) — the
  new service gets its own third one, mirroring PEWS's exactly (same
  `gpt-oss-120b`-style OpenAI-compatible gateway, credentials via
  `.env`/`os.getenv`, never hardcoded), since it's a standalone service
  like PEWS, not part of the backend.

---

## Part A: RAG retrieval layer

### The key design decision

The 11 documents only exist as rendered `.md`/`.pdf` files on disk — but
every document's real category tags (`relevant_issue_categories`,
`relevant_component_categories`) already exist as data in the
`Document` dataclass returned by each builder function in
`data/generators/documents/*.py`. **Re-run the builder functions
in-process to build the index, rather than parsing the rendered files.**
This guarantees the index's tags can never drift from the generator's
own logic, and costs nothing extra (the builders are pure Python, no
CSV/file writes required to just get the `Document` object back).

### New files (`Warranty_Predictive_Service/rag/`)

- `document_index.py` — at service startup, imports and calls every
  builder in `data/generators/documents/` (via the same sys.path
  cross-service import pattern PEWS already uses to reach
  `Causal_Discovery_Service`), collects each `Document`, and builds an
  in-memory index: `dict[("issue_category"|"component_category", value)]
  -> list[Document]`. Global documents (Master Warranty Policy, Claim
  Adjudication Guidelines, Boundary Guidelines, Insurance T&C, Rider
  Cover) are tagged against every category they're relevant to; per-claim
  documents (Surveyor Reports) and per-policy documents (Certificates,
  NCB Statements) are additionally indexed by `vehicle_id`/
  `insurance_claim_id`/`policy_number` for direct lookup.
- `retrieval.py` — `retrieve_context(issue_category=None,
  component_category=None, vehicle_id=None, claim_id=None) -> str`:
  looks up matching `Document`s, renders each via the existing
  `render_markdown()` (already built, already proven), concatenates into
  one context block — the same "build a plain-English case file
  deterministically" pattern as PEWS's `context_builder.py`.
- `prompts.py` / `llm_client.py` — copy PEWS's copilot pattern exactly
  (single system message = instructions + retrieved context, one user
  message per question; sync `OpenAI` client; credentials from
  `wps_config.py` via `os.getenv`). Do not invent a new prompting
  convention.
- `service.py` — `ask_warranty_docs(question, issue_category=None,
  component_category=None, vehicle_id=None) -> str`: retrieves context,
  calls the LLM, returns the answer. Mirrors PEWS's
  `copilot/service.py::ask_copilot`.

### API

New endpoint in the service's `api/main.py` (new FastAPI app, mirrors
PEWS's `api/main.py` conventions exactly — CORS, local-only bind):
`POST /api/docs/ask` (question + optional category/vehicle filters).

### Verification

Ask real questions the corpus should answer: "What voids suspension
warranty coverage?" (should retrieve the Driving-Behavior Exclusion
Clauses' SUSPENSION clause), "What's the NCB status for
[a real policy_number from insurance_claims.csv]?" (should retrieve
that specific policy's real NCB Statement), "Is a collision covered
under warranty?" (should retrieve the Boundary Guidelines' ACCIDENT_DAMAGE
row). Confirm retrieved text matches the real source document, and that
the LLM's answer only uses retrieved facts (no invented numbers).

---

## Part B: Clustered predictive model

### Clusters and labels

Reuse `data/generators/auto/service.py`'s real `COMPONENT_ISSUE_MAP` as
the canonical cluster definition (19 `supplier_component_category`
clusters, each mapping to its real `issue_category` values) — do not
redefine this mapping a second time.

**Label source: `service_events`, not `warranty_claims`.** Only 53 real
warranty claims exist — spread across up to 26 issue categories, several
clusters would have zero positive examples and be untrainable.
`service_events` (1,137+ rows, all `UNSCHEDULED_REPAIR` +
`repair_required` rows) is the richer, real signal for "did this issue
occur" and is exactly what `docs/data_required_for_warranty_predictive_model.md`
section 3 already recommended ("leaning on the much larger service_events
table as a supplementary weak-label source"). The model predicts
*occurrence*; whether an occurrence is Mahindra's financial liability is
a separate, already-built downstream step (coverage window + driving
behavior + accident routing), matching the plan's own
`expected cost = P(issue) × cost × is-eligible` formula exactly — the ML
model must not try to absorb eligibility into itself.

**One real multi-label model per cluster, not one-model-per-issue
relabeled.** `sklearn.ensemble.RandomForestClassifier` natively supports
multi-label output (fit directly on a 2D `y`, one column per
issue_category in the cluster) — the fitted trees are genuinely shared
across every issue in that cluster, so a rare issue really does borrow
statistical strength from its more common cluster-mates. This is the
one point where a one-binary-classifier-per-target design (PEWS's own
pattern) would silently contradict the user's original, explicit request
("instead of a separate model for every individual issue") — everything
else about PEWS's pipeline shape is reused as-is.

**Checkpoint/labeling window — adapted from PEWS, not copied verbatim.**
PEWS's telematics data is dense (per-minute), so it uses rolling 6-hour
checkpoints. Warranty data is episodic (one row per service visit), so
the natural checkpoint is each vehicle's `FIRST_INSPECTION` service
event (already real, already timestamped, already present for most
delivered vehicles) — or 60 days post-delivery if no First Inspection
was attended: features are computed from everything known about the
vehicle up to that checkpoint (production/supplier quality scores, First
Inspection outcome), label = whether any issue in the cluster's list
occurred in `service_events` *after* that checkpoint. This preserves
PEWS's core anti-leakage principle (a gap between what you knew and what
you're predicting) in a shape that actually fits this domain's real data.

### New files (`Warranty_Predictive_Service/`)

- `wps_config.py` — cluster definitions (imported from `service.py`'s
  `COMPONENT_ISSUE_MAP`, not redefined), checkpoint rule, min-training-
  rows floor, model paths, `.env`-sourced LLM config. Mirrors
  `pews_config.py`'s all-overridable-via-env-vars convention.
- `features.py` — per-vehicle, per-checkpoint feature vector: production/
  supplier quality scores (from `deliveries.csv`), First Inspection
  outcome, prior-issue counts *outside* the target cluster (cross-cluster
  signal), vehicle age/odometer at checkpoint. **Explicitly documented
  gap, not silently ignored:** telematics-derived features are only
  available for the ~24-vehicle cohort (per this session's own finding)
  — the model must work with telematics features absent/zero for the
  ~1,325 other vehicles, and this is called out in the module docstring
  the same way every other scope limit this session was.
- `training_data.py` — builds the per-cluster labeled dataset from
  `deliveries.csv` + `service_events.csv` using the checkpoint rule above.
- `train_model.py` — one `RandomForestClassifier` per cluster, fit on
  the cluster's multi-label `y`; time-based train/test split (mirrors
  PEWS); reports precision/recall/F1 per issue-column plus a macro
  average; skips a cluster below the min-training-rows floor (log it,
  don't crash the whole run — mirrors PEWS's per-model skip behavior).
  Persists via `joblib`, bundling model + feature-column list + the
  cluster's issue-column order (needed to map `predict_proba`'s output
  back to issue names).
- `cost_reference.py` — **new, small, real-data-grounded piece the plan
  flagged as missing ("a reusable cost-per-part-issue reference table...
  does not exist yet")**: typical repair cost per issue_category,
  computed from the real `claim_amount_inr` distribution in
  `warranty_claims.csv` + `insurance_claims.csv` where enough real
  examples exist, falling back to a `supplier_component_category`-level
  average, both clearly distinguished in the output so a caller knows
  which number is real-sample-backed vs. component-level fallback.
- `eligibility.py` — reuses the *real, already-built* logic rather than
  reimplementing it: imports `BASE_WARRANTY_YEARS`/`BASE_WARRANTY_KM`/
  `COMPONENT_COVERAGE` from `data/generators/documents/warranty_policy_data.py`
  for the coverage-window check, and `BEHAVIOR_CLAUSES` from
  `driving_behavior_data.py` for the driving-behavior check (evaluated
  against real telematics where available, skipped with a clear
  "no telematics coverage" flag otherwise — never fabricated).
- `predict.py` — for a vehicle: load its cluster models, compute
  features, get per-issue probabilities, multiply by `cost_reference`
  and the `eligibility` gate, return the per-issue expected-liability
  numbers.
- `rank.py` — fleet-wide: `priority = P(issue) × cost × eligibility ×
  affected-vehicle-count`, sorted descending, `severity` (real field
  already in `service_events`/`warranty_claims`) as a documented
  escalation flag on top of the rupee ranking — exactly per section 5 of
  the plan document, not a new ranking scheme invented here.
- `scheduler.py` + `predictions_store.py` — mirrors PEWS's
  `scheduler.py`/`warnings_store.py` exactly: periodic tick recomputes
  predictions for vehicles with new service data, persists one JSON
  record per (vehicle, cluster) prediction.
- `api/main.py` — new FastAPI app (mirrors PEWS's `api/main.py`):
  `GET /api/predictions` (ranked list), `GET /api/predictions/{vehicle_id}`,
  plus Part A's `/api/docs/ask`.

### Verification

1. `train_model.py` run against the real `deliveries.csv`/
   `service_events.csv` — confirm at least the larger clusters (the ones
   with real historical issues, e.g. STEERING, SUSPENSION, BRAKING_SYSTEM)
   train successfully and report real precision/recall/F1, and confirm
   thin clusters are skipped with a clear log line, not a crash.
2. Run `predict.py` for a handful of real vehicle IDs, sanity-check the
   output: probabilities in [0,1], costs in a plausible INR range,
   eligibility correctly reflecting a real vehicle's actual age/coverage
   status, and confirm a vehicle whose real telematics shows a driving-
   behavior exclusion pattern (if any exist in the 24-vehicle cohort)
   actually gets gated out.
3. Run `rank.py` fleet-wide, confirm the top of the ranked list is
   plausible (real cluster, real rupee figure) and that severity
   correctly escalates a cheap-but-HIGH-severity issue.
4. Start the API, hit both endpoint groups, confirm JSON shapes and that
   `/api/docs/ask` answers correctly ground in retrieved document text
   (spot-check against the actual document content, same as Part A's
   verification).
