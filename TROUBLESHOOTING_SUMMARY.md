# Troubleshooting Journey Summary

## Initial Setup (The Beginning)

**Problem:** Setting up virtual environment and running the FastAPI application.

**Solution:**
- Used existing `venv` directory (already present)
- Installed dependencies from `requirements.txt` 
- Started FastAPI server with: `uvicorn app.main:app --reload --host 0.0.0.0 --port 8000`

**Status:** ✅ Server started successfully

---

## Issue #1: "Not Found" Errors (404)

**Problem:** Getting "Not Found" errors when accessing `/docs`, `/`, or any endpoint, even though server was running.

**Root Causes Found:**
1. Missing `__init__.py` files in Python packages (`app/`, `app/agents/`, `app/utils/`, `app/mcp/`)
2. Port conflict - old server process was still running on port 8000

**Solutions Applied:**
- Created `__init__.py` files in all package directories to make them proper Python packages
- Killed old uvicorn processes and restarted fresh server
- Changed to port 8001 temporarily to test, then back to 8000

**Status:** ✅ Fixed - Server now responding correctly

---

## Issue #2: Missing Import in main.py

**Problem:** Internal Server Error when making POST requests to `/run/{jira_id}`

**Root Cause:** The endpoint was using `app_graph` but it wasn't imported in `main.py`

**Solution:**
```python
# Added this import
from app.graph import app_graph
```

**Status:** ✅ Fixed

---

## Issue #3: MCP Server File Path Errors

**Problem:** Error: `cannot import name 'server' from 'app.mcp.jira_server'`

**Root Cause:** 
- `main.py` was trying to import `server` but the MCP files exported `mcp`
- Agent files referenced wrong file names: `jira_mcp_server.py` and `github_mcp_server.py` instead of `jira_server.py` and `github_server.py`

**Solutions Applied:**
1. Changed imports in `main.py`: `server` → `mcp`
2. Fixed file paths in `jira_parser.py`: `jira_mcp_server.py` → `jira_server.py`
3. Fixed file paths in `github_pr.py`: `github_mcp_server.py` → `github_server.py`

**Status:** ✅ Fixed

---

## Issue #4: MCP Server Transport Mode

**Problem:** MCP servers configured to run with `transport="http"` but agents were trying to connect via `stdio` (subprocess mode)

**Root Cause:** MCP servers need `transport="stdio"` when run as subprocesses via `stdio_client`

**Solution:**
- Changed `jira_server.py`: `mcp.run(transport="http")` → `mcp.run(transport="stdio")`
- Changed `github_server.py`: `mcp.run(transport="http")` → `mcp.run(transport="stdio")`

**Status:** ✅ Fixed

---

## Issue #5: PYTHONPATH and Environment Variables

**Problem:** MCP server subprocess couldn't import `app` modules (ModuleNotFoundError)

**Root Cause:** When Python runs a subprocess, it doesn't inherit PYTHONPATH, so subprocess couldn't find `app.utils.config` or other app modules

**Solution:**
- Added PYTHONPATH to subprocess environment in `jira_parser.py` and `github_pr.py`:
```python
env = os.environ.copy()
env['PYTHONPATH'] = str(PROJECT_ROOT)
server_params = StdioServerParameters(
    command="python",
    args=[str(JIRA_MCP_PATH)],
    env=env,
)
```

**Status:** ✅ Fixed

---

## Issue #6: JIRA_BASE_URL Configuration Error

**Problem:** 404 errors from Jira API: `https://prince2015akash.atlassian.net/wiki/rest/api/3/issue/KAN-1`

