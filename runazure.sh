#!/usr/bin/env bash
# Deploy source code to the managed Azure App Service Python runtime.
set -euo pipefail

PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if [[ "${1:-}" == '--help' || "${1:-}" == '-h' ]]; then
    cat <<'HELP'
Usage: ./runazure.sh [--deploy-only]

Installs Azure CLI locally if needed, opens browser sign-in when necessary, deploys Python
source to App Service, waits for HTTPS, and opens the URL. No Docker is required.
Azure resources incur subscription charges.

  --deploy-only  Upload to an existing configured app; skip resource/config setup.

Optional environment variables:
  AZURE_SUBSCRIPTION        Optional override; otherwise discovered after login.
  AZURE_RESOURCE_GROUP      Default: pytest-auditor-rg
  AZURE_LOCATION            Default: westeurope
  AZURE_APP_NAME            Optional globally unique name (otherwise generated).
  AZURE_APP_SERVICE_PLAN    Default: pytest-auditor-plan
  AZURE_APP_SERVICE_SKU     Default: B1 (billable); F1 for limited free testing
  AZURE_NONINTERACTIVE=1    Fail instead of prompting for an initial Azure login.
  AZURE_MANAGED_IDENTITY=1  Sign in with a managed identity on an Azure host.
  AZURE_OPEN_BROWSER=0      Print the URL without opening a browser (for CI).

No Azure IDs or deployment settings are required: sign in in the browser.
The launcher discovers your enabled subscriptions and uses the Azure default
or the only available subscription. Multiple subscriptions without a default
require one selection. Subsequent runs reuse your login. Fully unattended
runs require an existing authenticated session or a configured managed identity.
Use Upload from laptop or GitHub sources in the hosted web UI.
HELP
    exit 0
fi
DEPLOY_ONLY=false
if [[ "${1:-}" == '--deploy-only' ]]; then
    DEPLOY_ONLY=true
    shift
