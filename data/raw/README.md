# raw/

Landing zone for **real** Mahindra source extracts (dealer DMS exports,
finance LOS dumps, logistics telemetry, etc.). Files here are immutable
snapshots — never edited in place.

Convention (when real data arrives):

```
raw/<source_system>/<yyyy-mm-dd>/<extract>.csv|.parquet
```

Currently empty: the project runs on synthetic data (see `../synthetic/`).
