# Mahindra AI Nexus — Time-Series Causal Discovery with LPCMCI

## Overview

This service is responsible for **causal discovery and root-cause analysis on time-series data**.

Its job is not simply to find metrics that move together. Its job is to find the most likely **cause-and-effect relationships across time** and use those relationships to explain an alert or early warning.

In simple terms:

> A predictive system says **"something may go wrong."**  
> The LPCMCI causal service tries to explain **"what chain of events most likely led to it."**

The service uses **LPCMCI** from the **Tigramite** library. LPCMCI is a statistical causal-discovery algorithm. It is **not a neural network** and it does not learn a black-box prediction model.

---

# 1. What this service does

The causal-discovery service:

- reads historical time-series metrics;
- cleans and prepares the data;
- selects a manageable set of useful variables;
- tests which variables have direct statistical relationships after controlling for other variables;
- checks relationships across time lags;
- builds a causal graph;
- keeps information about edge direction and edge type;
- identifies upstream/root-cause candidates;
- traces a causal path backward from an alert metric;
- returns the result to the API/UI for investigation.

The final output can answer questions such as:

- What is driving this alert?
- Which metric changed first?
- What happened one or two time steps before the issue?
- Is the relationship direct or likely caused by a hidden factor?
- What is the upstream chain behind a warranty, quality, telemetry, or manufacturing warning?
- How many causal steps, or "hops", separate the alert from an upstream cause?

---

# 2. What this service does **not** do

This repository should be kept clearly separate from the upstream predictive system.

The causal service does **not**:

- train the original early-warning prediction model;
- generate the original alert by itself;
- replace the predictive model;
- use SHAP as the causal-discovery algorithm;
- hardcode causal edges;
- treat ordinary correlation as proof of causation.

The upstream predictive system answers:

> **"Is an issue likely to happen?"**

The causal service answers:

> **"Given that the issue or alert exists, what causal chain in the observed system may explain it?"**

---

# 3. High-level system design

```text
                        ┌─────────────────────────────┐
                        │   Operational Time-Series   │
                        │ Manufacturing / Telematics  │
                        │ Sensors / Business Metrics  │
                        └──────────────┬──────────────┘
                                       │
                                       v
                        ┌─────────────────────────────┐
                        │      Data Ingestion /       │
                        │       Panel Builder         │
                        └──────────────┬──────────────┘
                                       │
                                       v
                        ┌─────────────────────────────┐
                        │      Data Preprocessing     │
                        │ Missing values / scaling /  │
                        │ stationarity / constants    │
                        └──────────────┬──────────────┘
                                       │
                                       v
                        ┌─────────────────────────────┐
                        │     Variable Selection      │
                        │ Keep useful variables and   │
                        │ force-include alert target  │
                        └──────────────┬──────────────┘
                                       │
                                       v
                        ┌─────────────────────────────┐
                        │       Tigramite LPCMCI      │
                        │  ParCorr + lagged testing   │
                        └──────────────┬──────────────┘
                                       │
                                       v
                        ┌─────────────────────────────┐
                        │       Causal Graph          │
                        │ Nodes + Edges + Lags +      │
                        │ Marks + Strength + p-values │
                        └──────────────┬──────────────┘
                                       │
                                       v
                        ┌─────────────────────────────┐
                        │ Root-Cause / Chain Tracing  │
                        │ Walk backward from alert    │
                        └──────────────┬──────────────┘
                                       │
                                       v
                        ┌─────────────────────────────┐
                        │       FastAPI / UI          │
                        │ Graph + explanation + hops  │
                        └─────────────────────────────┘


      Separate upstream predictive system
      ─────────────────────────────────────────────────────────

                        ┌─────────────────────────────┐
                        │      Prediction Model       │
                        │ Alert / confidence / target │
                        └──────────────┬──────────────┘
                                       │
                                       v
                        ┌─────────────────────────────┐
                        │   Alert Predictions Store   │
                        └──────────────┬──────────────┘
                                       │
                                       └──────► tells the causal service
                                                which host/entity and metric
                                                should be investigated
```

