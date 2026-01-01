import logging
from app.utils.logger import get_logger
from app.agents.jira_parser import parse_jira
from app.agents.github_pr import create_pr
from app.utils.coordination_logger import tracker, log_graph_structure
from langgraph.graph import StateGraph

logger = get_logger("langgraph", "langgraph.log")

from typing import TypedDict

class State(TypedDict):
    jira_id: str
    intent: dict
    pr_url: str

async def jira_node(state: State):
    """Jira node: Extracts structured intent from Jira ticket."""
    tracker.log_langgraph_node_start("jira", state)
    
    tracker.log_agent_call("Jira Parser Agent", "parse_jira_ticket", {
        "jira_id": state["jira_id"],
        "operation": "Extract structured intent from Jira"
    })
    
    intent = await parse_jira(state["jira_id"])
    
    result = {"intent": intent}
    tracker.log_langgraph_node_end("jira", result)
    tracker.log_state_transition("start", "github", {**state, **result})
    
    return result

async def github_node(state: State):
    """GitHub node: Orchestrates classifier and PR creation."""
    tracker.log_langgraph_node_start("github", state)
    
    # The GitHub PR agent internally calls the classifier agent
    tracker.log_agent_call("GitHub PR Agent", "create_pr_with_classification", {
        "intent_keys": list(state["intent"].keys()),
        "operation": "Classify resource type and generate PR"
    })
    
    pr_url = await create_pr(state["intent"])
    
    result = {"pr_url": pr_url}
    tracker.log_langgraph_node_end("github", result)
    tracker.log_state_transition("github", "end", {**state, **result})
    
    return result

graph = StateGraph(State)
graph.add_node("jira", jira_node)
graph.add_node("github", github_node)

graph.set_entry_point("jira")
graph.add_edge("jira", "github")
graph.set_finish_point("github")

app_graph = graph.compile()
