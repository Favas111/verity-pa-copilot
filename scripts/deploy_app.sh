#!/usr/bin/env bash
# Deploy the Verity console to Streamlit in Snowflake.
#
# Deliberately does NOT use `snow streamlit deploy`. That command uploads to
# versioned storage (snow://streamlit/.../versions/live/) and on this account
# every app deployed that way dies at load with:
#
#     Python Interpreter Error: TypeError: bad argument type for built-in operation
#
# Proven not to be application code: a two-line, pure-ASCII app failed the same
# way through the CLI, and succeeded immediately through ROOT_LOCATION. The same
# fault also surfaced as the CLI's `'live_version_location_uri'` error.
#
# So: PUT the file to a plain internal stage and point ROOT_LOCATION at it.
#
# Usage: ./scripts/deploy_app.sh [connection]

set -euo pipefail

CONN="${1:-hackathon}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "Deploying app/streamlit_app.py -> VERITY.APP.VERITY_CONSOLE"

snow sql -c "$CONN" -q "
PUT 'file://${ROOT}/app/streamlit_app.py' @VERITY.APP.STREAMLIT_STAGE/console
    AUTO_COMPRESS=FALSE OVERWRITE=TRUE;

CREATE OR REPLACE STREAMLIT VERITY.APP.VERITY_CONSOLE
  ROOT_LOCATION   = '@VERITY.APP.STREAMLIT_STAGE/console'
  MAIN_FILE       = 'streamlit_app.py'
  QUERY_WAREHOUSE = COMPUTE_WH
  TITLE           = 'Verity — PA Evidence Console';
" | grep -E "UPLOADED|successfully|Error" || true

echo
# CREATE OR REPLACE mints a new object identity, which silently orphans any
# access grant made to a teammate's role on the old one. Re-share every time.
snow streamlit share VERITY.APP.VERITY_CONSOLE VERITY_CLINICAL_REVIEWER -c "$CONN" \
    | grep -E "successfully|Error" || true

echo "Open it from Snowsight: Projects -> Streamlit -> VERITY_CONSOLE"
echo "or run: snow streamlit get-url verity_console -c $CONN"
echo "A real page load is the only verification that counts — EXECUTE STREAMLIT passes on builds that fail in the browser."