---

# 4. End-to-end workflow

The complete workflow is:

```text
1. Time-series data becomes available
            ↓
2. Select the entities/hosts/assets to analyse
            ↓
3. Select numeric metrics for those entities
            ↓
4. Build one time-aligned multivariate panel
            ↓
5. Force-include the alert metric if required
            ↓
6. Clean and preprocess the panel
            ↓
7. Remove constant/unusable variables
            ↓
8. Limit the number of variables if the panel is too large
            ↓
9. Convert the panel into Tigramite pp.DataFrame format
            ↓
10. Run ParCorr conditional-independence tests
            ↓
11. Run LPCMCI across lag 0 ... tau_max
            ↓
12. Read graph, value, and significance matrices
            ↓
13. Convert discovered relationships into graph nodes and edges
            ↓
14. Identify upstream/root-cause candidates
            ↓
15. Start from the alert node and walk backward through the graph
            ↓
16. Count graph edges as "hops"
            ↓
17. Return the causal chain to API/UI
```

---

# 5. Data ingestion

LPCMCI needs a **multivariate time-series matrix**.

Conceptually, the input looks like this:

```text
timestamp   vehicle_A||battery_temp   vehicle_A||voltage   vehicle_A||current   ...
T1                     34.2                    399.1                21.4
T2                     34.7                    398.5                22.9
T3                     35.4                    397.8                25.1
T4                     36.1                    396.9                27.6
...
```

or for manufacturing:

```text
timestamp   machine_A||temperature   machine_A||vibration   machine_A||load   ...
T1                     61.2                   2.1                  0.72
T2                     62.8                   2.3                  0.74
T3                     65.5                   2.8                  0.79
T4                     69.1                   3.4                  0.83
...
```

Each **column** is one metric for one entity.

Each **row** represents a time-aligned observation.

The causal algorithm works on these historical observations. It should not be given a predefined list of "correct" causal edges.

---

# 6. Host / asset selection and variable selection are different

Two separate selections happen before LPCMCI runs.

## A. Entity or host selection

This decides **which hosts, vehicles, machines, or assets are included** in the analysis.

The selection may use:

- active alerts;
- prediction activity;
- topology neighbours;
- configured host/entity limits;
- the current investigation target.

This happens before the time-series panel is built.

## B. Variable selection

After the panel is built, there may still be too many metric columns.

The LPCMCI runner can therefore apply a variable-selection cap and keep the most useful variables.

Typical selection criteria include:

- variance;
- host/entity coverage;
- computational limits;
- forced inclusion of the alert target metric.

These are two different concepts:

> **Entity selection decides whose data enters the panel.**  
> **Variable selection decides which metric columns are finally sent to LPCMCI.**

---

# 7. Preprocessing

Before causal discovery, the data must be made suitable for statistical testing.

Typical preprocessing steps are:

1. handle missing values;
2. align observations by timestamp;
3. normalize or standardize numeric columns;
4. remove constant columns;
5. check stationarity;
6. remove unusable variables.

A constant metric contains no useful changing information, so it cannot help explain time-series causality.

Example:

```text
battery_voltage = 400, 400, 400, 400, 400...
```

This column contains no variation and should normally be removed.

---

# 8. Why stationarity is checked

Time-series causal methods work best when the statistical behaviour of the series is reasonably stable.

A strongly drifting series can create misleading relationships.

For that reason, the preprocessing stage can test stationarity and apply the project's configured handling before LPCMCI runs.

The important idea is simple:

> We want LPCMCI to analyse meaningful changes in the system, not artificial trends caused only by an unstable series.

---

# 9. Tigramite data format

After preprocessing, the cleaned matrix is converted into Tigramite's time-series container:

```python
pp.DataFrame(...)
```

This is the format expected by Tigramite's causal-discovery algorithms.

The algorithm sees only the prepared time-series observations and variable names.

