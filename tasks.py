"""Development tasks for QGIS MCP.

Run `invoke --list` to see them. Copy `invoke.example.yml` to `invoke.yml` to
change the QGIS version or the build platform.

Every task runs inside a container by default, so a laptop and CI run the same
QGIS. Set `local: true` in `invoke.yml`, or `INVOKE_QGIS_MCP_LOCAL=1`, to run on
this machine instead.
"""

import os
from pathlib import Path

from invoke import Collection, task

REPO_ROOT = Path(__file__).resolve().parent
COMPOSE_DIR = REPO_ROOT / "development"
CREDS = COMPOSE_DIR / "creds.env"

namespace = Collection("qgis_mcp")
namespace.configure(
    {
        "qgis_mcp": {
            "qgis_ver": "ltr",
            "platform": "linux/amd64",
            "local": False,
            "compose_dir": str(COMPOSE_DIR),
            "compose_files": [
                "docker-compose.base.yml",
                "docker-compose.dev.yml",
            ],
        }
    }
)


def is_truthy(value):
    """Return True when a configuration value means yes."""
    if isinstance(value, bool):
        return value
    return str(value).lower() in {"1", "true", "yes", "y", "on"}


def _ensure_creds():
    """Write development/creds.env from the example, when it is missing.

    A container cannot show a generated token in a dock, so both services read
    one from this file.
    """
    if CREDS.exists():
        return
    import secrets

    CREDS.write_text(f"QGIS_MCP_TOKEN={secrets.token_urlsafe(32)}\n")
    print(f"Wrote {CREDS} with a fresh token.")


def compose_command(context, command, service=""):
    """Return the docker compose command line for this configuration."""
    settings = context.qgis_mcp
    files = " ".join(f'-f "{Path(settings.compose_dir) / name}"' for name in settings.compose_files)
    return (
        f"QGIS_VER={settings.qgis_ver} "
        f"QGIS_PLATFORM={settings.platform} "
        f"DOCKER_DEFAULT_PLATFORM={settings.platform} "
        f"docker compose --project-name qgis-mcp --project-directory "
        f'"{settings.compose_dir}" {files} {command} {service}'
    )


def docker_compose(context, command, service="", **kwargs):
    """Run one docker compose command."""
    _ensure_creds()
    return context.run(compose_command(context, command, service), pty=True, **kwargs)


def run_command(context, command, service="qgis", **kwargs):
    """Run a command in a service, or on this machine when local is set."""
    if is_truthy(context.qgis_mcp.local) or is_truthy(os.environ.get("INVOKE_QGIS_MCP_LOCAL", "")):
        return context.run(command, pty=True, **kwargs)

    running = context.run(compose_command(context, "ps --services --filter status=running"), hide=True, warn=True)
    if service in (running.stdout or "").split():
        return docker_compose(context, f"exec {service}", f'sh -c "{command}"', **kwargs)
    return docker_compose(context, "run --rm --entrypoint=''", f'{service} sh -c "{command}"', **kwargs)


@task(help={"no_cache": "Build without the layer cache"})
def build(context, no_cache=False):
    """Build the container images."""
    options = "--no-cache" if no_cache else ""
    docker_compose(context, f"build {options}")


@task(help={"service": "Start one service only"})
def start(context, service=""):
    """Start the stack in the background."""
    docker_compose(context, "up --detach", service)


@task(help={"service": "Stop one service only"})
def stop(context, service=""):
    """Stop the stack."""
    docker_compose(context, "down --remove-orphans" if not service else "stop", service)


@task
def restart(context):
    """Stop the stack, then start it."""
    stop(context)
    start(context)


@task(help={"volumes": "Remove the volumes as well"})
def destroy(context, volumes=True):
    """Remove the containers, and the volumes by default."""
    docker_compose(context, f"down --remove-orphans {'--volumes' if volumes else ''}")


@task
def debug(context):
    """Run the stack in the foreground, with the logs attached."""
    docker_compose(context, "up")


@task(help={"service": "Follow one service", "follow": "Keep following"})
def logs(context, service="", follow=False):
    """Show the container logs."""
    docker_compose(context, f"logs {'--follow' if follow else ''}", service)


@task
def ps(context):
    """List the containers."""
    docker_compose(context, "ps")


@task(help={"service": "The service to open a shell in"})
def cli(context, service="qgis"):
    """Open a shell inside a service."""
    docker_compose(context, "run --rm --entrypoint=''", f"{service} bash")


@task
def unittest(context):
    """Run the unit suite. It needs no QGIS."""
    run_command(context, "python3 -m pytest -q")


@task
def integration(context):
    """Run the QGIS suite, against a real QGIS."""
    run_command(context, "python3 -m pytest tests/integration -c tests/integration/pytest.ini -q")


@task(help={"fix": "Apply the fixes"})
def ruff(context, fix=False):
    """Lint and format."""
    run_command(context, f"ruff check {'--fix' if fix else ''} .")
    run_command(context, f"ruff format {'' if fix else '--check'} .")


@task
def pylint(context):
    """Run the static analysis."""
    run_command(context, "pylint src/qgis_mcp/")


@task
def mypy(context):
    """Check the types."""
    run_command(context, "mypy src/qgis_mcp/")


@task
def docs(context):
    """Build the documentation site, the way CI does."""
    run_command(context, "mkdocs build --strict")


@task
def lock(context):
    """Regenerate poetry.lock."""
    run_command(context, "poetry lock")


@task
def tests(context):
    """Run every check: lint, types, both suites, and the docs."""
    ruff(context)
    pylint(context)
    mypy(context)
    unittest(context)
    integration(context)
    print("All checks passed.")


for item in (
    build,
    start,
    stop,
    restart,
    destroy,
    debug,
    logs,
    ps,
    cli,
    unittest,
    integration,
    ruff,
    pylint,
    mypy,
    docs,
    lock,
    tests,
):
    namespace.add_task(item)
