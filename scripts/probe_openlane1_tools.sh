#!/usr/bin/env bash
# OpenLane1 imajindaki Docker Hub build hedeflerini cozumler; JSON manifest uretir.
set -euo pipefail

IMAGE="${OPENLANE1_IMAGE:-efabless/openlane:ci2504-dev-amd64}"
PLATFORM="${OPENLANE1_PLATFORM:-linux/amd64}"
OUT="${1:-}"

declare -A CANDIDATES=(
  [klayout]="klayout"
  [replace]="replace"
  [opendp]="opendp"
  [route]="route"
  [cugr]="cugr"
  [drcu]="drcu"
  [opensta]="opensta sta"
  [yosys]="yosys"
  [antmicro_yosys]="yosys"
  [magic]="magic"
  [openroad_app]="openroad openroad_app"
  [padring]="padring"
  [netgen]="netgen"
  [vlogtoverilog]="vlogtoverilog"
  [openphysyn]="openphysyn"
  [cvc]="cvc"
)

declare -A PROBE_ARGV=(
  [klayout]="-v"
  [replace]="-version"
  [opendp]="-version"
  [route]="-version"
  [cugr]="-version"
  [drcu]="-version"
  [opensta]="-version"
  [yosys]="-V"
  [antmicro_yosys]="-V"
  [magic]="-version"
  [openroad_app]="-version"
  [padring]="-h"
  [netgen]="-version"
  [vlogtoverilog]="-h"
  [openphysyn]="-h"
  [cvc]="-h"
)

probe_in_container() {
  local hub_key="$1"
  local candidates="$2"
  docker run --rm --platform "$PLATFORM" "$IMAGE" bash -lc "
    set +e
    hub_key='$hub_key'
    candidates='$candidates'
    resolved=''
  for name in \$candidates; do
    if path=\$(command -v \"\$name\" 2>/dev/null); then
      resolved=\"\$path\"
      echo \"RESOLVED:\$path\"
      break
    fi
  done
  if [ -z \"\$resolved\" ]; then
    for name in \$candidates; do
      found=\$(find / -maxdepth 6 -type f -name \"\$name\" -perm -111 2>/dev/null | head -n 1)
      if [ -n \"\$found\" ]; then
        echo \"RESOLVED:\$found\"
        resolved=\"\$found\"
        break
      fi
    done
  fi
  if [ -z \"\$resolved\" ]; then
    echo 'RESOLVED:'
    exit 0
  fi
  bin=\$(basename \"\$resolved\")
  case \"\$hub_key\" in
    yosys|antmicro_yosys) probe_argv='-V' ;;
    magic|opensta|replace|opendp|route|cugr|drcu|netgen|openroad_app) probe_argv='-version' ;;
    klayout) probe_argv='-v' ;;
    *) probe_argv='-h' ;;
  esac
  echo \"PROBE:\$bin \$probe_argv\"
  \"\$resolved\" \$probe_argv >/dev/null 2>&1 || true
  "
}

json_escape() {
  python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))' <<<"$1"
}

entries=()
for hub_key in klayout replace opendp route cugr drcu opensta yosys antmicro_yosys magic openroad_app padring netgen vlogtoverilog openphysyn cvc; do
  echo "Probing $hub_key..." >&2
  output="$(probe_in_container "$hub_key" "${CANDIDATES[$hub_key]}")"
  resolved_line="$(printf '%s\n' "$output" | awk -F: '/^RESOLVED:/{print substr($0,10); exit}')"
  probe_line="$(printf '%s\n' "$output" | awk -F: '/^PROBE:/{print substr($0,7); exit}')"
  if [ -n "$resolved_line" ]; then
    bin_name="$(basename "$resolved_line")"
    enabled="true"
    probe_argv="${PROBE_ARGV[$hub_key]}"
    smoke_argv="$probe_argv"
    notes=""
    if [ "$hub_key" = "openroad_app" ] && [ "$bin_name" = "openroad" ]; then
      notes="Hub hedefi openroad_app; PATH uzerinde openroad."
    elif [ "$hub_key" = "opensta" ] && [ "$bin_name" = "sta" ]; then
      notes="Hub hedefi opensta; PATH uzerinde sta."
    elif [ "$hub_key" = "antmicro_yosys" ]; then
      notes="Antmicro Yosys dagitimi; binary adi yosys olabilir."
    fi
  else
    bin_name=""
    enabled="false"
    probe_argv="${PROBE_ARGV[$hub_key]}"
    smoke_argv="$probe_argv"
    notes="Imajda cozumlenemedi; probe devre disi."
  fi
  if [ -n "$bin_name" ]; then
  resolved_json="[\"$(printf '%s' "$bin_name" | sed 's/"/\\"/g')\"]"
  else
  resolved_json="[]"
  fi
  entries+=("$(cat <<EOF
    {
      "hub_key": "$hub_key",
      "label": "$hub_key",
      "resolved_bins": $resolved_json,
      "probe_argv": $(json_escape "$probe_argv"),
      "smoke_argv": $(json_escape "$smoke_argv"),
      "enabled": $enabled,
      "notes": $(json_escape "$notes")
    }
EOF
)")
done

manifest="$(printf '%s\n' "${entries[@]}" | paste -sd, -)"
json="{\"image\":\"$IMAGE\",\"platform\":\"$PLATFORM\",\"tools\":[${manifest//$'\n'/}]}"
if [ -n "$OUT" ]; then
  printf '%s\n' "$json" | python3 -m json.tool >"$OUT"
  echo "Wrote $OUT" >&2
else
  printf '%s\n' "$json" | python3 -m json.tool
fi