---

# 10. Independence testing with ParCorr

The service uses **Partial Correlation (`ParCorr`)** as the conditional-independence test.

A normal correlation asks:

> Do X and Y move together?

Partial correlation asks a more useful question:

> Do X and Y still have a relationship after we control for other relevant variables?

Example:

```text
Temperature ─────► Vibration
      │
      └──────────► Downtime
```

Suppose vibration and downtime are correlated.

A simple correlation may suggest:

```text
Vibration → Downtime
```

But if that relationship disappears after controlling for temperature, the algorithm has evidence that the apparent relationship may be indirect.

This conditional testing is one of the main reasons causal discovery is more useful than a normal correlation heatmap.

---

# 11. LPCMCI

LPCMCI is the main causal-discovery algorithm used by this service.

The "L" is important.

It is designed for settings where some relevant causes may be **unobserved or latent**.

In real systems, we rarely measure every possible factor.

Examples of unmeasured factors may include:

- driver behaviour;
- road conditions;
- operator behaviour;
- small environmental changes;
- unrecorded maintenance conditions;
- supplier-process variations;
- hidden control-system states.

LPCMCI can represent uncertainty caused by these hidden variables instead of always forcing a direct X → Y conclusion.

---

# 12. Why LPCMCI instead of plain PCMCI

Plain PCMCI is suitable when the causal assumptions are closer to a system in which all important variables are observed.

LPCMCI is preferred when latent confounding may exist.

Example:

```text
              Hidden factor Z
              /            \
             v              v
        Metric X          Metric Y
```

If Z is not measured, X and Y may appear strongly related.

A method that assumes there are no hidden causes may incorrectly report:

```text
X → Y
```

LPCMCI can instead represent that the relationship may be explained by a latent common cause.

This makes it more suitable for complex real-world systems where the measured data is never perfectly complete.

---

# 13. Important LPCMCI parameters

## `tau_max`

`tau_max` defines the maximum time lag LPCMCI should examine.

Example:

```text
tau_max = 2
```

means the algorithm can investigate relationships such as:

```text
X(t)   → Y(t)
X(t-1) → Y(t)
X(t-2) → Y(t)
```

So LPCMCI is not only asking whether two variables move together now.

It is also asking whether an earlier change in one variable helps explain a later change in another.

---

## `pc_alpha`

`pc_alpha` controls how strict the conditional-independence testing is.

Example:

```text
pc_alpha = 0.10
```

A lower value is generally stricter and usually produces fewer retained relationships.

For example:

```text
0.10  → more permissive
0.05  → stricter
0.01  → very strict
```

The correct value depends on the data, sample size, domain and validation strategy.

---

# 14. What LPCMCI returns

Tigramite produces matrices that describe the discovered graph.

The important outputs are conceptually:

```text
graph
val_matrix
p_matrix
```

## `graph`

Describes the relationship/edge mark between variables.

Examples may include directional or partially oriented edge marks.

## `val_matrix`

Contains the statistical strength or test value for a relationship.

## `p_matrix`

Contains statistical-significance information.

The service converts these matrices into API-friendly graph objects.

---

# 15. Understanding causal graph edges

A simple directed edge:

```text
X ─────► Y
```

means the discovered graph supports X as an upstream cause of Y under the model assumptions and current data.

A bidirected relationship:

```text
X ◄────► Y
```

indicates that the relationship may involve a hidden/common cause rather than a simple direct X → Y relationship.

LPCMCI may also produce edge marks with orientation uncertainty.

The important rule for the application is:

> Do not throw away LPCMCI's edge-orientation information when converting the result into the application's graph format.

---

# 16. Graph construction

Once LPCMCI finishes, the service walks through the returned matrices.

For every source/target/lag combination, it checks whether a valid edge exists.

Conceptually:

```text
for source:
    for target:
        for lag:
            if LPCMCI says an edge exists:
                create causal edge
```

Each stored edge can include information such as:

