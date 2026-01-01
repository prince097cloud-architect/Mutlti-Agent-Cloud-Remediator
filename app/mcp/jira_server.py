import requests
from mcp.server.fastmcp import FastMCP
from app.utils.logger import get_logger
from app.utils.config import (
    JIRA_BASE_URL,
    JIRA_EMAIL,
    JIRA_API_TOKEN,
)

logger = get_logger("jira-mcp" , "jira_mcp.log")

mcp = FastMCP("Jira")

@mcp.tool()
def get_jira_issue(jira_id: str) -> dict:
    logger.info(f"Fetching Jira issue {jira_id}")

    url = f"{JIRA_BASE_URL}/rest/api/3/issue/{jira_id}"
    resp = requests.get(
        url,
        auth=(JIRA_EMAIL, JIRA_API_TOKEN),
        headers={"Accept": "application/json"},
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()

    return {
        "id": jira_id,
        "summary": data["fields"]["summary"],
        "description": data["fields"]["description"],
        "issuetype": data["fields"]["issuetype"]["name"],
    }

if __name__ == "__main__":
    mcp.run(transport="stdio")
