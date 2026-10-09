#!/bin/sh
set -eu

: "${FRONTEND_BASE_URL:?FRONTEND_BASE_URL is required}"
FRONTEND_BASE_URL=${FRONTEND_BASE_URL%/}
case "$FRONTEND_BASE_URL" in
    http://*|https://*) ;;
    *) echo "FRONTEND_BASE_URL must start with http:// or https://" >&2; exit 1 ;;
esac
# This variable is a public origin, not HTML or a URL containing a query.
case "$FRONTEND_BASE_URL" in
    *[!a-zA-Z0-9:/._~-]*) echo "Invalid FRONTEND_BASE_URL origin" >&2; exit 1 ;;
esac
export FRONTEND_BASE_URL

find /opt/frontend-templates -type f | while IFS= read -r template; do
    destination="/usr/share/nginx/html/${template#/opt/frontend-templates/}"
    mkdir -p "$(dirname "$destination")"
    envsubst '${FRONTEND_BASE_URL}' < "$template" > "$destination"
done
