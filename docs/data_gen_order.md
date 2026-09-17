STEP 1
common/
seed.py
ids.py
dates.py
distributions.py

STEP 2
master/
regions
cities
vehicle_models
dealers
plants
machines

STEP 3
auto/
customers
leads
followups
test_drives
bookings

STEP 4
finance_applications
cancellations
allocations
deliveries

STEP 5
suppliers
supplier_lots
production_batches
service
warranty

STEP 6
manufacturing causal time series

STEP 7
finance customers
loans
payments

STEP 8
collections cases
collections interactions

STEP 9
logistics routes
warehouse events
shipments

STEP 10
ELV
RVSF
dMRV
credits

STEP 11
scenario engine

STEP 12
ground truth

STEP 13
validation

STEP 14
CSV export

STEP 15
PostgreSQL import

STEP 16
FastAPI services consume DB

STEP 17
Frontend displays calculated output

# Directory Structure

data/
│
├── config/
│   ├── generation.yaml
│   ├── scenarios.yaml
│   └── distributions.yaml
│
├── generators/
│   │
│   ├── common/
│   │   ├── seed.py
│   │   ├── ids.py
│   │   ├── dates.py
│   │   ├── distributions.py
│   │   └── helpers.py
│   │
│   ├── master/
│   │   ├── geography.py
│   │   ├── vehicle_models.py
│   │   ├── dealers.py
│   │   ├── plants.py
│   │   ├── machines.py
│   │   ├── warehouses.py
│   │   ├── routes.py
│   │   └── finance_products.py
│   │
│   ├── auto/
│   │   ├── customers.py
│   │   ├── leads.py
│   │   ├── followups.py
│   │   ├── test_drives.py
│   │   ├── bookings.py
│   │   ├── finance_applications.py
│   │   ├── cancellations.py
│   │   ├── allocations.py
│   │   ├── deliveries.py
│   │   ├── service.py
│   │   ├── production.py
│   │   ├── suppliers.py
│   │   └── warranty.py
│   │
│   ├── causal/
│   │   ├── manufacturing_timeseries.py
│   │   ├── mobility_timeseries.py
│   │   ├── scenarios.py
│   │   └── ground_truth.py
│   │
│   ├── finance/
│   │   ├── customers.py
│   │   ├── loans.py
│   │   ├── payments.py
│   │   └── cross_sell.py
│   │
│   ├── collections/
│   │   ├── cases.py
│   │   └── interactions.py
│   │
│   ├── logistics/
│   │   ├── shipments.py
│   │   └── warehouse_events.py
│   │
│   ├── circularity/
│   │   ├── elv.py
│   │   ├── rvsf.py
│   │   ├── dmrv.py
│   │   └── credits.py
│   │
│   ├── xr/
│   │   └── sessions.py
│   │
│   ├── governance/
│   │   ├── recommendations.py
│   │   ├── trust.py
│   │   └── audit.py
│   │
│   ├── agents/
│   │   └── workflow.py
│   │
│   └── copilot/
│       └── evaluation_cases.py
│
├── scripts/
│   ├── generate_all.py
│   ├── validate_all.py
│   ├── export_csv.py
│   └── import_postgres.py
│
├── synthetic/
│   ├── master/
│   ├── auto/
│   ├── causal/
│   ├── finance/
│   ├── collections/
│   ├── logistics/
│   ├── circularity/
│   ├── xr/
│   ├── governance/
│   ├── agents/
│   └── copilot/
│
└── ground_truth/
    ├── outcomes/
    ├── causal/
    ├── simulations/
    ├── recommendations/
    └── copilot/