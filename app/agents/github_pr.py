import os
import sys
import json
import subprocess
import re
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_mcp_adapters.tools import load_mcp_tools
from app.utils.logger import get_logger
from app.utils.config import OPENAI_API_KEY
from app.agents.classifier import classify_resource_type
from app.config.prompt_templates import get_prompt_template

logger = get_logger("github-agent", "github_agent.log")

llm = ChatOpenAI(
    api_key=OPENAI_API_KEY,
    temperature=0,
)

# Dynamic prompt - will be set based on resource type classification
# This is just a placeholder, actual prompt is created in create_pr function
CODE_PROMPT = None

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
GITHUB_MCP_PATH = PROJECT_ROOT / "app" / "mcp" / "github_server.py"

def _extract_affected_resources(intent: dict) -> list:
    """Extract affected resources from intent in a generic way."""
    # Try various common field names for affected resources
    possible_fields = [
        "Affected Buckets", "affected_buckets",
        "Affected Resources", "affected_resources",
        "Affected Instances", "affected_instances",
        "Affected Keys", "affected_keys",
        "Affected Databases", "affected_databases",
    ]
    
    for field in possible_fields:
        resources = intent.get(field)
        if resources:
            if isinstance(resources, list):
                return [r.strip() for r in resources if isinstance(r, str) and r.strip()]
            elif isinstance(resources, dict):
                # Handle nested structures like {"Buckets": [...]}
                for key, value in resources.items():
                    if isinstance(value, list):
                        return [r.strip() for r in value if isinstance(r, str) and r.strip()]
    
    return []

