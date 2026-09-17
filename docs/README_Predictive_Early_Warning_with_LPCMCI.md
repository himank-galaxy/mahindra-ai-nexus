# Predictive Early-Warning System with LPCMCI Causal Investigation

## Overview

This README explains, in plain English, how to build a vehicle early-warning system where:

1. vehicle telemetry is collected continuously;
2. a predictive model estimates whether a problem may happen in the future;
3. an early warning is created when risk becomes high;
4. the warning stores the metric that should be investigated;
5. when the warning is opened, LPCMCI analyzes historical time-series data;
6. the UI shows the target node, upstream causes, root-cause candidates, downstream effects, causal lags, and hop distance.

The most important design principle is:

> **The predictive model generates the warning. LPCMCI explains the warning.**

The predictive model answers:

> **What may happen?**

LPCMCI answers:

> **Why may it be happening?**

---

# 1. What are we trying to build?

Suppose we monitor the vehicle model:

```text
XUV700
```

Each vehicle continuously produces telemetry such as:

```text
battery_temperature
battery_voltage
battery_current
battery_soc
battery_internal_resistance
motor_temperature
coolant_temperature
vehicle_speed
ambient_temperature
charging_status
energy_consumption
impact_force
```

The predictive system should identify patterns that suggest a future issue.

Example:

```text
WARNING

Vehicle:
VEHUNIT_SYN_0001275

Vehicle Model:
XUV700

Predicted Problem:
Battery Overheating

Predicted Within:
Next 24 Hours

Risk:
82%

Severity:
HIGH
```

When the engineer opens this warning, the application should show a causal graph such as:

```text
Ambient Temperature
        ↓
Cooling Demand
        ↓
Battery Current
        ↓
Battery Temperature
        ↓
Internal Resistance
        ↓
Battery Voltage
        ↓
Battery SOC
```

If `Battery Temperature` is the warning target:

```text
Ambient Temperature
= root-cause candidate

Cooling Demand
= upstream

Battery Current
= upstream

Battery Temperature
= target

Internal Resistance
= downstream

Battery Voltage
= downstream

Battery SOC
= downstream
```

---

# 2. High-level architecture

```text
Vehicle Sensors / Telemetry
            │
            ▼
Historical Time-Series Storage
            │
            ├─────────────────────────────┐
            │                             │
            ▼                             ▼
Predictive Model                    LPCMCI Causal Engine
            │                             │
            ▼                             ▼
Future Risk Score                 Learned Causal Graph
            │                             │
            ▼                             │
Early Warning                      │
            │                             │
            └──────────────┬──────────────┘
                           ▼
                  Warning Investigation
                           │
                           ▼
             Root / Upstream / Target /
                  Downstream Graph
```

---

# 3. Prediction and causal discovery are separate systems

## Predictive system

The predictive model answers:

> **What is likely to happen next?**

Examples:

```text
Battery overheating probability in next 24 hours = 82%
Motor overheating probability in next 6 hours = 74%
Component failure probability in next 7 days = 68%
```

Its job is to generate future-risk scores and warnings.

## LPCMCI causal system

The causal system answers:

> **Why does this condition appear to be developing?**

Example:

```text
Ambient Temperature
        ↓
Battery Current
        ↓
Battery Temperature
```

The causal engine should not generate the warning itself.

---

# 4. Simple mental model

```text
Predictive Model
      ↓
WHAT MAY HAPPEN?

LPCMCI
      ↓
WHY MAY IT BE HAPPENING?

Graph Traversal
      ↓
WHAT IS ROOT / UPSTREAM / TARGET / DOWNSTREAM?

Frontend
      ↓
HOW DOES THE ENGINEER INVESTIGATE IT?
```

---

# 5. Step 1 — collect telemetry continuously

Store time-series observations for each vehicle.

Example fields:

```text
timestamp
vehicle_id
vehicle_model
battery_temperature_c
battery_voltage_v
battery_current_a
battery_soc_pct
battery_internal_resistance_ohm
motor_temperature_c
coolant_temperature_c
vehicle_speed_kph
ambient_temperature_c
charging_status
energy_consumption_kwh
impact_g_force
```

Example rows:

