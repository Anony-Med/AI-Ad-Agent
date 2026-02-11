# Manual Utilities

This folder contains ad-hoc operational/debug scripts that were previously at the repository root.

These scripts are **not part of the FastAPI runtime path**. They are intended for manual troubleshooting, ad-job monitoring, Cloud Run/GCS inspection, and endpoint testing.

## Categories

- `test_*.py`: manual integration checks against running services/endpoints.
- `monitor_*.py`: live polling/monitoring helpers for job/log status.
- `check_*.py`, `list_*.py`, `parse_*.py`, `fetch_*.py`: diagnostic and inspection tools.
- `kill_*.py`: local process cleanup helpers.
- `create_*.py`, `start_new_job.py`: request/job bootstrap helpers.

## Notes

- `auth_token.txt` is used by some scripts as a local token cache.
- `fix_veo_permissions.sh` is an operational script for fixing Veo-related permissions.

If a script is no longer used, remove it after confirming no operational dependency.