```text
source variable
target variable
lag
edge mark / orientation
strength
p-value or significance
confidence / stability information
```

The graph is then used by the root-cause and investigation layer.

---

# 17. Root-cause candidates

In the simplified operational graph, a node with no incoming directed edges can be treated as an **upstream/root-cause candidate**.

Example:

```text
Battery Temperature ─► Internal Resistance ─► Voltage Drop ─► Alert
```

`Battery Temperature` has no incoming directed edge in this local graph, so it may be presented as the top upstream cause candidate.

This should be interpreted as:

> "Nothing else in the currently analysed graph explains this node."

It does **not** mean that the variable has no cause anywhere in the real world.

The result is limited to:

- the metrics we measured;
- the time window analysed;
- the selected entities;
- the selected variables;
- the statistical assumptions of LPCMCI.

---

# 18. Alert-centred causal tracing

After the graph is built, another process starts from the alert metric and walks **backward** through upstream causal edges.

Example:

```text
Ambient Temperature
        │
        v
Battery Temperature
        │
        v
Internal Resistance
        │
        v
Battery Voltage
        │
        v
Low-Voltage Warning
```

When the alert is:

```text
Low-Voltage Warning
```

the causal tracer walks backward:

```text
Low-Voltage Warning
        ↑
Battery Voltage
        ↑
Internal Resistance
        ↑
Battery Temperature
        ↑
Ambient Temperature
```

This is how the system builds the causal explanation shown to the user.

---

# 19. What "hops" means

A **hop** is one edge travelled through the already-discovered causal graph.

Example:

```text
A → B → C → ALERT
```

From the alert:

```text
C = 1 hop upstream
B = 2 hops upstream
A = 3 hops upstream
```

Therefore a UI label such as:

```text
UPSTREAM CAUSE · 2 hops
```

means the system travelled across two causal graph edges from the alert node.

This is different from topology hops used earlier for host/entity selection.

---

# 20. Early-warning prediction and causal discovery are separate

This is one of the most important architectural boundaries.

```text
UPSTREAM PREDICTIVE SYSTEM
            │
            │ predicts an issue
            v
     Alert / Prediction
            │
            │ becomes investigation target
            v
LPCMCI CAUSAL DISCOVERY SERVICE
            │
            │ explains possible causal chain
            v
 Root Cause / Upstream Drivers
```

The predictive system may provide:

```text
entity / hostname
predicted issue
target metric
confidence
optional local feature explanation
```

The causal service can use this information to:

1. know which host/entity is being investigated;
2. know which metric should be the graph target;
3. force-include that metric in the LPCMCI panel;
4. trace the graph backward from the correct node.

---

# 21. Why force-including the target metric matters

The variable-selection stage may remove a low-variance or unusual metric.

That becomes a problem if the removed metric is exactly the metric behind the active alert.

For that reason, the target metric should be force-included where possible.

Example:

```text
Normal metric selection:
CPU
Memory
Disk
Network
Temperature

Active alert:
special_battery_resistance_metric
```

Without force inclusion, the alert metric may never enter LPCMCI.

With force inclusion:

```text
CPU
Memory
Disk
Network
Temperature
special_battery_resistance_metric   ← retained because it is the target
```

Now the graph can actually explain the alert.

---

# 22. Detailed workflow design

## Workflow A — Scheduled/background causal discovery

```text
Scheduler
   │
   v
Check whether new time-series data exists
   │
   ├── No new data ──► reuse/skip existing causal result
   │
   └── New data
          │
          v
Select analysis entities
          │
          v
Fetch historical time-series window
          │
          v
Build aligned panel
          │
          v
Preprocess
          │
          v
Select variables
          │
          v
Run LPCMCI
          │
          v
Convert output to graph
          │
          v
Persist run + nodes + edges + metadata
          │
          v
Expose latest graph through API
```

---

## Workflow B — Alert investigation