```text
10:00  VEH001  XUV700  34.2  399.1  21.4  78  0.051
10:05  VEH001  XUV700  34.8  398.7  22.9  77  0.053
10:10  VEH001  XUV700  35.6  398.0  25.1  76  0.056
10:15  VEH001  XUV700  37.4  397.1  29.4  75  0.061
```

Both the predictive model and LPCMCI should use this same historical evidence.

---

# 6. Step 2 — define warning types

Before training a model, define the future problems you want to predict.

Examples:

```text
BATTERY_OVERHEATING
LOW_BATTERY_VOLTAGE
BATTERY_DEGRADATION
MOTOR_OVERHEATING
ABNORMAL_ENERGY_CONSUMPTION
BRAKE_ANOMALY
COOLING_SYSTEM_RISK
COMPONENT_FAILURE_RISK
WARRANTY_RISK
```

Each warning must also have a prediction horizon.

Examples:

```text
Battery overheating within next 6 hours
Battery overheating within next 24 hours
Battery degradation within next 7 days
Component failure within next 30 days
```

---

# 7. Step 3 — train the predictive model

The model reads recent history and estimates a future outcome.

```text
Past 48 Hours
      ↓
Feature Generation
      ↓
Prediction Model
      ↓
Risk in Next 24 Hours
```

For example, it may observe:

```text
Battery Temperature        rising
Internal Resistance        rising
Voltage                    falling
Battery Current            unstable
Ambient Temperature        high
```

and output:

```text
Battery overheating risk in next 24 hours = 82%
```

---

# 8. Possible predictive models

The architecture does not require one specific algorithm.

Possible models include:

```text
Logistic Regression
Random Forest
XGBoost
LightGBM
Time-Series Classification
Sequence Models
Survival Models
Anomaly Detection
Hybrid Rule + ML
```

For an MVP, a simpler model is often easier to validate.

The important rule is:

> The model must predict a clearly defined future outcome from past data.

---

# 9. Step 4 — create training labels

A supervised predictive model needs historical examples of:

```text
past telemetry
      ↓
what happened later
```

Example:

```text
Historical Input Window:
1 Aug 00:00 → 2 Aug 00:00

Future Label Window:
2 Aug 00:00 → 3 Aug 00:00

Question:
Did battery temperature cross the warning threshold?

Yes = 1
No  = 0
```

The model learns which past patterns are associated with future problems.

---

# 10. Step 5 — run prediction on a schedule

The model can run periodically:

```text
Every 5 minutes
Every 15 minutes
Every hour
```

depending on telemetry frequency and use case.

Workflow:

```text
New telemetry arrives
        ↓
Build recent feature window
        ↓
Run predictive model
        ↓
Calculate future risk
        ↓
Compare with threshold
```

Example:

```text
Risk = 32%  → no warning
Risk = 48%  → no warning
Risk = 67%  → medium monitoring
Risk = 82%  → create high-risk warning
```

---

# 11. Step 6 — create the warning record

When risk crosses the configured threshold, create a persistent warning.

Example:

```text
warning_id:
WARN_000182

vehicle_id:
VEHUNIT_SYN_0001275

vehicle_model:
XUV700

warning_type:
BATTERY_OVERHEATING

target_metric:
battery_temperature_c

prediction_probability:
0.82

forecast_horizon:
24 hours

severity:
HIGH

warning_timestamp:
2026-08-31 10:00

status:
OPEN
```

The warning should be a database record, not only a frontend card.

---

# 12. The target metric connects prediction to LPCMCI

Every warning should map to one causal target metric.

Examples:

```text
BATTERY_OVERHEATING
        ↓
battery_temperature_c

LOW_BATTERY_VOLTAGE
        ↓
battery_voltage_v

BATTERY_DEGRADATION
        ↓
battery_internal_resistance_ohm

MOTOR_OVERHEATING
        ↓
motor_temperature_c

HIGH_ENERGY_CONSUMPTION
        ↓
energy_consumption_kwh
```

This tells the causal system:

> **This is the graph node that should be investigated.**

---

# 13. Step 7 — show the warning in the UI

Example warning card:

```text
┌──────────────────────────────────────────┐
│ HIGH                                     │
│ XUV700                                   │
│ Battery Overheating Risk                 │
│                                          │
│ Vehicle: VEHUNIT_SYN_0001275             │
│ Risk: 82%                                │
│ Predicted Within: 24 Hours               │
│                                          │
│ [Investigate]                            │
└──────────────────────────────────────────┘
```

