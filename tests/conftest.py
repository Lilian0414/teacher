"""Suite-wide safeguards for deterministic test configuration."""

from companion.settings import Settings

# A developer's repository-local UAT profile must never become an implicit test
# input. Individual settings tests can still opt in with ``_env_file=...``.
Settings.model_config["env_file"] = None