async def create_pr(intent: dict) -> str:
    logger.info("="*80)
    logger.info("GitHub PR Agent Started")
    logger.info("="*80)
    
    # Log the full intent received
    logger.info("INTENT RECEIVED FROM JIRA PARSER:")
    logger.info(json.dumps(intent, indent=2))
    logger.info("-"*80)
    
    # Classify resource type to select appropriate prompt
    logger.info("STEP 1: RESOURCE TYPE CLASSIFICATION")
    logger.info(f"Sending intent to classifier agent...")
    resource_type = classify_resource_type(intent)
    logger.info(f"✓ Classifier returned resource type: '{resource_type}'")
    logger.info("-"*80)
    
    # Get resource-specific prompt template
    logger.info("STEP 2: PROMPT TEMPLATE SELECTION")
    logger.info(f"Fetching prompt template for resource type: '{resource_type}'")
    prompt_template = get_prompt_template(resource_type)
    logger.info(f"✓ Selected prompt template key: '{resource_type}'")
    logger.info(f"✓ Prompt template description: {prompt_template['description']}")
    logger.info(f"✓ Prompt template system message (first 300 chars):")
    logger.info(f"   {prompt_template['system'][:300]}...")
    logger.info("-"*80)
    
    # Log prompt template selection
    from app.utils.coordination_logger import tracker
    tracker.log_prompt_template_selection(resource_type, prompt_template)
    
    # Create dynamic prompt based on resource type
    code_prompt = ChatPromptTemplate.from_messages([
        ("system", prompt_template["system"]),
        ("human", "{context}")
    ])

    # Set PYTHONPATH to project root so subprocess can import app modules
    # The subprocess will load .env file fresh when it imports config.py
    env = os.environ.copy()
    env['PYTHONPATH'] = str(PROJECT_ROOT)
    # Don't override env vars - let subprocess load them from .env file
    
    server_params = StdioServerParameters(
        command=sys.executable,
        args=[str(GITHUB_MCP_PATH)],
        env=env,
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await load_mcp_tools(session)
            tool_map = {t.name: t for t in tools}

            repo = intent.get("repo")
            if not repo or not isinstance(repo, str):
                raise ValueError(
                    "Missing required `repo` in intent before cloning. "
                    "Expected `owner/repo` or a GitHub URL."
                )

            branch = intent.get("branch")
            jira_id = intent.get("jira_id", "unknown")
            
            # Create readable branch name with date-time format: YYYY-MM-DD-HHMMSS-JIRA-ID
            from datetime import datetime
            timestamp = datetime.now().strftime("%Y-%m-%d-%H%M%S")
            branch = f"{timestamp}-{jira_id.upper()}"
            intent["branch"] = branch

            # Extract affected resources from intent (generic, not S3-specific)
            logger.info("STEP 3: EXTRACTING AFFECTED RESOURCES FROM INTENT")
            affected_resources = _extract_affected_resources(intent)
            logger.info(f"✓ Extracted {len(affected_resources)} affected resource(s): {affected_resources}")
            logger.info("-"*80)

            # 1️⃣ Clone repo
            clone_result = await tool_map["clone_repo"].ainvoke({
                "repo": repo
            })

            if isinstance(clone_result, list) and clone_result:
                raw = clone_result[0]
                if isinstance(raw, dict) and "text" in raw:
                    repo_path = raw["text"]
                else:
                    repo_path = raw
            else:
                repo_path = clone_result

            if not isinstance(repo_path, (str, bytes, os.PathLike)):
                raise TypeError(
                    f"Unexpected clone_repo output type: {type(repo_path)}. "
                    "Expected path-like string."
                )

            # 2️⃣ Checkout branch early so all changes land on it
            await tool_map["create_branch"].ainvoke({
                "repo_path": repo_path,
                "branch": branch,
            })

            # 3️⃣ Scan repo (local filesystem)
            terraform_files = []
            terragrunt_files = []
            for root, _, files in os.walk(repo_path):
                for f in files:
                    if f.endswith(".tf") or f.endswith(".tfvars"):
                        terraform_files.append(os.path.join(root, f))
                    if f == "terragrunt.hcl" or f.endswith(".hcl"):
                        terragrunt_files.append(os.path.join(root, f))

            if not terraform_files and not terragrunt_files:
                raise ValueError(
                    "No Terraform/Terragrunt files were found in the target repository after cloning. "
                    "Expected to find at least one of: *.tf, *.tfvars, terragrunt.hcl."
                )

            # If repo is module-based, try to discover local module sources from root-level TF.
            module_source_dirs: list[str] = []
            discovered_module_sources: list[str] = []
            root_tf_files = [p for p in terraform_files if os.path.dirname(p) == str(repo_path)]
            module_block_re = re.compile(r'module\s+"(?P<name>[^"]+)"\s*\{(?P<body>.*?)\}', re.DOTALL)
            source_re = re.compile(r'source\s*=\s*"(?P<source>[^"]+)"')
            for abs_path in root_tf_files:
                try:
                    with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
                        content = f.read()
                    for m in module_block_re.finditer(content):
                        body = m.group("body")
                        sm = source_re.search(body)
                        if not sm:
                            continue
                        source = sm.group("source").strip()
                        discovered_module_sources.append(source)

                        # Normalize common local-module patterns.
                        # Examples:
                        # - ./modules/s3/v1/v1.0.0
                        # - modules/s3/v1/v1.0.0
                        # - ${path.module}/modules/s3/v1/v1.0.0
                        normalized_source = source
                        normalized_source = normalized_source.replace("${path.module}", ".")
                        normalized_source = normalized_source.replace("${path.root}", ".")
                        normalized_source = normalized_source.strip()

                        if (
                            normalized_source.startswith("./")
                            or normalized_source.startswith("../")
                            or normalized_source.startswith("modules/")
                        ):
                            module_dir = os.path.normpath(os.path.join(str(repo_path), normalized_source))
                            if os.path.isdir(module_dir) and module_dir not in module_source_dirs:
                                module_source_dirs.append(module_dir)
                except OSError:
                    continue

            # Match files containing affected resource names
            matched_files: list[str] = []
            for abs_path in terraform_files:
                try:
                    with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
                        content = f.read()
                    if any(resource in content for resource in affected_resources):
                        matched_files.append(abs_path)
                except OSError:
                    continue

            # Match files related to the classified resource type (generic)
            resource_related_files: list[str] = []
            # Use resource_type to find relevant files (e.g., "s3", "ec2", "kms")
            resource_markers = [resource_type, f"aws_{resource_type}"]
            for abs_path in (terraform_files + terragrunt_files):
                try:
                    with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
                        content = f.read()
                    if any(marker in content.lower() for marker in resource_markers):
                        resource_related_files.append(abs_path)
                except OSError:
                    continue

            module_files: list[str] = []
            for module_dir in module_source_dirs:
                for root, _, files in os.walk(module_dir):
                    for f in files:
                        if f.endswith(".tf") or f.endswith(".tfvars"):
                            module_files.append(os.path.join(root, f))

            # Fallback: if repo has a modules/ directory at root, scan it directly
            # BUT only scan subdirectories matching the classified resource type
            modules_dir_at_root = os.path.join(str(repo_path), "modules")
            if os.path.isdir(modules_dir_at_root) and not module_files:
                # Only scan modules matching the resource type (e.g., modules/s3/ for S3)
                resource_specific_module = os.path.join(modules_dir_at_root, resource_type)
                if os.path.isdir(resource_specific_module):
                    for root, _, files in os.walk(resource_specific_module):
                        for f in files:
                            if f.endswith(".tf") or f.endswith(".tfvars"):
                                module_files.append(os.path.join(root, f))
                else:
                    # If no resource-specific module dir, scan all (fallback to old behavior)
                    for root, _, files in os.walk(modules_dir_at_root):
                        for f in files:
                            if f.endswith(".tf") or f.endswith(".tfvars"):
                                module_files.append(os.path.join(root, f))

            if affected_resources and not matched_files and not resource_related_files and not module_files:
                raise ValueError(
                    f"None of the affected {resource_type} resources were found in Terraform code, and no {resource_type}-related Terraform "
                    "resources/modules were detected in this repository. "
                    f"Scanned {len(terraform_files)} Terraform files and {len(terragrunt_files)} Terragrunt/HCL files. "
                    f"Discovered module sources in root: {discovered_module_sources}. "
                    f"This likely means the {resource_type} resources are not managed by this Terraform repo/workspace (or resource names are "
                    "fully dynamic and not represented anywhere). Proceed with manual remediation or update the intent "
                    "with the correct repository/workspace."
                )

            # Select candidate files based on matching priority (generic logic)
            candidate_files: list[str] = []
            if matched_files:
                # Priority 1: Files containing affected resource names
                candidate_files.extend(matched_files)
                matched_dirs = {os.path.dirname(p) for p in matched_files}
                for abs_path in terraform_files:
                    if os.path.dirname(abs_path) in matched_dirs and abs_path not in candidate_files:
                        candidate_files.append(abs_path)
            elif affected_resources and resource_related_files:
                # Priority 2: Files related to resource type
                candidate_files = resource_related_files
            elif module_files:
                # Priority 3: Module files + root files
                candidate_files = module_files
                # Add root-level .tf files (main.tf, terraform.tf, etc.)
                for abs_path in terraform_files:
                    if os.path.dirname(abs_path) == str(repo_path) and abs_path not in candidate_files:
                        candidate_files.append(abs_path)
            else:
                # Priority 4: All terraform files
                candidate_files = terraform_files
            
            logger.info(f"Candidate files for analysis: {len(candidate_files)} files")
            if not candidate_files:
                raise ValueError(
                    "No Terraform files found to analyze. "
                    f"Scanned {len(terraform_files)} Terraform files, "
                    f"found {len(resource_related_files)} {resource_type}-related files, "
                    f"found {len(module_files)} module files."
                )

            max_files = 50
            max_total_chars = 200_000
            terraform_file_contents: dict[str, str] = {}
            total_chars = 0
            for abs_path in candidate_files[:max_files]:
                try:
                    rel_path = os.path.relpath(abs_path, repo_path)
                    with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
                        content = f.read()
                    remaining = max_total_chars - total_chars
                    if remaining <= 0:
                        break
                    if len(content) > remaining:
                        content = content[:remaining]
                    terraform_file_contents[rel_path] = content
                    total_chars += len(content)
                except OSError:
                    continue

            # 4️⃣ Use LLM to generate full file content (new prompt template approach)
            logger.info("STEP 4: LLM GENERATION OF UPDATED FILE")
            logger.info(f"Invoking LLM with prompt template: '{resource_type}'")
            
            # Prepare context for LLM
            context = {
                "intent": intent,
                "affected_resources": affected_resources,
                "matched_terraform_files": [os.path.relpath(p, repo_path) for p in matched_files],
                "resource_related_files": [os.path.relpath(p, repo_path) for p in resource_related_files],
                "module_source_dirs": [os.path.relpath(p, repo_path) for p in module_source_dirs],
                "terraform_files": list(terraform_file_contents.keys()),
                "terraform_file_contents": terraform_file_contents,
            }
            logger.info("Context being sent to LLM:")
            logger.info(f"  - Intent fields: {list(intent.keys())}")
            logger.info(f"  - Affected resources: {affected_resources}")
            logger.info(f"  - Terraform files: {len(terraform_file_contents)} files")
            
            plan = (code_prompt | llm).invoke({
                "context": json.dumps(context, indent=2)
            })
            
            raw = plan.content.strip()
            logger.info(f"✓ LLM returned {len(raw)} chars")
            logger.info(f"LLM response preview: {raw[:200]}...")
            
            if raw.startswith("```"):
                raw = raw.strip("`")
                raw = raw.replace("json", "", 1).strip()
            
            try:
                changes = json.loads(raw)
            except json.JSONDecodeError as e:
                logger.error(f"LLM returned invalid JSON: {raw[:500]}")
                raise ValueError(f"LLM did not return valid JSON: {e}")

            files_obj = changes.get("files")
            if not isinstance(files_obj, dict):
                raise ValueError("LLM response missing required `files` object")
            
            logger.info(f"✓ LLM proposed changes to {len(files_obj)} file(s): {list(files_obj.keys())}")
            logger.info("-"*80)
            
            if not files_obj:
                raise ValueError(
                    "LLM returned empty files object. The LLM could not determine which Terraform files to modify. "
                    f"Intent summary: {intent.get('summary', 'N/A')}. "
                    f"Affected resources: {affected_resources}. "
                    "This may indicate the Terraform code structure doesn't match expected patterns, or the intent "
                    "description is too vague for the LLM to map to specific Terraform resources."
                )

            # 5️⃣ Apply changes with validation
            changed_files = []
            for rel_path, content in files_obj.items():
                if not isinstance(rel_path, str) or not isinstance(content, str):
                    raise ValueError("LLM `files` must map string paths to string file contents")
                
                full_path = os.path.join(repo_path, rel_path)
                
                # Validation: check if LLM removed content (for main.tf files)
                if os.path.exists(full_path) and rel_path in ["main.tf", "terraform.tf", "providers.tf"]:
                    with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                        original_content = f.read()
                    
                    # Check if original has multiple module blocks but new content doesn't
                    original_module_count = original_content.count("module \"")
                    new_module_count = content.count("module \"")
                    
                    # Check for other critical content
                    original_has_terraform_block = "terraform {" in original_content
                    new_has_terraform_block = "terraform {" in content
                    
                    original_has_variables = "variable \"" in original_content
                    new_has_variables = "variable \"" in content
                    
                    original_has_outputs = "output \"" in original_content
                    new_has_outputs = "output \"" in content
                    
                    original_has_resources = "resource \"" in original_content
                    new_has_resources = "resource \"" in content
                    
                    # Calculate content size ratio
                    size_ratio = len(content) / len(original_content) if len(original_content) > 0 else 0
                    
                    errors = []
                    if original_module_count > 1 and new_module_count < original_module_count:
                        errors.append(f"Removed {original_module_count - new_module_count} module block(s)")
                    
                    if original_has_terraform_block and not new_has_terraform_block:
                        errors.append("Removed terraform backend configuration")
                    
                    if original_has_variables and not new_has_variables:
                        errors.append("Removed variable definitions")
                    
                    if original_has_outputs and not new_has_outputs:
                        errors.append("Removed output definitions")
                    
                    if original_has_resources and not new_has_resources:
                        errors.append("Removed resource definitions")
                    
                    if size_ratio < 0.5:
                        errors.append(f"File size reduced by {int((1-size_ratio)*100)}% (likely truncated)")
                    
                    if errors:
                        logger.error(
                            f"LLM removed critical content from {rel_path}! Issues: {', '.join(errors)}"
                        )
                        raise ValueError(
                            f"LLM removed critical content from {rel_path}: {', '.join(errors)}. "
                            "The LLM was instructed to preserve all content but failed. "
                            "This indicates the LLM is not capable of handling full-file modifications reliably. "
                            "Rejecting changes to prevent data loss."
                        )
                
                dir_path = os.path.dirname(full_path)
                if dir_path:
                    os.makedirs(dir_path, exist_ok=True)
                with open(full_path, "w", encoding="utf-8") as f:
                    f.write(content)
                changed_files.append(full_path)
            
            # Validate Terraform syntax for changed .tf files
            for file_path in changed_files:
                if file_path.endswith(".tf"):
                    try:
                        result = subprocess.run(
                            ["terraform", "fmt", "-check", file_path],
                            cwd=repo_path,
                            capture_output=True,
                            text=True,
                            timeout=10
                        )
                        if result.returncode != 0:
                            logger.warning(f"Terraform fmt check failed for {file_path}: {result.stderr}")
                            # Try to auto-fix formatting
                            subprocess.run(
                                ["terraform", "fmt", file_path],
                                cwd=repo_path,
                                capture_output=True,
                                timeout=10
                            )
                    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
                        logger.warning(f"Could not validate Terraform syntax: {e}")

            # Refuse to create a PR if there are no actual diffs
            diff_names = subprocess.check_output(
                ["git", "-C", str(repo_path), "diff", "--name-only"],
                text=True,
            ).strip()
            if not diff_names:
                raise ValueError("No code changes were produced; refusing to open an empty PR.")

            pr_body = (
                "Automated remediation PR generated from Jira intent.\n\n"
                "Changed files:\n"
                f"{diff_names}\n\n"
                "Intent:\n"
                f"{json.dumps(intent, indent=2)}"
            )

            await tool_map["commit_changes"].ainvoke({
                "repo_path": repo_path,
                "message": "Automated fix from Jira intent",
            })

            await tool_map["push_branch"].ainvoke({
                "repo_path": repo_path,
                "branch": branch,
            })

            pr_url = await tool_map["create_pull_request"].ainvoke({
                "repo": intent["repo"],
                "branch": branch,
                "title": "Automated remediation",
                "body": pr_body,
            })

    logger.info(f"PR created: {pr_url}")
    return pr_url   
