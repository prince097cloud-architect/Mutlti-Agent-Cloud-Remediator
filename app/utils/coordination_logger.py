#!/usr/bin/env python3
"""
Agent Coordination Logger for Multi-Agent Cloud Remediator

This logger provides detailed visibility into:
1. How agents coordinate via LangGraph
2. State transitions between agents
3. Decision points and data flow
4. Agent-specific operations
"""

import json
import logging
import time
from datetime import datetime
from typing import Dict, Any, Optional

# Configure dedicated logger for agent coordination
coordination_logger = logging.getLogger("agent_coordination")
coordination_logger.setLevel(logging.INFO)

# Create file handler for coordination logs
coordination_handler = logging.FileHandler("logs/agent_coordination.log", mode='w')
coordination_handler.setLevel(logging.INFO)

# Create formatter
coordination_formatter = logging.Formatter(
    '%(asctime)s | %(levelname)s | %(name)s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
coordination_handler.setFormatter(coordination_formatter)
coordination_logger.addHandler(coordination_handler)

class AgentCoordinationTracker:
    """Tracks and logs agent coordination throughout the workflow."""
    
    def __init__(self):
        self.session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.start_time = None
        self.agent_calls = {}
        self.state_transitions = []
        
    def log_workflow_start(self, jira_id: str):
        """Log the start of the entire workflow."""
        self.start_time = time.time()
        coordination_logger.info("="*80)
        coordination_logger.info(f"WORKFLOW STARTED - Session: {self.session_id}")
        coordination_logger.info(f"Jira ID: {jira_id}")
        coordination_logger.info(f"Start Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        coordination_logger.info("="*80)
        
    def log_langgraph_node_start(self, node_name: str, input_state: Dict[str, Any]):
        """Log when a LangGraph node starts execution."""
        start_time = time.time()
        self.agent_calls[node_name] = {"start_time": start_time, "input_state": input_state}
        
        coordination_logger.info(f"\n{'='*60}")
        coordination_logger.info(f"LANGGRAPH NODE START: {node_name.upper()}")
        coordination_logger.info(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        coordination_logger.info(f"Input State Keys: {list(input_state.keys())}")
        
        if "jira_id" in input_state:
            coordination_logger.info(f"Jira ID: {input_state['jira_id']}")
        if "intent" in input_state:
            intent = input_state["intent"]
            coordination_logger.info(f"Intent Summary: {intent.get('Violation/Issue description', 'N/A')}")
            coordination_logger.info(f"Affected Resources: {intent.get('Affected resources', {})}")
        
        coordination_logger.info("-"*60)
        
    def log_langgraph_node_end(self, node_name: str, output_state: Dict[str, Any]):
        """Log when a LangGraph node completes execution."""
        if node_name in self.agent_calls:
            duration = time.time() - self.agent_calls[node_name]["start_time"]
            self.agent_calls[node_name]["duration"] = duration
            self.agent_calls[node_name]["output_state"] = output_state
        
        coordination_logger.info(f"\nLANGGRAPH NODE COMPLETE: {node_name.upper()}")
        coordination_logger.info(f"Duration: {duration:.2f}s")
        coordination_logger.info(f"Output State Keys: {list(output_state.keys())}")
        
        if "intent" in output_state:
            coordination_logger.info("✓ Intent successfully parsed and structured")
        if "pr_url" in output_state:
            coordination_logger.info(f"✓ PR Created: {output_state['pr_url']}")
        
        coordination_logger.info("-"*60)
        
    def log_agent_call(self, agent_name: str, operation: str, details: Dict[str, Any]):
        """Log specific agent operations within nodes."""
        coordination_logger.info(f"\n  🤖 AGENT CALL: {agent_name}")
        coordination_logger.info(f"  Operation: {operation}")
        coordination_logger.info(f"  Details: {json.dumps(details, indent=2)}")
        
    def log_state_transition(self, from_node: str, to_node: str, state: Dict[str, Any]):
        """Log state transitions between LangGraph nodes."""
        transition = {
            "from": from_node,
            "to": to_node,
            "timestamp": datetime.now().isoformat(),
            "state_keys": list(state.keys())
        }
        self.state_transitions.append(transition)
        
        coordination_logger.info(f"\n🔄 STATE TRANSITION")
        coordination_logger.info(f"  From: {from_node}")
        coordination_logger.info(f"  To: {to_node}")
        coordination_logger.info(f"  State Keys: {list(state.keys())}")
        
    def log_classifier_decision(self, intent: Dict[str, Any], resource_type: str):
        """Log the classifier agent decision making."""
        coordination_logger.info(f"\n  🎯 CLASSIFIER AGENT DECISION")
        coordination_logger.info(f"  Intent Summary: {intent.get('Violation/Issue description', 'N/A')[:100]}...")
        coordination_logger.info(f"  Determined Resource Type: '{resource_type}'")
        coordination_logger.info(f"  Reasoning: Based on intent content and compliance references")
        
    def log_prompt_template_selection(self, resource_type: str, template_info: Dict[str, Any]):
        """Log prompt template selection process."""
        coordination_logger.info(f"\n  📋 PROMPT TEMPLATE SELECTION")
        coordination_logger.info(f"  Resource Type: '{resource_type}'")
        coordination_logger.info(f"  Template Description: {template_info.get('description', 'N/A')}")
        coordination_logger.info(f"  System Message Length: {len(template_info.get('system', ''))} chars")
        
    def log_workflow_complete(self, final_state: Dict[str, Any]):
        """Log the completion of the entire workflow."""
        total_duration = time.time() - self.start_time if self.start_time else 0
        
        coordination_logger.info("\n" + "="*80)
        coordination_logger.info(f"WORKFLOW COMPLETED - Session: {self.session_id}")
        coordination_logger.info(f"Total Duration: {total_duration:.2f}s")
        coordination_logger.info(f"End Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        # Summary of agent calls
        coordination_logger.info("\n📊 AGENT EXECUTION SUMMARY:")
        for agent, details in self.agent_calls.items():
            duration = details.get("duration", 0)
            coordination_logger.info(f"  - {agent}: {duration:.2f}s")
        
        # Final state summary
        coordination_logger.info(f"\n🎯 FINAL RESULTS:")
        if "pr_url" in final_state:
            coordination_logger.info(f"  ✓ PR Created: {final_state['pr_url']}")
        else:
            coordination_logger.info(f"  ✗ No PR created")
            
        coordination_logger.info("="*80)

# Global tracker instance
tracker = AgentCoordinationTracker()

def log_graph_structure():
    """Log the LangGraph structure and flow."""
    coordination_logger.info("\n" + "="*80)
    coordination_logger.info("LANGGRAPH STRUCTURE ANALYSIS")
    coordination_logger.info("="*80)
    
    coordination_logger.info("""
🔄 WORKFLOW FLOW DIAGRAM:
┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│   START     │───▶│   JIRA      │───▶│   GITHUB    │
│             │    │   NODE      │    │   NODE      │
└─────────────┘    └─────────────┘    └─────────────┘
                          │                   │
                          ▼                   ▼
                   ┌─────────────┐    ┌─────────────┐
                   │ Jira Parser │    │ GitHub PR   │
                   │   Agent     │    │   Agent     │
                   └─────────────┘    └─────────────┘
                                            │
                                            ▼
                                    ┌─────────────┐
                                    │ Classifier  │
                                    │   Agent     │
                                    └─────────────┘

📝 AGENT RESPONSIBILITIES:
1. JIRA NODE → Jira Parser Agent:
   - Extracts structured intent from Jira ticket
   - Parses compliance requirements, affected resources, actions
   - Output: Structured intent JSON

2. GITHUB NODE → GitHub PR Agent (with Classifier):
   - Step 1: Classifier Agent determines resource type
   - Step 2: Selects appropriate prompt template
   - Step 3: GitHub PR Agent applies changes via LLM
   - Output: GitHub PR URL

🔄 STATE MANAGEMENT:
- State flows sequentially through nodes
- Each node receives full state and adds its output
- State keys: ['jira_id'] → ['jira_id', 'intent'] → ['jira_id', 'intent', 'pr_url']
""")

if __name__ == "__main__":
    log_graph_structure()