When the user clicks **Investigate**, the causal workflow starts.

---

# 14. Step 8 — freeze the causal investigation time

Suppose the warning was generated at:

```text
31 Aug 2026
10:00 AM
```

The predictive model is forecasting the future.

But the causal engine must only use data that existed at or before 10:00 AM.

Example:

```text
PAST                              NOW                    FUTURE
──────────────────────────────────│─────────────────────────────
                                  │
<---- LPCMCI lookback window ---->│<-- Prediction horizon ----->
                                  │
                            Warning created
```

For example:

```text
LPCMCI:
Previous 48 hours

Prediction:
Next 24 hours
```

Never use future data to explain the warning at the time it was generated.

---

# 15. Step 9 — build the LPCMCI panel

When the warning is opened, load the historical telemetry for the relevant vehicle.

Example variables:

```text
ambient_temperature_c
battery_current_a
battery_internal_resistance_ohm
battery_soc_pct
battery_temperature_c
battery_voltage_v
motor_temperature_c
vehicle_speed_kph
energy_consumption_kwh
```

Convert them into a time-aligned matrix:

```text
timestamp   ambient_temp   batt_current   batt_temp   resistance   voltage
10:00       31.0           21.4           34.2        0.051        399.1
10:05       31.4           22.9           34.8        0.053        398.7
10:10       32.1           25.1           35.6        0.056        398.0
10:15       33.0           29.4           37.4        0.061        397.1
```

---

# 16. Step 10 — preprocess the data

Conceptual preprocessing:

```text
Historical telemetry
        ↓
Time alignment
        ↓
Missing-value handling
        ↓
Normalization
        ↓
Stationarity checks
        ↓
Remove constant columns
        ↓
Variable selection
```

If there are too many metrics, select the useful variables.

But the target metric must be force-included.

Example:

```text
Warning:
Battery Overheating

Target:
battery_temperature_c
```

Even if normal variable selection would remove it, the target must remain.

---

# 17. Step 11 — run LPCMCI

Now run LPCMCI on the historical time-series panel.

Conceptually:

```text
Prepared Time-Series
        ↓
ParCorr conditional-independence testing
        ↓
LPCMCI
        ↓
Causal graph
```

Example discovered relationships:

```text
ambient_temperature(t-2)
        ↓
battery_current(t-1)

battery_current(t-1)
        ↓
battery_temperature(t)

battery_temperature(t-1)
        ↓
internal_resistance(t)

internal_resistance(t-1)
        ↓
battery_voltage(t)
```

These relationships should come from data, not hardcoded graph definitions.

---

# 18. Step 12 — preserve causal edge information

Store information such as:

```text
source
target
lag
edge orientation
edge mark
strength
statistical significance
```

Example:

```text
Source:
battery_current

Target:
battery_temperature

Lag:
1 interval

Strength:
0.43

p-value:
0.018

Edge:
-->
```

Do not reduce all LPCMCI output to simple arrows if the algorithm produced more detailed edge marks.

---

# 19. Step 13 — identify the target node

The warning already contains:

```text
target_metric = battery_temperature_c
```

Find that node in the causal graph.

That node becomes:

```text
TARGET
```

Example:

```text
╔════════════════════════╗
║ Battery Temperature    ║
║ TARGET                 ║
╚════════════════════════╝
```

---

# 20. Step 14 — identify upstream nodes

Anything causally pointing toward the target is upstream.

Example:

```text
Ambient Temperature
        ↓
Cooling Demand
        ↓
Battery Current
        ↓
Battery Temperature
```

If Battery Temperature is the target:

```text
Battery Current
= 1 hop upstream

Cooling Demand
= 2 hops upstream

Ambient Temperature
= 3 hops upstream
```

---

# 21. Step 15 — identify root-cause candidates

A node with no incoming directed edge in the relevant local graph can be treated as a root-cause candidate.

Example:

```text
Ambient Temperature
        ↓
Cooling Demand
        ↓
Battery Current
        ↓
Battery Temperature
```

`Ambient Temperature` has no incoming edge in this graph.

So the UI can show:

```text
ROOT-CAUSE CANDIDATE
Ambient Temperature
```