```text
User opens an alert
        │
        v
Read alert/prediction target
        │
        v
Identify entity + metric
        │
        v
Build scoped time-series panel
        │
        v
Force-include alert metric
        │
        v
Run or reuse relevant LPCMCI graph
        │
        v
Locate alert node
        │
        v
Walk upstream causal edges
        │
        v
Rank root-cause candidates
        │
        v
Return:
- causal chain
- hops
- edge types
- lags
- strengths/significance
- explanation
```

---

## Workflow C — UI investigation flow

```text
Early Warning
      │
      v
User clicks "Investigate"
      │
      v
Causal graph loads
      │
      v
Alert node is highlighted
      │
      v
Upstream chain is highlighted
      │
      ├── click node ──► show metric details
      │
      ├── click edge ──► show lag / orientation / strength
      │
      └── click cause ─► show downstream impact
      │
      v
User receives root-cause explanation
```

---

# 23. Recommended API response structure

A causal investigation response can be shaped like:

```json
{
  "target": {
    "entity_id": "VEHICLE_001",
    "metric": "battery_voltage_v",
    "alert": "LOW_BATTERY_VOLTAGE"
  },
  "causal_run": {
    "algorithm": "lpcmci",
    "tau_max": 2,
    "pc_alpha": 0.1,
    "window_start": "2026-08-20T00:00:00Z",
    "window_end": "2026-08-22T00:00:00Z"
  },
  "root_cause_candidates": [
    {
      "metric": "battery_temperature_c",
      "hops": 3
    }
  ],
  "nodes": [],
  "edges": [],
  "causal_chain": []
}
```

The exact schema can vary, but the API should preserve enough metadata for the UI to explain where the graph came from.

---

# 24. Recommended edge object

Example:

```json
{
  "source": "battery_temperature_c",
  "target": "battery_internal_resistance_ohm",
  "lag": 1,
  "edge_mark": "-->",
  "strength": 0.42,
  "p_value": 0.018,
  "orientation": "DIRECTED"
}
```

This is much better than storing only:

```json
{
  "source": "battery_temperature_c",
  "target": "battery_internal_resistance_ohm"
}
```

because the causal meaning depends on:

- direction;
- lag;
- edge mark;
- statistical evidence.

---

# 25. Suggested run metadata

Every causal run should retain enough information to make the result reproducible.

Useful metadata includes:

```text
run_id
algorithm
domain
entity scope
window start
window end
number of rows
number of variables
selected variable names
tau_min
tau_max
pc_alpha
contemporaneous testing enabled/disabled
preprocessing configuration
source signature / data version
runtime
status
created_at
```

This makes debugging and graph comparison much easier.

---

# 26. Causal graph lifecycle

A useful graph lifecycle is:

```text
NEW DATA
   ↓
RUN LPCMCI
   ↓
STORE GRAPH
   ↓
SERVE GRAPH
   ↓
MORE DATA ARRIVES
   ↓
RUN LPCMCI AGAIN
   ↓
COMPARE / UPDATE GRAPH
```

The graph should be data-driven.

It should not remain permanently unchanged just because an old graph exists.

At the same time, if the underlying source data has not changed, reusing a previous valid run can avoid unnecessary compute.

---

# 27. Important distinction: prediction explanation vs causal explanation

These two explanations answer different questions.

## Predictive explanation

Example:

```text
The model predicted battery failure because:
- battery temperature was high
- voltage was falling
- internal resistance increased
```

This explains why a predictive model produced its score.

## Causal explanation

Example:

```text
Ambient temperature
    ↓
Battery temperature
    ↓
Internal resistance
    ↓
Voltage drop
    ↓
Failure warning
```

This explains the discovered cross-variable chain behind the event.

They may overlap, but they are not the same thing.

---

# 28. Simple example

Assume we observe:

```text
Time   Ambient Temp   Battery Temp   Resistance   Voltage
T1        31              35            0.05        401
T2        34              38            0.06        399
T3        37              42            0.08        395
T4        40              47            0.11        389
```

LPCMCI may discover a pattern like:

