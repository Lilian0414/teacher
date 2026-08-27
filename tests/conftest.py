"""Suite-wide isolation from developer-local dotenv configuration."""

from companion.settings import Settings

# Process environment variables (including CI's explicit provider selection) still work.
# Only the implicit repository-local `.env` lookup is disabled for ordinary tests. Tests
# that exercise dotenv behavior opt in with ``Settings(_env_file=...)``.
Settings.model_config["env_file"] = None
