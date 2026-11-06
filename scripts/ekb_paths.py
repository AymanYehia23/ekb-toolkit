"""Resolve where the toolkit lives and where the knowledge base lives.

The toolkit and the knowledge base are deliberately different trees.

    TOOLKIT   prompts, scripts, schemas, config. Versioned, shared, upgraded
              by pulling this repository.
    WORKSPACE profile, projects, context, applications, artifacts, index.
              Yours. Private. Never travels with the toolkit.

Keeping them apart is the one structural decision that makes the toolkit
publishable at all: personal career data and reusable procedure sitting in the
same directory is what forces every "share my setup" question to become a
manual audit.

Resolution order for the workspace, first match wins:

    1. --workspace / --root on the command line (handled by each script)
    2. $EKB_WORKSPACE
    3. `workspace:` in config/toolkit.yaml, relative to the toolkit root
    4. <toolkit root>/workspace
"""

from __future__ import annotations

import os

TOOLKIT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_DIR = os.path.join(TOOLKIT_ROOT, "config")


def _from_config() -> str | None:
    path = os.path.join(CONFIG_DIR, "toolkit.yaml")
    if not os.path.isfile(path):
        return None
    try:
        import yaml
    except ImportError:
        return None
    try:
        with open(path, encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
    except Exception:
        return None
    value = (data.get("paths") or {}).get("workspace")
    if not value:
        return None
    value = os.path.expanduser(value)
    return value if os.path.isabs(value) else os.path.join(TOOLKIT_ROOT, value)


def workspace_root() -> str:
    """Absolute path to the knowledge base this run should read and write."""
    env = os.environ.get("EKB_WORKSPACE")
    if env:
        return os.path.abspath(os.path.expanduser(env))
    configured = _from_config()
    if configured:
        return os.path.abspath(configured)
    return os.path.join(TOOLKIT_ROOT, "workspace")


def config_path(name: str, workspace: str | None = None) -> str:
    """Resolve a config file, preferring a private workspace override.

    The toolkit ships safe, versioned defaults in ``config/``. A user may put
    a file with the same name in ``<workspace>/config/`` to keep personal
    writing preferences, calibration, and role vocabulary out of the public
    toolkit repository. ``workspace_root`` deliberately reads the shipped
    ``toolkit.yaml`` directly while locating the workspace, so this lookup
    cannot recurse.
    """
    if os.path.basename(name) != name:
        raise ValueError("config names must be filenames")
    private = os.path.join(workspace if workspace is not None else workspace_root(), "config", name)
    if os.path.isfile(private):
        return private
    return os.path.join(CONFIG_DIR, name)


def load_config(name: str, workspace: str | None = None) -> dict:
    """Read a YAML or JSON config file. Missing file returns an empty dict."""
    path = config_path(name, workspace)
    if not os.path.isfile(path):
        return {}
    with open(path, encoding="utf-8") as handle:
        if name.endswith(".json"):
            import json

            return json.load(handle) or {}
        import yaml

        return yaml.safe_load(handle) or {}


def evidence_policy(workspace: str) -> dict[str, set[str]]:
    """Read effective eligibility, with private keys overriding shipped keys."""
    import yaml

    settings = {}
    for path in (os.path.join(CONFIG_DIR, "toolkit.yaml"),
                 os.path.join(workspace, "config", "toolkit.yaml")):
        if not os.path.isfile(path):
            continue
        with open(path, encoding="utf-8") as handle:
            data = yaml.safe_load(handle)
        if data is None:
            data = {}
        if not isinstance(data, dict) or not isinstance(data.get("evidence", {}), dict):
            raise ValueError(f"{path}: evidence policy must be a mapping")
        settings.update(data.get("evidence", {}))

    boundaries = {
        "eligible_kinds": {"repo-verified", "user-stated"},
        "eligible_involvement": {"led", "implemented", "contributed"},
    }
    for key, allowed in boundaries.items():
        values = settings.get(key)
        if not isinstance(values, list) or any(
            not isinstance(value, str) or value not in allowed for value in values
        ):
            raise ValueError(f"evidence.{key} must be a list drawn from {sorted(allowed)}")
    return {key: set(settings[key]) for key in boundaries}


def project_evidence_eligible(record: dict, policy: dict[str, set[str]]) -> bool:
    return (
        record.get("resume_eligible") is not False
        and record.get("kind") in policy["eligible_kinds"]
        and record.get("involvement") in policy["eligible_involvement"]
    )
