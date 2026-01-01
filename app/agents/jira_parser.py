import asyncio
import os
import json
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_mcp_adapters.tools import load_mcp_tools

from app.utils.logger import get_logger
from app.utils.config import OPENAI_API_KEY

logger = get_logger("jira-parser-agent", "jira_parser_agent.log")

llm = ChatOpenAI(
    api_key=OPENAI_API_KEY,
    temperature=0,
)

PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        """
You are a Jira Extraction Agent.

Extract ALL explicit information from the Jira ticket into a structured JSON object.
Preserve ALL fields, values, and details exactly as they appear in the ticket.

CRITICAL REQUIREMENTS:
1. Extract EVERY field mentioned in the summary and description
2. Preserve exact field names and values
3. If you find a GitHub repository URL or link, ALSO include it as "repo" field
4. Do NOT omit any information
5. Do NOT summarize or condense
6. Return valid JSON only

FIELDS TO LOOK FOR (extract all that exist):
- Violation/Issue description
- AWS Account, Region, Environment
- Version information (current, target)
- Terraform workspace
- Repository/GitHub link (extract as "repo" field)
- Affected resources (buckets, instances, databases, keys, etc.)
- Issues identified
- Required actions
- Compliance references
- Automation requirements
- Approval requirements
- Any other fields present in the ticket

OUTPUT FORMAT:
Return a JSON object with ALL extracted fields.
"""
    ),
    (
        "human",
        """
Jira Summary:
{summary}

Jira Description:
{description}
"""
    )
])

PROJECT_ROOT = Path(__file__).resolve().parents[2]
JIRA_MCP_PATH = PROJECT_ROOT / "app" / "mcp" / "jira_server.py"


async def parse_jira(jira_id: str) -> dict:
    logger.info(f"Parsing Jira ID {jira_id}")

    env = os.environ.copy()
    env["PYTHONPATH"] = str(PROJECT_ROOT)

    server_params = StdioServerParameters(
        command=sys.executable,
        args=[str(JIRA_MCP_PATH)],
        env=env,
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await load_mcp_tools(session)

            jira_tool = next(t for t in tools if t.name == "get_jira_issue")
            issue_result = await jira_tool.ainvoke({"jira_id": jira_id})

            if isinstance(issue_result, list) and issue_result:
                raw = issue_result[0]
                if isinstance(raw, dict) and "text" in raw:
                    issue_data = json.loads(raw["text"])
                else:
                    issue_data = raw
            elif isinstance(issue_result, dict):
                issue_data = issue_result
            else:
                raise ValueError(f"Unexpected Jira MCP output: {type(issue_result)}")

            issue = {
                "summary": issue_data.get("summary", ""),
                "description": (
                    json.dumps(issue_data.get("description"))
                    if isinstance(issue_data.get("description"), dict)
                    else str(issue_data.get("description", ""))
                ),
            }

    result = (PROMPT | llm).invoke(issue)

    try:
        raw = result.content.strip()

        if not raw:
            raise ValueError("LLM returned empty response")

        if raw.startswith("```"):
            raw = raw.strip("`")
            raw = raw.replace("json", "", 1).strip()

        intent = json.loads(raw)
        logger.info(f"Parsed intent: {intent}")

        # =====================================================
        # 🔧 ONLY CHANGE MADE (INLINE REPO NORMALIZATION)
        # =====================================================
        description = intent.get("description")
        if not isinstance(description, dict):
            description = {}

        repo = (
            intent.get("repo")
            or description.get("repo")
            or description.get("Repository")
            or description.get("Repository link")
            or intent.get("Repository")
            or intent.get("Repository link")
            or intent.get("Github Link")
            or intent.get("GitHub Link")
        )

        if isinstance(repo, str):
            repo = repo.strip()

        if repo and isinstance(repo, str) and repo.startswith("http"):
            repo = repo.split("github.com/")[-1].replace(".git", "").strip("/")

        if not repo or not isinstance(repo, str):
            raise ValueError(
                "Missing required GitHub repository in parsed intent. "
                "Expected `repo` (owner/repo or GitHub URL)."
            )

        intent["repo"] = repo

        branch = intent.get("branch")
        if not branch or not isinstance(branch, str):
            intent["branch"] = f"remediate-{jira_id.strip().lower()}"
        # =====================================================

        output_dir = PROJECT_ROOT / "output"
        output_dir.mkdir(exist_ok=True)
        output_file = output_dir / f"parsed_intent_{jira_id}.json"

        with open(output_file, "w") as f:
            json.dump(intent, f, indent=2)

        logger.info(f"Saved parsed intent to {output_file}")
        return intent

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON from LLM response: {repr(result.content)}")
        raise ValueError(f"LLM did not return valid JSON: {e}")
