import os
from pathlib import Path
from dotenv import load_dotenv

# Always load .env from project root, regardless of where this module is imported from
PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = PROJECT_ROOT / ".env"
load_dotenv(dotenv_path=ENV_FILE)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

JIRA_BASE_URL = os.getenv("JIRA_BASE_URL")
JIRA_EMAIL = os.getenv("JIRA_EMAIL")
JIRA_API_TOKEN = os.getenv("JIRA_API_TOKEN")

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")


JIRA_MCP_URL = os.getenv("JIRA_MCP_URL")
GITHUB_MCP_URL = os.getenv("GITHUB_MCP_URL")

