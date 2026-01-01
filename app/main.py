from fastapi import FastAPI
from app.utils.logger import get_logger
from app.graph import app_graph
from app.utils.coordination_logger import tracker, log_graph_structure

# Import MCP servers
from app.mcp.jira_server import mcp as jira_mcp_server
from app.mcp.github_server import mcp as github_mcp_server

logger = get_logger(__name__, "api.log")

# ----------------------------
# FASTAPI APP
# ----------------------------
app = FastAPI(
    title="Multi-Agent Cloud Remediator",
    version="1.0.0",
)

# ----------------------------
# MCP SERVER MOUNTS
# ----------------------------
# TODO: Mount MCP servers using streamable_http_app
# app.mount("/jira-mcp", jira_mcp_server.streamable_http_app)
# app.mount("/github-mcp", github_mcp_server.streamable_http_app)

# ----------------------------
# HEALTH CHECK
# ----------------------------
@app.get("/health")
def health():
    logger.info("Health check called")
    return {"status": "ok"}

# ----------------------------
# OPTIONAL ROOT
# ----------------------------
@app.get("/")
def root():
    return {
        "service": "multi-agent-cloud-remediator",
        "mcp_endpoints": {
            "jira": "/jira-mcp/mcp",
            "github": "/github-mcp/mcp",
        },
    }

@app.post("/run/{jira_id}")
async def run(jira_id: str):
    logger.info(f"Workflow triggered for Jira ID: {jira_id}")
    
    # Initialize coordination tracking for this run
    tracker.log_workflow_start(jira_id)
    log_graph_structure()
    
    try:
        result = await app_graph.ainvoke({"jira_id": jira_id})
        tracker.log_workflow_complete(result)
        return result
    except Exception as e:
        logger.error(f"Error processing Jira ID {jira_id}: {str(e)}", exc_info=True)
        tracker.log_workflow_complete({"error": str(e)})
        raise