```text
Ambient Temp(t-1)
       ↓
Battery Temp(t)
       ↓
Resistance(t+1)
       ↓
Voltage(t+2)
```

If the warning is caused by low voltage, the UI can show:

```text
LOW VOLTAGE WARNING
        ↑
Voltage
        ↑
Internal Resistance
        ↑
Battery Temperature
        ↑
Ambient Temperature
```

This is much more useful than simply saying:

```text
Battery temperature and voltage are correlated.
```

---

# 29. Operational interpretation of the result

The graph should be treated as **statistical causal evidence**, not absolute physical truth.

The discovered result depends on:

- available variables;
- data quality;
- time alignment;
- sampling frequency;
- analysis window;
- preprocessing;
- lag settings;
- significance settings;
- hidden variables;
- statistical assumptions.

For high-impact operational decisions, causal findings should be combined with:

- engineering knowledge;
- domain validation;
- repeated/stable discovery across windows;
- human review.

---

# 30. Suggested monitoring

Useful runtime metrics include:

```text
causal runs started
causal runs completed
causal runs failed
causal runs reused
causal runs skipped
runtime per run
input rows
input variables
selected variables
edges discovered
directed edges
latent/bidirected edges
source data signature
latest successful run
```

These make it easier to distinguish:

```text
"No new data"
```

from:

```text
"LPCMCI failed"
```

or:

```text
"The graph legitimately did not change."
```

---

# 31. Common troubleshooting cases

## No edges are discovered

Possible reasons:

- too little data;
- overly strict `pc_alpha`;
- poor time alignment;
- too many missing values;
- variables are nearly constant;
- lag window is too small;
- true dependencies are weak;
- preprocessing removed important columns.

---

## Too many edges are discovered

Possible reasons:

- `pc_alpha` is too permissive;
- noisy/non-stationary series;
- strong common trends;
- too many variables relative to observations;
- insufficient preprocessing.

---

## Alert metric is missing

Check whether:

- the metric exists in the source;
- the metric is numeric;
- the metric was removed as constant;
- the metric was removed by variable selection;
- force-inclusion was correctly applied.

---

## Graph does not change

Check whether:

- new source rows actually arrived;
- the analysis window moved;
- the source signature changed;
- the scheduler reused an existing run;
- the input panel changed;
- the source has been exhausted or stopped updating.

---

# 32. Plain-English summary

The whole service can be understood in three sentences:

1. **Ingest:** collect the selected entities' historical numeric time-series metrics and place them into one aligned matrix.

2. **Discover:** run Tigramite LPCMCI on that matrix to discover statistically supported time-lagged relationships while allowing for hidden confounding.

3. **Explain:** when an alert exists, start from the alert metric and walk backward through the learned graph to show upstream causes, lags and hop distance.

---

# 33. One-line architecture summary

```text
Time-Series Data
    → Preprocess
    → Select Variables
    → ParCorr
    → LPCMCI
    → Causal Graph
    → Alert-Centred Upstream Trace
    → Root-Cause Explanation
```

with the upstream prediction system connected separately:

```text
Predictive System
    → Alert Target
    → Causal Investigation
```

---

# 34. Final design principle

> **Prediction tells us what may happen. LPCMCI helps us investigate why it may be happening.**

The causal graph must be learned from time-series evidence, preserve LPCMCI's edge orientation and lag information, and remain separate from the upstream model that originally generated the warning.

This separation keeps the architecture understandable:

```text
Observe
   ↓
Predict
   ↓
Explain with LPCMCI
   ↓
Investigate causal chain
   ↓
Recommend / Review / Act
   ↓
Learn from new data
```

---

## Reference note

This README is written in plain English from the supplied LPCMCI workflow material and the project README description. The reference implementation described in the supplied LPCMCI document uses the same main stages: time-series ingestion, preprocessing, variable selection, Tigramite `pp.DataFrame`, `ParCorr`, LPCMCI, graph conversion, and backward causal-chain tracing from an alert target.