It is better to say **candidate**, because the graph is statistical evidence and may still be affected by unobserved factors.

---

# 22. Step 16 — identify downstream nodes

Anything causally after the target is downstream.

Example:

```text
Battery Temperature
        ↓
Internal Resistance
        ↓
Battery Voltage
        ↓
Battery SOC
```

Then:

```text
Internal Resistance
= 1 hop downstream

Battery Voltage
= 2 hops downstream

Battery SOC
= 3 hops downstream
```

This helps the engineer understand what else may be affected if the target condition continues.

---

# 23. Complete target-centered graph

```text
                ROOT-CAUSE CANDIDATE
                Ambient Temperature
                         │
                         ▼
                    Cooling Demand
                  2 hops upstream
                         │
                         ▼
                   Battery Current
                  1 hop upstream
                         │
                         ▼
              ╔════════════════════╗
              ║ Battery Temperature║
              ║       TARGET       ║
              ╚═════════╤══════════╝
                        │
                        ▼
               Internal Resistance
                1 hop downstream
                        │
                        ▼
                  Battery Voltage
                2 hops downstream
                        │
                        ▼
                    Battery SOC
                3 hops downstream
```

---

# 24. What does a hop mean?

One hop means one graph edge.

Example:

```text
A → B → C → TARGET
```

Then:

```text
C = 1 hop upstream
B = 2 hops upstream
A = 3 hops upstream
```

And:

```text
TARGET → D → E
```

means:

```text
D = 1 hop downstream
E = 2 hops downstream
```

---

# 25. Step 17 — combine prediction and causality on one investigation page

The warning page should have two clear sections.

## Prediction section

```text
BATTERY OVERHEATING WARNING

Vehicle Model:
XUV700

Vehicle:
VEHUNIT_SYN_0001275

Predicted Within:
24 hours

Risk:
82%

Severity:
HIGH
```

## Causal investigation section

```text
Target:
Battery Temperature

Top Root-Cause Candidate:
Ambient Temperature

Main Upstream Driver:
Battery Current

Downstream Risks:
Internal Resistance
Battery Voltage
Battery SOC
```

Then render the interactive graph.

---

# 26. Node interaction

When a user clicks a node:

```text
Battery Current

Role:
UPSTREAM CAUSE

Distance:
1 hop upstream

Current Value:
86 A

Recent Change:
+18% over 3 hours

Relationship:
Battery Current(t-1)
→ Battery Temperature(t)

Strength:
0.43

Lag:
1 interval
```

---

# 27. Edge interaction

When a user clicks:

```text
Battery Current → Battery Temperature
```

show:

```text
Source:
Battery Current

Target:
Battery Temperature

Lag:
1 interval

Edge:
-->

Strength:
0.43

p-value:
0.018
```

If LPCMCI produces:

```text
X <-> Y
```

preserve that information because it may represent latent/confounded structure rather than a simple direct cause.

---

# 28. Vehicle-level warnings

The simplest implementation works at individual vehicle level.

Example:

```text
Vehicle:
VEHUNIT_SYN_0001275

Model:
XUV700

Warning:
Battery Overheating

Risk:
82%
```

The causal graph uses that vehicle's own historical telemetry.

This answers:

> **What appears to be happening in this specific vehicle?**

---

# 29. Model-level or fleet-level warnings

You can also build model-wide warnings.

Example:

```text
XUV700 FLEET WARNING

Battery thermal risk increasing

Affected Vehicles:
47

Primary Region:
West

Risk Trend:
Increasing
```

This answers:

> **Is the same issue appearing across many vehicles of this model?**

---

# 30. Per-vehicle causal discovery and model-level consensus

A strong model-level design is:

```text
XUV700 VEH001
        ↓
LPCMCI Graph

XUV700 VEH002
        ↓
LPCMCI Graph

XUV700 VEH003
        ↓
LPCMCI Graph

...
        ↓
Compare discovered edges
        ↓
Calculate recurrence
        ↓
Calculate sign stability
        ↓
Calculate orientation stability
        ↓
Build XUV700 consensus graph
```

Example:

```text
Battery Current → Battery Temperature
```

appears in:

```text
73 out of 100 analysed XUV700 vehicles
```

The model-level graph may then show:

```text
Recurrence:
73%

Direction Stability:
High

Sign Stability:
High
```

