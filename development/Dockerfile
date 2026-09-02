# The image both development services run on.
#
# It builds on the QGIS image so the container QGIS matches the one CI tests
# against. The MCP server and the plugin then share one image, and the two
# always agree on the protocol.
ARG QGIS_VER=ltr
FROM qgis/qgis:${QGIS_VER}

ENV PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    POETRY_VIRTUALENVS_CREATE=false

WORKDIR /work

# The venv shares the system site packages, so PyQGIS stays importable. pip
# installs the rest. Poetry is not used here: it insists on replacing the
# Debian packages that QGIS relies on, and those carry no uninstall metadata.
RUN python3 -m venv --system-site-packages /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir --upgrade pip

ENV PATH="/opt/venv/bin:${PATH}"

COPY . .

RUN /opt/venv/bin/pip install --no-cache-dir -e ".[dev,docs]"

CMD ["python3", "development/entrypoint_headless.py"]
