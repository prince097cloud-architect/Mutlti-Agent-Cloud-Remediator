"""
LLM-based classifier agent to determine the resource type from a Jira intent.

This agent uses an LLM to analyze the intent JSON and identify which AWS resource type
is being remediated. This approach scales to any number of resource types without
hardcoding patterns.
"""

import json
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from app.utils.config import OPENAI_API_KEY
from app.utils.logger import get_logger
from app.config.prompt_templates import list_supported_resources

logger = get_logger("classifier-agent", "classifier.log")

# Lightweight LLM for fast classification
classifier_llm = ChatOpenAI(
    api_key=OPENAI_API_KEY,
    temperature=0,
    model="gpt-4o-mini",  # Fast and cheap for classification
)

CLASSIFIER_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        """
You are a cloud infrastructure classification expert.

Your task: Analyze a Jira intent describing a cloud compliance issue and identify the PRIMARY AWS resource type being remediated.

Available resource types:
{supported_resources}

INSTRUCTIONS:
1. Read the intent carefully (violation description, affected resources, issues, required actions).
2. Identify the PRIMARY AWS resource type (e.g., s3, ec2, kms, rds, lambda, vpc, iam, etc.).
3. Return ONLY the resource type as a single lowercase word.
4. If the resource type is not in the supported list or unclear, return "generic".

EXAMPLES:
- Intent mentions "S3 buckets", "encryption", "public access" → return: s3
- Intent mentions "EC2 instances", "IMDSv2", "metadata" → return: ec2
- Intent mentions "KMS keys", "key rotation" → return: kms
- Intent mentions "RDS databases", "backup retention" → return: rds
- Intent mentions "Lambda functions", "runtime" → return: lambda
- Intent is unclear or mixed resources → return: generic

OUTPUT FORMAT:
Return ONLY the resource type string, nothing else.
"""
    ),
    ("human", "Intent JSON:\n{intent}\n\nResource type:")
])


def classify_resource_type(intent: dict) -> str:
    """
    Classify the AWS resource type from the intent using an LLM.
    
    Args:
        intent: The parsed Jira intent JSON
    
    Returns:
        Resource type string (e.g., 's3', 'ec2', 'kms', 'rds', 'generic')
    """
    from app.utils.coordination_logger import tracker
    
    logger.info("Starting resource type classification")
    tracker.log_agent_call("Classifier Agent", "classify_resource_type", {
        "intent_summary": intent.get('Violation/Issue description', 'N/A')[:100],
        "affected_resources": intent.get('Affected resources', {}),
        "operation": "Determine AWS resource type from intent"
    })
    
    try:
        # Get list of supported resource types
        supported = list_supported_resources()
        supported_str = ", ".join(supported)
        logger.info(f"Supported resource types: {supported_str}")
        
        # Extract key fields from intent for logging
        violation = intent.get("Violation Detected") or intent.get("Violation") or intent.get("summary", "N/A")
        logger.info(f"Analyzing intent - Violation: {violation[:100]}...")
        
        # Invoke LLM classifier
        logger.debug("Invoking LLM classifier (gpt-4o-mini)")
        response = (CLASSIFIER_PROMPT | classifier_llm).invoke({
            "intent": json.dumps(intent, indent=2),
            "supported_resources": supported_str
        })
        
        # Extract resource type from response
        resource_type = response.content.strip().lower()
        logger.info(f"LLM classifier returned: '{resource_type}'")
        
        # Validate it's a known type
        if resource_type not in supported:
            # LLM returned something unexpected, default to first supported type
            logger.warning(f"LLM returned unexpected resource type '{resource_type}', defaulting to '{supported[0]}'")
            return supported[0]
        
        logger.info(f"Classification successful: {resource_type}")
        
        # Log classifier decision
        tracker.log_classifier_decision(intent, resource_type)
        
        return resource_type
        
    except Exception as e:
        # If classification fails, default to first supported type
        supported = list_supported_resources()
        default_type = supported[0] if supported else "s3"
        logger.error(f"Classification error: {e}", exc_info=True)
        logger.info(f"Defaulting to '{default_type}' resource type due to error")
        
        tracker.log_classifier_decision(intent, default_type)
        return default_type


def get_resource_type_from_intent(intent: dict) -> tuple[str, float]:
    """
    Get resource type with confidence score.
    
    Args:
        intent: The parsed Jira intent JSON
    
    Returns:
        Tuple of (resource_type, confidence_score)
    """
    resource_type = classify_resource_type(intent)
    
    # LLM-based classification has high confidence when specific, lower when generic
    confidence = 0.95 if resource_type != "generic" else 0.6
    
    logger.info(f"Final classification: {resource_type} (confidence: {confidence})")
    return resource_type, confidence
