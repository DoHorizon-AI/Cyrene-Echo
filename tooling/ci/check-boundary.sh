#!/usr/bin/env bash
# Echo product boundary guard.
#
# Echo may use the pinned Platform Artifact SDK only inside its artifact
# adapter. It must not regain a Platform source checkout, environment bridge,
# or closed artifact taxonomy outside that adapter.
set -euo pipefail

repo_root="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$repo_root"

status=0
guard_path='tooling/ci/check-boundary.sh'

check_matches_outside() {
  local label=$1
  local pattern=$2
  local allowed_paths=$3
  local matches
  matches=$(git grep -n -i -E "$pattern" -- ":!$guard_path" 2>/dev/null \
    | grep -E -v "^(${allowed_paths}):" || true)
  if [ -n "$matches" ]; then
    echo "FORBIDDEN Echo boundary violation ($label):"
    echo "$matches" | sed 's/^/  - /'
    status=1
  fi
}

check_matches_outside 'Platform git/source checkout' 'Cyrene-Platform[.]git' \
  'pyproject[.]toml|uv[.]lock'
check_matches_outside 'Platform artifact SDK/package' 'cyrene-artifacts|cy_artifacts' \
  'pyproject[.]toml|uv[.]lock|src/cyrene_echo/engine[.]py'
check_matches_outside 'Platform environment bridge' 'CYRENE_PLATFORM' '^$'
check_matches_outside 'closed ArtifactKind code vocabulary' \
  'ArtifactKind[[:space:]]*(::|[.])|class[[:space:]]+ArtifactKind|enum[[:space:]]+ArtifactKind' \
  'src/cyrene_echo/engine[.]py'

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
  echo "OK: Echo limits the Platform Artifact SDK to its adapter and keeps ArtifactRef kind open."
fi
exit "$status"
