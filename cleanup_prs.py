#!/usr/bin/env python3
"""
Script to close all open PRs and delete their branches in the Test-Multigent-infra repo.
"""
import os
from github import Github
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

if not GITHUB_TOKEN:
    print("Error: GITHUB_TOKEN not found in environment variables")
    exit(1)

# Initialize GitHub client
g = Github(GITHUB_TOKEN)

# Get the repository
repo_name = "prince097cloud-architect/Test-Multigent-infra"
repo = g.get_repo(repo_name)

print(f"Fetching open PRs from {repo_name}...")

# Get all open pull requests
open_prs = repo.get_pulls(state='open')

pr_count = 0
for pr in open_prs:
    pr_count += 1
    print(f"\nPR #{pr.number}: {pr.title}")
    print(f"  Branch: {pr.head.ref}")
    
    # Close the PR
    pr.edit(state='closed')
    print(f"  ✓ Closed PR #{pr.number}")
    
    # Delete the branch (only if it's not the default branch)
    if pr.head.ref != repo.default_branch:
        try:
            ref = repo.get_git_ref(f"heads/{pr.head.ref}")
            ref.delete()
            print(f"  ✓ Deleted branch: {pr.head.ref}")
        except Exception as e:
            print(f"  ✗ Could not delete branch {pr.head.ref}: {e}")
    else:
        print(f"  ⚠ Skipped deleting default branch: {pr.head.ref}")

print(f"\n{'='*50}")
print(f"Summary: Closed {pr_count} PR(s) and deleted their branches")
print(f"{'='*50}")
