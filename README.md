# LibreLane Backend

FastAPI backend; workspace dosya API'si, job orchestration ve AI uçlarını servis eder.

## Workspace

Kalıcı proje dosyaları `WORKSPACE_ROOT` altında tutulur (varsayılan `/workspace`). Docker compose bu dizini `./workspace` ile bind mount eder.

## Çalıştırma

```bash
docker compose up --build
```

Gateway üzerinden workspace listesi:

```bash
curl http://127.0.0.1:8000/workspace/projects
```