fi
[[ $# -eq 0 ]] || { printf 'Usage: ./runazure.sh [--deploy-only]\n' >&2; exit 2; }
fail() { printf 'Error: %s\n' "$*" >&2; exit 1; }
command -v curl >/dev/null 2>&1 || fail 'curl is required for the deployment readiness check.'
command -v python3 >/dev/null 2>&1 || fail 'python3 is required to package the source deployment.'
export UV_CACHE_DIR="${UV_CACHE_DIR:-$PROJECT_DIR/.cache/uv}"
export PIP_CACHE_DIR="${PIP_CACHE_DIR:-$PROJECT_DIR/.cache/pip}"

# Keep Azure tooling isolated from the application's local runtime.
CLI_DIR="$PROJECT_DIR/.azure-cli"
install_azure_cli() {
    if command -v uv >/dev/null 2>&1; then
        # Azure CLI SDK dependencies include prereleases.
        uv pip install --python "$CLI_DIR/bin/python" --upgrade --prerelease=allow 'azure-cli>=2.61'
    else
        "$CLI_DIR/bin/python" -m ensurepip --upgrade
        "$CLI_DIR/bin/python" -m pip install --upgrade 'azure-cli>=2.61'
    fi
}
if command -v az >/dev/null 2>&1; then
    AZ=(az)
    if [[ "$(command -v az)" == "$CLI_DIR/bin/az" ]]; then
        AZ=("$CLI_DIR/bin/python" -m azure.cli)
    fi
elif [[ -x "$CLI_DIR/bin/python" ]]; then
    AZ=("$CLI_DIR/bin/python" -m azure.cli)
else
    [[ ! -e "$CLI_DIR" ]] || fail 'The local Azure CLI environment is incomplete; recreate .azure-cli.'
    printf 'Preparing Azure CLI…\n'
    if command -v uv >/dev/null 2>&1; then
        uv venv --python python3 "$CLI_DIR"
    else
        python3 -m venv "$CLI_DIR"
    fi
    AZ=("$CLI_DIR/bin/python" -m azure.cli)
fi

# Run the local CLI module with its interpreter; its shell wrapper may require
# a global "python" command. Repair missing or outdated CLI installations.
if [[ "${AZ[0]}" == "$CLI_DIR/bin/python" ]]; then
    [[ -x "$CLI_DIR/bin/python" ]] || fail 'The local Azure CLI environment is incomplete; recreate .azure-cli.'
    if ! "$CLI_DIR/bin/python" -c 'from importlib.metadata import version; import sys; sys.exit(0 if tuple(map(int, version("azure-cli").split(".")[:2])) >= (2, 61) else 1)' 2>/dev/null; then
        printf 'Installing a supported Azure CLI…\n'
        install_azure_cli
    fi
fi

# Token validation also detects missing login; no separate account probe needed.
if ! "${AZ[@]}" account get-access-token --output none 2>/dev/null; then
    if [[ "${AZURE_MANAGED_IDENTITY:-0}" == 1 ]]; then
        "${AZ[@]}" login --identity --output none
    elif [[ "${AZURE_NONINTERACTIVE:-0}" == 1 ]]; then
        fail 'No Azure login found. Authenticate with az login before an unattended deployment.'
    else
        printf 'Opening Azure sign-in in your browser. Complete login/MFA there; deployment will continue automatically.\n'
        AZURE_CORE_LOGIN_EXPERIENCE_V2=off "${AZ[@]}" login --output none
    fi
fi
# Discover subscription metadata through Azure CLI after Microsoft finishes login.
# Passwords and browser cookies stay with Microsoft/Azure CLI, never this script.
if [[ -n "${AZURE_SUBSCRIPTION:-}" ]]; then
    "${AZ[@]}" account set --subscription "$AZURE_SUBSCRIPTION"
else
    SUBSCRIPTIONS="$("${AZ[@]}" account list --refresh \
        --query "[?state=='Enabled'].[id, name, isDefault]" --output tsv)"
    SUBSCRIPTION_IDS=()
    SUBSCRIPTION_NAMES=()
    DEFAULT_SUBSCRIPTION=""
    while IFS=$'\t' read -r subscription_id subscription_name is_default; do
        [[ -n "$subscription_id" ]] || continue
        SUBSCRIPTION_IDS+=("$subscription_id")
        SUBSCRIPTION_NAMES+=("$subscription_name")
        case "$is_default" in
            true|True) DEFAULT_SUBSCRIPTION="$subscription_id" ;;
        esac
    done <<< "$SUBSCRIPTIONS"
    [[ ${#SUBSCRIPTION_IDS[@]} -gt 0 ]] || fail 'Login succeeded, but no enabled Azure subscription was found. Activate a subscription in Azure and rerun.'
    if [[ -n "$DEFAULT_SUBSCRIPTION" ]]; then
        SELECTED_SUBSCRIPTION="$DEFAULT_SUBSCRIPTION"
    elif [[ ${#SUBSCRIPTION_IDS[@]} -eq 1 ]]; then
        SELECTED_SUBSCRIPTION="${SUBSCRIPTION_IDS[0]}"
    else
        [[ "${AZURE_NONINTERACTIVE:-0}" != 1 ]] || fail 'Multiple subscriptions were found without a default. Select one with az account set, then rerun.'
        [[ -t 0 ]] || fail 'Multiple subscriptions were found without a default. Run in a terminal to select one, or use az account set.'
        printf 'Choose the subscription to deploy into:\n'
        for index in "${!SUBSCRIPTION_IDS[@]}"; do
            printf '  %s) %s\n' "$((index + 1))" "${SUBSCRIPTION_NAMES[$index]}"
        done
        while true; do
            read -r -p 'Subscription number: ' choice || fail 'Subscription selection was cancelled.'
            if [[ "$choice" =~ ^[1-9][0-9]*$ && ${#choice} -le 6 ]] &&
               (( choice <= ${#SUBSCRIPTION_IDS[@]} )); then
                SELECTED_SUBSCRIPTION="${SUBSCRIPTION_IDS[$((choice - 1))]}"
                break
            fi
            printf 'Enter a number from the list.\n'
        done
    fi
    "${AZ[@]}" account set --subscription "$SELECTED_SUBSCRIPTION"
fi
IFS=$'\t' read -r SUBSCRIPTION_ID SUBSCRIPTION_NAME < <(
    "${AZ[@]}" account show --query '[[id, name]]' --output tsv)
[[ -n "$SUBSCRIPTION_ID" && -n "$SUBSCRIPTION_NAME" ]] || fail 'Azure did not return subscription details.'
printf 'Using Azure subscription: %s\n' "$SUBSCRIPTION_NAME"

RESOURCE_GROUP="${AZURE_RESOURCE_GROUP:-pytest-auditor-rg}"
LOCATION="${AZURE_LOCATION:-westeurope}"
NAME_SUFFIX="$(printf '%s' "$SUBSCRIPTION_ID:$RESOURCE_GROUP" | cksum | awk '{print $1}')"
APP_NAME="${AZURE_APP_NAME:-pytest-auditor-$NAME_SUFFIX}"
PLAN_NAME="${AZURE_APP_SERVICE_PLAN:-pytest-auditor-plan}"
PLAN_SKU="${AZURE_APP_SERVICE_SKU:-B1}"
if ! "$DEPLOY_ONLY"; then
    # Reuse an existing deployment's region instead of asking for location details.
    GROUP_EXISTS=false
    if existing_location="$("${AZ[@]}" group show --name "$RESOURCE_GROUP" --query location --output tsv 2>/dev/null)"; then
        GROUP_EXISTS=true
        if [[ -z "${AZURE_LOCATION:-}" && -n "$existing_location" && "$existing_location" != null ]]; then
            LOCATION="$existing_location"
        fi
    fi

    # Retry regional admission/quota failures, preserving explicit location choices.
    create_in_eligible_region() {
        local region output attempted=" "
        local regions=("$LOCATION")
        if [[ -z "${AZURE_LOCATION:-}" ]]; then
            regions+=(northeurope francecentral germanywestcentral swedencentral)
        fi
        for region in "${regions[@]}"; do
            [[ "$attempted" != *" $region "* ]] || continue
            attempted+="$region "
            printf 'Trying %s in %s…\n' "$1" "$region"
            if output="$("${AZ[@]}" "$@" --location "$region" 2>&1)"; then
                [[ -z "$output" ]] || printf '%s\n' "$output"
                LOCATION="$region"
                return 0
            fi
            case "$output" in
                *locationineligible*|*'selected region is currently not accepting new customers'*)
                    printf 'Azure rejected region %s; checking the next region.\n' "$region" ;;
                *'Operation cannot be completed without additional quota'*)
                    if [[ -n "${AZURE_LOCATION:-}" ]]; then
                        printf '%s\n' "$output" >&2
                        return 1
                    fi
                    printf 'Azure has insufficient %s quota in %s; checking the next region.\n' "$PLAN_SKU" "$region" ;;
                *) printf '%s\n' "$output" >&2; return 1 ;;
            esac
        done
        fail 'No region with available App Service quota was found. Request quota in Azure or choose a subscription-supported AZURE_LOCATION.'
    }

    printf 'Checking App Service provider…\n'
    state="$("${AZ[@]}" provider show --namespace Microsoft.Web --query registrationState --output tsv)"
    if [[ "$state" != Registered ]]; then
        "${AZ[@]}" provider register --namespace Microsoft.Web --wait --output none
    fi
    if ! "$GROUP_EXISTS"; then
        "${AZ[@]}" group create --name "$RESOURCE_GROUP" --location "$LOCATION" --output none
    fi
fi

# Package an allowlist of sources, never tooling, credentials, or local projects.
BUILD_DIR="$(mktemp -d "${TMPDIR:-/tmp}/pytest-auditor-azure.XXXXXX")"
trap 'rm -rf -- "$BUILD_DIR"' EXIT
PACKAGE="$BUILD_DIR/app.zip"
python3 - "$PROJECT_DIR" "$PACKAGE" <<'PACKAGE_PY'
from pathlib import Path
import sys
from zipfile import ZipFile, ZIP_DEFLATED
root = Path(sys.argv[1])
files = [root / name for name in (
    'requirements.txt', '__main__.py', '__init__.py', 'web_server.py', 'web_sources.py')]
for name in ('core', 'scanning', 'reporting', 'web'):
    files.extend(path for path in (root / name).rglob('*')
                 if path.is_file() and '__pycache__' not in path.parts
                 and path.suffix not in {'.pyc', '.pyo'})
with ZipFile(sys.argv[2], 'w', ZIP_DEFLATED) as archive:
    for path in files:
        archive.write(path, path.relative_to(root))
PACKAGE_PY

if ! "$DEPLOY_ONLY"; then
    printf 'Preparing Linux App Service plan %s (creation tier: %s)…\n' "$PLAN_NAME" "$PLAN_SKU"
    if ! "${AZ[@]}" appservice plan show --name "$PLAN_NAME" --resource-group "$RESOURCE_GROUP" --output none 2>/dev/null; then
        create_in_eligible_region appservice plan create --name "$PLAN_NAME" --resource-group "$RESOURCE_GROUP" \
            --is-linux --sku "$PLAN_SKU" --number-of-workers 1 --output none
    fi
    # Always On requires a paid tier. Read the actual plan SKU on reruns because
    # an existing plan can differ from the requested creation tier.
    ACTUAL_PLAN_SKU="$("${AZ[@]}" appservice plan show --name "$PLAN_NAME" --resource-group "$RESOURCE_GROUP" --query sku.name --output tsv)"
    printf 'Using App Service plan %s (%s).\n' "$PLAN_NAME" "$ACTUAL_PLAN_SKU"
    ALWAYS_ON=true
    case "${ACTUAL_PLAN_SKU^^}" in F1|D1) ALWAYS_ON=false ;; esac
    if ! "${AZ[@]}" webapp show --name "$APP_NAME" --resource-group "$RESOURCE_GROUP" --output none 2>/dev/null; then
        "${AZ[@]}" webapp create --name "$APP_NAME" --resource-group "$RESOURCE_GROUP" \
            --plan "$PLAN_NAME" --runtime "PYTHON:3.12" --output none
    fi
    printf 'Configuring Python runtime, startup command, and HTTPS…\n'
    # Setting linuxFxVersion also migrates an existing container app to managed Python.
    "${AZ[@]}" webapp config set --name "$APP_NAME" --resource-group "$RESOURCE_GROUP" \
        --linux-fx-version 'PYTHON|3.12' \
        --startup-file 'python web_server.py --host 0.0.0.0 --port 8000' \
        --always-on "$ALWAYS_ON" --output none
    # Remove incompatible settings left by previous container/package deployments.
    "${AZ[@]}" webapp config appsettings delete --name "$APP_NAME" --resource-group "$RESOURCE_GROUP" \
        --setting-names WEBSITES_PORT WEBSITES_CONTAINER_START_TIME_LIMIT WEBSITES_RUN_FROM_PACKAGE \
        DOCKER_CUSTOM_IMAGE_NAME DOCKER_REGISTRY_SERVER_URL DOCKER_REGISTRY_SERVER_USERNAME DOCKER_REGISTRY_SERVER_PASSWORD --output none
    "${AZ[@]}" webapp config appsettings set --name "$APP_NAME" --resource-group "$RESOURCE_GROUP" \
        --settings SCM_DO_BUILD_DURING_DEPLOYMENT=true ENABLE_ORYX_BUILD=true --output none
    "${AZ[@]}" webapp update --name "$APP_NAME" --resource-group "$RESOURCE_GROUP" --https-only true --output none
    # Azure uses this logging option for managed Linux runtimes too.
    "${AZ[@]}" webapp log config --name "$APP_NAME" --resource-group "$RESOURCE_GROUP" \
        --docker-container-logging filesystem --output none
else
    # Do not silently create a new app when the user requested a source-only update.
    "${AZ[@]}" webapp show --name "$APP_NAME" --resource-group "$RESOURCE_GROUP" --output none ||
        fail 'Deploy-only requires an existing configured app. Run ./runazure.sh first.'
    printf 'Updating source only; keeping existing Azure configuration.\n'
fi
printf 'Uploading source ZIP and installing dependencies in Azure…\n'
if ! "${AZ[@]}" webapp deploy --name "$APP_NAME" --resource-group "$RESOURCE_GROUP" \
    --src-path "$PACKAGE" --type zip --restart true --enable-kudu-warmup false --timeout 1800000 --output none; then
    fail "Source deployment failed. Inspect: az webapp log deployment show --name $APP_NAME --resource-group $RESOURCE_GROUP"
fi
FQDN="$("${AZ[@]}" webapp show --name "$APP_NAME" --resource-group "$RESOURCE_GROUP" \
    --query defaultHostName --output tsv)"
[[ -n "$FQDN" && "$FQDN" != null ]] || fail 'Azure did not return an application hostname.'
[[ "$FQDN" =~ ^[a-zA-Z0-9][a-zA-Z0-9.-]+$ ]] || fail 'Azure returned an invalid application hostname.'
APP_URL="https://$FQDN"
printf 'Waiting for %s…\n' "$APP_URL"
READY=false
for attempt in {1..90}; do
    if response="$(curl --fail --silent --max-time 10 "$APP_URL/")" &&
       [[ "$response" == *'id="audit-form"'* ]]; then
        READY=true
        break
    fi
    printf 'Waiting for application startup (%s/90)…\n' "$attempt"
    sleep 5
done
"$READY" || fail "Deployment did not become reachable. Inspect: az webapp log tail --name $APP_NAME --resource-group $RESOURCE_GROUP"
printf 'Application URL: %s\n' "$APP_URL"

# Opening a URL is best-effort on desktop hosts; CI can explicitly disable it.
if [[ "${AZURE_OPEN_BROWSER:-1}" == 1 ]]; then
    if command -v xdg-open >/dev/null 2>&1; then
        xdg-open "$APP_URL" >/dev/null 2>&1 || printf 'Browser opening failed; use the URL above.\n'
    elif command -v open >/dev/null 2>&1; then
        open "$APP_URL" || printf 'Browser opening failed; use the URL above.\n'
    elif command -v cmd.exe >/dev/null 2>&1; then
        cmd.exe /c start "" "$APP_URL" >/dev/null 2>&1 || printf 'Browser opening failed; use the URL above.\n'
    else
        printf 'No desktop URL opener was found; use the URL above.\n'
    fi
fi