---

# 31. Why both levels are useful

```text
INDIVIDUAL VEHICLE WARNING
        ↓
"What is happening to this vehicle?"

MODEL / FLEET WARNING
        ↓
"Is the same problem developing across this vehicle model?"
```

Vehicle-level warnings are useful for:

```text
service
maintenance
fleet monitoring
vehicle support
```

Model-level warnings are useful for:

```text
warranty
quality
engineering
manufacturing
supplier investigation
```

---

# 32. Database concept

Conceptually, the system needs four main groups.

## Raw telemetry

```text
vehicle_telematics_timeseries
```

## Prediction runs

Possible fields:

```text
prediction_id
vehicle_id
vehicle_model
prediction_type
probability
forecast_horizon
model_version
created_at
```

## Early warnings

Possible fields:

```text
warning_id
vehicle_id
vehicle_model
warning_type
target_metric
prediction_probability
severity
forecast_horizon
warning_timestamp
status
```

## Causal data

```text
causal_runs
causal_nodes
causal_edges
```

The warning connects prediction and causal investigation.

---

# 33. Warning relationship

Conceptually:

```text
Warning
 ├─ warning_id
 ├─ vehicle_id
 ├─ vehicle_model
 ├─ warning_type
 ├─ target_metric
 ├─ prediction_probability
 ├─ forecast_horizon
 ├─ warning_timestamp
 └─ causal_run_id
```

Flow:

```text
Prediction
    ↓
Warning
    ↓
Causal Investigation
```

---

# 34. Scheduled predictive workflow

```text
Scheduler
   ↓
Find active vehicles
   ↓
Read recent telemetry
   ↓
Generate features
   ↓
Run warning models
   ↓
Calculate probabilities
   ↓
Apply thresholds
   ↓
Create or update warnings
   ↓
Persist results
```

Users should not need to click anything to generate warnings.

---

# 35. Alert investigation workflow

```text
User opens warning
        ↓
Load warning metadata
        ↓
Identify target metric
        ↓
Identify warning timestamp
        ↓
Select causal lookback window
        ↓
Load historical telemetry
        ↓
Run or reuse LPCMCI
        ↓
Center graph around target
        ↓
Classify graph nodes:
- root candidate
- upstream
- target
- downstream
        ↓
Return investigation
```

---

# 36. UI workflow

```text
Early Warnings Page
        ↓
Select warning
        ↓
Warning Details
        ↓
Prediction Summary
        ↓
Causal Investigation
        ↓
Interactive Graph
        ↓
Click Node / Edge
        ↓
Detailed Explanation
```

---

# 37. Full end-to-end runtime workflow

```text
VEHICLE IS RUNNING
        ↓
Telemetry arrives continuously
        ↓
Store telemetry
        ↓
Prediction scheduler runs
        ↓
Build recent feature window
        ↓
Run predictive model
        ↓
Calculate future risk
        ↓
Risk above configured threshold?
        │
     No │
        └──────────────→ Continue monitoring
        │
       Yes
        ↓
Create early warning
        ↓
Show warning in frontend
        ↓
User opens warning
        ↓
Read:
- vehicle
- model
- target metric
- warning timestamp
        ↓
Take historical window ending at warning timestamp
        ↓
Build LPCMCI panel
        ↓
Force-include target metric
        ↓
Preprocess
        ↓
Run or reuse LPCMCI
        ↓
Find target node
        ↓
Walk backward
        ↓
Find upstream causes
        ↓
Find root-cause candidates
        ↓
Walk forward
        ↓
Find downstream effects
        ↓
Render target-centered graph
```

---

# 38. Complete example — battery overheating

Suppose:

```text
Vehicle:
VEHUNIT_SYN_0001275

Vehicle Model:
XUV700
```

Recent telemetry shows:

```text
Ambient Temperature       rising
Battery Current           rising
Battery Temperature       rising
Internal Resistance       rising
Battery Voltage           falling
```

## Prediction

At:

```text
31 Aug
10:00 AM
```

the predictive model calculates:

```text
Battery overheating probability
during next 24 hours = 82%
```

Warning threshold:

```text
75%
```

Since:

```text
82% > 75%
```

a warning is created.

## Warning

