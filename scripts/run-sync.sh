#!/usr/bin/env bash
set -euo pipefail

curl -s -X POST http://localhost:8090/api/snapshot/sync | jq
