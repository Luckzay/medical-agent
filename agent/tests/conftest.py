import os

# Set required configuration before test modules import app.main.
os.environ["AGENT_INTERNAL_TOKEN"] = "test-only-agent-token"