```text
WARNING ID:
WARN_000182

VEHICLE:
VEHUNIT_SYN_0001275

MODEL:
XUV700

WARNING:
Battery Overheating

TARGET:
battery_temperature_c

PROBABILITY:
82%

FORECAST:
next 24 hours

SEVERITY:
HIGH
```

## User investigation

The engineer clicks:

```text
Investigate
```

The system reads:

```text
vehicle:
VEHUNIT_SYN_0001275

target:
battery_temperature_c

warning time:
10:00 AM
```

## Causal window

Configured causal lookback:

```text
48 hours
```

So LPCMCI uses:

```text
29 Aug 10:00 AM
        ↓
31 Aug 10:00 AM
```

No future data is used.

## Example LPCMCI relationships

```text
Ambient Temperature(t-2)
        ↓
Battery Current(t-1)

Battery Current(t-1)
        ↓
Battery Temperature(t)

Battery Temperature(t-1)
        ↓
Internal Resistance(t)

Internal Resistance(t-1)
        ↓
Battery Voltage(t)

Battery Voltage(t)
        ↓
Battery SOC(t+1)
```

## Target-centered graph

```text
Ambient Temperature
ROOT-CAUSE CANDIDATE
        │
        ▼
Battery Current
UPSTREAM · 1 HOP
        │
        ▼
╔════════════════════════╗
║ Battery Temperature    ║
║ TARGET                 ║
╚════════════╤═══════════╝
             │
             ▼
Internal Resistance
DOWNSTREAM · 1 HOP
             │
             ▼
Battery Voltage
DOWNSTREAM · 2 HOPS
             │
             ▼
Battery SOC
DOWNSTREAM · 3 HOPS
```

## Engineer-facing explanation

```text
Battery overheating is predicted within the next 24 hours.

The strongest observed upstream driver is increasing battery current.

Ambient temperature appears further upstream in the causal chain.

If the current condition continues, the graph indicates possible downstream impact on internal resistance, battery voltage, and battery SOC.
```

---

# 39. Example — motor overheating

Prediction:

```text
Motor overheating risk:
76%

Forecast:
next 6 hours
```

Target:

```text
motor_temperature_c
```

Possible graph:

```text
Vehicle Load
     ↓
Motor Current
     ↓
Motor Temperature
     ↓
Coolant Temperature
     ↓
Power Limitation
```

Interpretation:

```text
Root-cause candidate:
Vehicle Load

Upstream:
Motor Current

Target:
Motor Temperature

Downstream:
Coolant Temperature
Power Limitation
```

---

# 40. Example — low battery voltage

Prediction:

```text
Low-voltage risk:
79%

Forecast:
next 12 hours
```

Target:

```text
battery_voltage_v
```

Possible graph:

```text
Battery Temperature
        ↓
Internal Resistance
        ↓
Battery Voltage
        ↓
Battery SOC
```

Interpretation:

```text
Battery Temperature
= root/upstream

Internal Resistance
= upstream

Battery Voltage
= target

Battery SOC
= downstream
```

---

# 41. Example — XUV700 fleet warning

Suppose:

```text
Vehicle Model:
XUV700

Active vehicles analysed:
500

Vehicles showing thermal pattern:
67
```

The prediction layer determines:

```text
XUV700 battery thermal risk is increasing.
```

Suppose:

```text
Battery Current → Battery Temperature
```

appears in:

```text
51 of the 67 affected vehicles
```

Then the fleet warning may show:

```text
XUV700 Fleet Warning

Battery thermal risk increasing

Affected vehicles:
67

Primary repeated upstream relationship:
Battery Current → Battery Temperature

Edge recurrence:
76%

Orientation stability:
High
```

---

# 42. Prediction confidence and causal evidence are different

Do not mix them.

Example:

```text
Prediction probability:
82%
```

means:

> The predictive model estimates an 82% future risk.

But:

```text
Causal edge strength:
0.43

p-value:
0.018

recurrence:
73%
```

describes evidence for the causal relationship.

These values should not be merged into one fake universal confidence score.

---

# 43. Avoid future leakage

If warning time is:

```text
10:00 AM
```

the causal analysis must use:

```text
data <= 10:00 AM
```

The future period should only be used later for evaluation:

```text
Did the predicted problem actually happen?
```

---

# 44. Evaluate the warning after the forecast window closes

Example:

