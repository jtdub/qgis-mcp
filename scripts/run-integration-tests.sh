#!/usr/bin/env bash
# Run the QGIS integration tests.
#
# `invoke integration` is the newer way in. It builds a container whose QGIS
# matches CI, and runs the same suite there. This script stays for a local
# QGIS, and for a machine with no docker.
#
# With no argument the script looks for a local QGIS and uses its Python.
# Pass "docker" to run every layer inside the qgis/qgis container instead.
# A local macOS QGIS ships Python 3.9, which is too old for the MCP package,
# so the end to end layer only runs under docker.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMAGE="${QGIS_IMAGE:-qgis/qgis:ltr}"

run_in_docker() {
    docker run --rm \
        --platform "${QGIS_PLATFORM:-linux/amd64}" \
        -v "${REPO_ROOT}:/work" \
        -w /work \
        -e QT_QPA_PLATFORM=offscreen \
        "${IMAGE}" \
        bash -lc '
            set -euo pipefail
            python3 -m venv --system-site-packages /tmp/venv
            /tmp/venv/bin/pip install --quiet --upgrade pip
            /tmp/venv/bin/pip install --quiet pytest pytest-asyncio "mcp[cli]>=1.12,<2"
            /tmp/venv/bin/python -m pytest tests/integration -c tests/integration/pytest.ini "$@"
        ' bash "$@"
}

find_local_python() {
    for candidate in \
        /Applications/QGIS-LTR.app/Contents/MacOS/bin/python3 \
        /Applications/QGIS.app/Contents/MacOS/bin/python3 \
        "$(command -v python3 || true)"
    do
        if [ -x "${candidate}" ] && "${candidate}" -c "import qgis.core" >/dev/null 2>&1; then
            echo "${candidate}"
            return 0
        fi
    done
    return 1
}

if [ "${1:-}" = "docker" ]; then
    shift
    run_in_docker "$@"
    exit 0
fi

if ! PYTHON="$(find_local_python)"; then
    echo "No local Python can import qgis.core. Run: $0 docker" >&2
    exit 1
fi

echo "Using ${PYTHON}"
cd "${REPO_ROOT}"
exec "${PYTHON}" -m pytest tests/integration -c tests/integration/pytest.ini "$@"
