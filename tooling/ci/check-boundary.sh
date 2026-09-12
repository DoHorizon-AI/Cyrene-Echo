#!/usr/bin/env bash
# Echo product boundary guard.
#
# Echo keeps its local ArtifactRef adapter and may call Products directly. It
# must not regain a source checkout or runtime dependency on Platform.
set -euo pipefail

repo_root="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$repo_root"

status=0
forbidden_patterns=(
  'Cyrene-Platform\.git'
  'cyrene[_-]artifacts'
  'cy[_-]artifacts'
  'CYRENE_PLATFORM'
  'platform_artifacts'
  'PlatformArtifactPlane'
  'ArtifactKind\.(DATASET|MODEL|CHECKPOINT|TRAINING_SPEC|METRICS|MERGED|QUANTIZED|REPORT)'
)
for pattern in "${forbidden_patterns[@]}"; do
  matches=$(git grep -n -E "$pattern" -- . ':(exclude)tooling/ci/check-boundary.sh' 2>/dev/null || true)
  if [ -n "$matches" ]; then
    echo "FORBIDDEN Echo/Platform coupling or closed artifact taxonomy: $pattern"
    echo "$matches" | sed 's/^/  - /'
    status=1
  fi
done

if ! python3 - <<'PY'
import json
from pathlib import Path

artifact_path = Path("contracts/product/v1/generated/platform/artifact-ref.schema.json")
artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
kind = artifact["properties"]["kind"]
assert kind.get("type") == "string"
assert kind.get("minLength") == 1
assert kind.get("maxLength") == 128
assert "enum" not in kind

closed = []
def walk(value: object, path: str) -> None:
    if isinstance(value, dict):
        properties = value.get("properties")
        required = value.get("required")
        if (
            isinstance(properties, dict)
            and isinstance(required, list)
            and "kind" in required
            and isinstance(properties.get("kind"), dict)
            and "enum" in properties["kind"]
        ):
            closed.append(f"{path}.properties.kind")
        for key, child in value.items():
            walk(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            walk(child, f"{path}[{index}]")

for path in sorted(Path("contracts").rglob("*.json")):
    walk(json.loads(path.read_text(encoding="utf-8")), str(path))
assert not closed, f"closed ArtifactRef kind taxonomy: {closed}"
PY
then
  echo "FORBIDDEN: ArtifactRef kind must remain an opaque producer-owned string"
  status=1
fi

pipeline_external_checkout=$(
  git grep -n -E '^[[:space:]]*(resources:|checkout:)' -- azure-pipelines.yml 2>/dev/null \
    | grep -Ev 'checkout:[[:space:]]*self([[:space:]]|$)' || true
)
if [ -n "$pipeline_external_checkout" ]; then
  echo "FORBIDDEN: Azure pipeline must checkout only Echo and use local boundary checks"
  echo "$pipeline_external_checkout" | sed 's/^/  - /'
  status=1
fi

if [ "$status" -eq 0 ]; then
  echo "OK: Echo has no Platform source/runtime coupling and ArtifactRef kind is open."
fi
exit "$status"
