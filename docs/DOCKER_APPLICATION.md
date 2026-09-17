# Docker application startup

The PostgreSQL service is intentionally external to this Compose file. Its
existing container, volume and port mapping are not recreated or modified.

From the project root:

```bash
docker compose up --build -d
```

The stack joins `backend_default`, the existing network of
`mahindra-postgres`. Override the network name only when required:

```bash
MAHINDRA_DB_NETWORK=backend_default docker compose up --build -d
```

URLs:

- Frontend and proxied API: `http://10.10.90.98:5174`
- Backend health through the frontend proxy: `/health`
- Direct backend health: `http://10.10.90.98:8002/health`

Stop only the application containers:

```bash
docker compose down
```

This command leaves the database container and all existing database data
untouched.
