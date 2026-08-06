# processed/

Cleaned & normalized real data, reshaped to the exact column contracts of
`../synthetic/` so it loads through the same `seed_database.py` pipeline.

Convention (when real data arrives):

```
processed/<table_name>.csv        # one file per PostgreSQL table
```

Currently empty: the project runs on synthetic data (see `../synthetic/`).