```text
Warning:
Battery overheating in next 24 hours

Predicted probability:
82%
```

After 24 hours:

```text
Actual outcome:
Overheating occurred

Prediction:
Correct
```

or:

```text
Actual outcome:
No overheating

Prediction:
False positive
```

This becomes training/evaluation evidence for future model versions.

---

# 45. Predictive model evaluation

Useful measures include:

```text
Precision
Recall
F1 Score
ROC-AUC
PR-AUC
Calibration
False-positive rate
False-negative rate
Lead time before failure
```

Lead time is important because an early warning should arrive early enough for someone to act.

---

# 46. Causal graph evaluation

If synthetic data has known generating relationships, evaluate LPCMCI separately using:

```text
true-edge recovery
false-edge rate
direction recovery
lag recovery
sign recovery
stability across windows
recurrence across vehicles
```

Prediction quality and causal-graph quality should be measured independently.

---

# 47. Warning lifecycle

Possible warning states:

```text
OPEN
ACKNOWLEDGED
INVESTIGATING
ACTION_RECOMMENDED
ACTION_APPROVED
RESOLVED
FALSE_POSITIVE
EXPIRED
```

Example flow:

```text
OPEN
  ↓
Engineer opens warning
  ↓
INVESTIGATING
  ↓
Causal graph reviewed
  ↓
ACTION_RECOMMENDED
  ↓
Maintenance approved
  ↓
RESOLVED
```

---

# 48. Closed-loop extension

Once prediction and causal explanation work, the system can later become:

```text
OBSERVE
Vehicle telemetry

        ↓

PREDICT
Battery overheating likely

        ↓

EXPLAIN
LPCMCI causal chain

        ↓

RECOMMEND
Inspect thermal-management system

        ↓

APPROVE
Engineer approves

        ↓

ACT
Maintenance action taken

        ↓

LEARN
Did the problem occur?
Did the intervention help?
Was the diagnosis useful?
```

---

# 49. Final system architecture

```text
                         VEHICLE FLEET
                              │
                              ▼
                     Telemetry Collection
                              │
                              ▼
                         PostgreSQL
                              │
              ┌───────────────┴───────────────┐
              │                               │
              ▼                               ▼
      Predictive Pipeline              Causal Pipeline
              │                               │
      Feature Generation                Panel Builder
              │                               │
      Prediction Model                 Preprocessing
              │                               │
       Future Risk Score                  LPCMCI
              │                               │
       Warning Threshold               Causal Graph
              │                               │
              ▼                               │
          Early Warning                      │
              │                               │
              └───────────────┬───────────────┘
                              ▼
                       Investigation API
                              │
                              ▼
                          Frontend
                              │
                    ┌─────────┼──────────┐
                    ▼         ▼          ▼
                  Root     Upstream    Target
                                         │
                                         ▼
                                      Downstream
```

---

# 50. Short summary

The complete system works like this:

```text
Vehicle telemetry arrives
        ↓
Predictive model analyses recent history
        ↓
Model predicts a future problem
        ↓
If risk is high, create a warning
        ↓
Warning stores the target metric
        ↓
User opens warning
        ↓
Take historical telemetry ending at warning time
        ↓
Run or reuse LPCMCI
        ↓
Find the target node
        ↓
Walk backward to find upstream causes
        ↓
Find root-cause candidates
        ↓
Walk forward to find downstream impact
        ↓
Show everything in an interactive causal graph
```

---

# 51. Final design principle

Always keep this separation:

```text
Predictive Model
      =
WHEN / WHAT MAY FAIL?

LPCMCI
      =
WHY MAY THIS CONDITION BE DEVELOPING?

Graph Walker
      =
WHAT IS ROOT / UPSTREAM / TARGET / DOWNSTREAM?

Frontend
      =
HOW DOES AN ENGINEER INVESTIGATE IT?
```

The final experience should look like:

```text
"XUV700 vehicle VEHUNIT_SYN_0001275 has an 82% risk of battery overheating within the next 24 hours."

                    ↓

Engineer opens warning

                    ↓

Root-cause candidate:
Ambient Temperature

Upstream:
Battery Current

Target:
Battery Temperature

Downstream:
Internal Resistance
Battery Voltage
Battery SOC
```

That is the basic architecture for combining predictive early warnings with LPCMCI causal investigation.
