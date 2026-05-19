# GCP Cloud Logging

The application uses standard Python `logging` customized to output JSON.

## Cloud Run Integration
On Cloud Run, all stdout JSON is automatically parsed by GCP Cloud Logging. 

1. `severity` maps to GCP Log levels.
2. `message` becomes the log payload.
3. `X-Cloud-Trace-Context` is mapped if present.

Set `ENABLE_GCP_LOGGING=true` to enable the official `google-cloud-logging` handler for deeper integration.