**Root Cause:** `.env` file had incorrect `JIRA_BASE_URL=https://prince2015akash.atlassian.net/wiki` (included `/wiki` which shouldn't be there)

**Correct URL format should be:**
- ✅ `https://prince2015akash.atlassian.net/rest/api/3/issue/KAN-1`
- ❌ `https://prince2015akash.atlassian.net/wiki/rest/api/3/issue/KAN-1`

**Solution:**
- Updated `.env` file: `JIRA_BASE_URL=https://prince2015akash.atlassian.net` (removed `/wiki` and `/browse`)
- Updated `config.py` to explicitly load `.env` from project root:
```python
PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = PROJECT_ROOT / ".env"
load_dotenv(dotenv_path=ENV_FILE)
```

**Status:** ✅ Fixed - Jira API calls now working

---

## Issue #7: MCP Tool Response Format (List vs Dict)

**Problem:** `TypeError: Expected mapping type as input to ChatPromptTemplate. Received <class 'list'>`

**Root Cause:** MCP tools return results in a list format: `[{'type': 'text', 'text': '{"json": "string"}'}]` instead of a direct dictionary

**Solution:**
- Added parsing logic in `jira_parser.py` to extract JSON from the list format:
```python
if isinstance(issue_result, list) and len(issue_result) > 0:
    if 'text' in issue_result[0]:
        issue_data = json.loads(issue_result[0]['text'])
        issue = {
            "summary": issue_data.get("summary", ""),
            "description": json.dumps(issue_data.get("description", "")) 
                           if isinstance(issue_data.get("description"), dict) 
                           else str(issue_data.get("description", ""))
        }
```

**Status:** ✅ Fixed

---

## Issue #8: LLM Response Format (JSON String)

**Problem:** LLM returns JSON as a string, but code expected a dict

**Root Cause:** LangChain LLM's `result.content` is a string containing JSON, not a parsed dict

**Solution:**
- Added JSON parsing in `jira_parser.py`:
```python
intent = json.loads(result.content)
```

**Status:** ✅ Fixed

---

## Issue #9: JSON Output File Creation

**Request:** User wanted to see the parsed JSON structure to understand what data is being extracted

**Solution:**
- Added code to save parsed intent to JSON file:
```python
output_dir = PROJECT_ROOT / "output"
output_dir.mkdir(exist_ok=True)
output_file = output_dir / f"parsed_intent_{jira_id}.json"
with open(output_file, 'w') as f:
    json.dump(intent, f, indent=2)
```

**Status:** ✅ Implemented - Files saved to `output/parsed_intent_{JIRA_ID}.json`

---

## Current Issue: Missing 'repo' Field in Intent

**Problem:** `KeyError: 'repo'` in `github_pr.py` at line 70

**Root Cause:** The parsed intent JSON structure doesn't match what the GitHub PR agent expects:
- GitHub agent expects: `intent["repo"]` and `intent["branch"]`
- Actual structure has: `description["Github Link"]` = `"https://github.com/prince097cloud-architect/Test-Multigent-infra.git"`

**Current Intent Structure:**
```json
{
  "summary": "...",
  "description": {
    "Github Link": "https://github.com/prince097cloud-architect/Test-Multigent-infra.git",
    ...
  }
}
```

**What GitHub Agent Needs:**
```python
intent["repo"]  # Should be: "prince097cloud-architect/Test-Multigent-infra"
intent["branch"]  # Missing - needs to be extracted or defaulted
```

**Status:** ⚠️ **PENDING** - Needs fix to extract repo from GitHub link or update prompt to extract it explicitly

---

## Key Learnings

1. **Python Package Structure:** Always need `__init__.py` files for proper package imports
2. **MCP Transport Modes:** Use `stdio` for subprocess execution, `http` for standalone servers
3. **Environment Variables:** Subprocesses need explicit PYTHONPATH configuration
4. **MCP Tool Responses:** Returns data in a nested list format with JSON strings
5. **LLM Responses:** Always JSON strings, need explicit parsing
6. **Configuration Files:** Always specify full path for `.env` loading to avoid path issues

---

## Files Modified

1. `app/main.py` - Added `app_graph` import, added error handling
2. `app/agents/jira_parser.py` - Fixed file paths, added PYTHONPATH, added MCP response parsing, added JSON parsing, added JSON file output
3. `app/agents/github_pr.py` - Fixed file paths, added PYTHONPATH
4. `app/mcp/jira_server.py` - Changed transport from `http` to `stdio`
5. `app/mcp/github_server.py` - Changed transport from `http` to `stdio`
6. `app/utils/config.py` - Added explicit `.env` file path loading
7. `app/__init__.py` - Created (new file)
8. `app/agents/__init__.py` - Created (new file)
9. `app/utils/__init__.py` - Created (new file)
10. `app/mcp/__init__.py` - Created (new file)
11. `.env` - Fixed `JIRA_BASE_URL` (removed `/wiki`)

---

## Current Status

✅ **Working:**
- FastAPI server running correctly
- MCP servers starting and connecting via stdio
- Jira API integration working
- Jira issue fetching and parsing working
- JSON extraction from LLM working
- Intent JSON files being saved to `output/` directory

⚠️ **Pending:**
- Extract `repo` and `branch` from intent structure for GitHub PR creation
- Need to either:
  - Update Jira parser prompt to extract these fields explicitly, OR
  - Post-process intent to extract repo from GitHub link and set default branch

---

## How to Monitor Progress

**View logs in real-time:**
```bash
# API logs
tail -f logs/api.log

# Jira parser logs
tail -f logs/jira_parser_agent.log

# GitHub agent logs  
tail -f logs/github_agent.log

# LangGraph workflow logs
tail -f logs/langgraph.log
```

**Check parsed intents:**
```bash
cat output/parsed_intent_KAN-1.json
```

**Test the API:**
```bash
curl -X POST http://localhost:8000/run/KAN-1
```

---

## Issue #9: GitHub PR Agent Hardcoded S3 Logic

**Date:** 2026-01-01

**Problem:** GitHub PR agent had extensive S3-specific hardcoding, making it non-generic and not scalable for other resource types.

**Root Causes Found:**
1. Hardcoded `affected_buckets` extraction
2. S3-specific file matching (`s3_related_files`, `s3_markers`)
3. Conditional branching `if resource_type == "s3"`
4. Generic error messages referencing S3 terms

**Solutions Applied:**
- Created generic `_extract_affected_resources()` function to handle any resource type
- Replaced S3-specific file matching with dynamic `resource_related_files` and `resource_markers`
- Removed conditional branching - unified LLM invocation for all resource types
- Updated all error messages to use dynamic `resource_type` references
- Added detailed logging to trace intent flow through each agent step

**Status:** ✅ Fixed - Agent is now fully intent-driven and generic

---

## Issue #10: KeyError 'generic' in Prompt Templates

**Date:** 2026-01-01

**Problem:** `KeyError: 'generic'` when accessing prompt templates after removing the generic fallback template.

**Root Causes Found:**
1. Classifier was defaulting to "generic" as fallback
2. `get_prompt_template()` was trying to access non-existent "generic" key
3. `list_supported_resources()` was filtering out "generic" but classifier still used it

**Solutions Applied:**
- Updated classifier to only return supported resource types (currently just "s3")
- Modified `get_prompt_template()` to raise clear `ValueError` for unsupported types
- Updated `list_supported_resources()` to return all available keys
- Removed all "generic" fallback logic from classifier

**Status:** ✅ Fixed - Classifier now only returns valid resource types

---

## Issue #11: LangChain Prompt Template Variable Errors

**Date:** 2026-01-01

**Problem:** LangChain interpreting curly braces in prompt templates as template variables instead of literal text.

**Root Causes Found:**
1. Unescaped `{` and `}` in JSON output format examples
2. Words like "changes" being interpreted as template variables
3. New prompt template had unescaped braces in JSON structure

**Solutions Applied:**
- Escaped all `{` → `{{` and `}` → `}}` in JSON examples
- Escaped specific words like "changes" → "{{changes}}" in text
- Applied to both old and new prompt templates

**Status:** ✅ Fixed - LangChain no longer interprets JSON as template variables

---

## Issue #12: LLM Creating Duplicate Keys in Terraform

**Date:** 2026-01-01

**Problem:** LLM was creating duplicate attribute keys in bucket objects instead of replacing existing values.

**Example Wrong Output:**
```
encrypted = false
encrypted = true
```

**Root Causes Found:**
1. LLM was adding new lines instead of replacing existing ones
2. Prompt instructions weren't explicit about replacement vs addition

**Solutions Applied:**
- Added explicit instruction: "REPLACE existing values, do not add new lines"
- Added clear examples showing wrong vs correct approach
- Emphasized "Each attribute key MUST appear EXACTLY ONCE per object"

**Status:** ✅ Fixed - LLM now properly replaces attribute values

---

## Issue #13: Bucket Name Mismatch Between Intent and Code

**Date:** 2026-01-01

**Problem:** Intent listed "cloudforge-artifacts-prod" but Terraform code had "cloudforge-artifacts-dev", causing LLM to skip versioning updates.

**Root Causes Found:**
1. Jira intent had incorrect bucket name
2. LLM couldn't find exact match, so didn't apply updates
3. Versioning was already partially correct, so no change made

**Solutions Applied:**
- Initially added NAME MATCHING RULES to handle prod/dev variations
- User corrected the bucket name in Jira intent from "prod" to "dev"
- Added explicit versioning requirement to intent ("Versioning is not enabled")

**Status:** ✅ Fixed - Bucket names now match exactly, versioning updates applied

---

## Issue #14: Missing Versioning in Intent

**Date:** 2026-01-01

**Problem:** LLM wasn't updating versioning because intent didn't explicitly mention versioning issues.

**Root Causes Found:**
1. Intent only mentioned encryption and public access issues
2. LLM strictly follows only explicitly mentioned attributes
3. Versioning requirement was implied but not stated

**Solutions Applied:**
- User updated intent to include: "Versioning is not enabled on S3 buckets"
- User added to required actions: "Enable Versioning on the impacted buckets"
- Demonstrated intent-driven architecture working correctly

**Status:** ✅ Fixed - Intent now explicitly states all three requirements

---

## Issue #15: Agent Coordination Visibility

**Date:** 2026-01-01

**Problem:** Lack of visibility into how agents coordinate via LangGraph and state flows between them.

**Root Causes Found:**
1. No centralized logging of agent orchestration
2. Unclear how classifier fits into GitHub PR agent workflow
3. Missing state transition tracking

**Solutions Applied:**
- Created comprehensive coordination logger (`app/utils/coordination_logger.py`)
- Added detailed logging to LangGraph nodes in `app/graph.py`
- Integrated tracking in `main.py` for workflow start/end
- Added classifier decision logging and prompt template selection logging
- Created workflow flow diagrams and performance tracking

**Status:** ✅ Fixed - Complete visibility into agent coordination via `logs/agent_coordination.log`

---

## Issue #16: Prompt Template Architecture Refactor

**Date:** 2026-01-01

**Problem:** User wanted to replace the entire S3 prompt template with a new one focused on root-level module remediation.

**Root Causes Found:**
1. Existing prompt was attribute-analysis only
2. User wanted full file generation approach
3. New template needed different JSON output format

**Solutions Applied:**
- Replaced entire S3 prompt template with user-provided version
- Updated GitHub PR agent to handle new `{"files": {"main.tf": "..."}}` format
- Reverted from hybrid approach back to full file content generation
- Escaped all curly braces in new template to prevent LangChain errors

**Status:** ✅ Fixed - New prompt template integrated and working

---

*Summary created on: 2025-12-31*
*Last updated: 2026-01-01*
*Total issues resolved: 16*
*Current issue: 0 (all resolved)*

