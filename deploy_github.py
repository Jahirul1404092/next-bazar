# -*- coding: utf-8 -*-
"""
GitHub Deployment Helper for Next Bazar.

Sets up the GitHub repository and pushes the project for the first time.
After this, GitHub Actions handles everything automatically.

Usage:
    python deploy_github.py --repo YOUR_GITHUB_USERNAME/bajar-price-prediction
    python deploy_github.py --repo jahirul/bajar-price-prediction

Prerequisites:
    - git installed
    - GitHub CLI (gh) installed and authenticated: https://cli.github.com/
    - OR: create the repo manually on github.com and provide the URL

Author: Jahirul (2026)
"""

import os
import sys
import subprocess
import argparse
from pathlib import Path

PROJECT_DIR = Path(__file__).parent


def run(cmd, desc="", check=True):
    """Run a shell command."""
    if desc:
        print(f"\n>> {desc}")
    print(f"   $ {cmd}")
    result = subprocess.run(cmd, shell=True, cwd=PROJECT_DIR, capture_output=True, text=True)
    if result.stdout.strip():
        print(result.stdout.strip())
    if result.stderr.strip():
        print(result.stderr.strip())
    if check and result.returncode != 0:
        print(f"   FAILED (exit code {result.returncode})")
        return False
    return True


def main():
    parser = argparse.ArgumentParser(description="Deploy Next Bazar to GitHub Pages")
    parser.add_argument("--repo", type=str, required=True,
                        help="GitHub repo name (e.g., 'username/bajar-price-prediction')")
    parser.add_argument("--private", action="store_true",
                        help="Make the repo private (GitHub Pages requires Pro for private repos)")
    args = parser.parse_args()

    repo_name = args.repo
    print("=" * 60)
    print("Next Bazar - GitHub Deployment")
    print("=" * 60)
    print(f"Repository: {repo_name}")
    print(f"Project:    {PROJECT_DIR}")
    print()

    # Step 1: Check if git is initialized
    if not (PROJECT_DIR / ".git").exists():
        print("Initializing git repository...")
        run("git init")
        run("git branch -M main")
    else:
        print("Git repository already initialized.")

    # Step 2: Check if gh CLI is available
    gh_available = run("gh --version", check=False)

    # Step 3: Create GitHub repo if gh is available
    if gh_available:
        visibility = "--private" if args.private else "--public"
        print(f"\nCreating GitHub repo: {repo_name}")
        run(f'gh repo create {repo_name} {visibility} --source=. --push --description "Bangladesh Commodity Price Prediction Dashboard - ML-powered daily predictions from TCB data"',
            desc="Creating repo and pushing", check=False)
    else:
        print("\nGitHub CLI (gh) not found. Please:")
        print(f"  1. Create repo manually: https://github.com/new")
        print(f"  2. Name it: {repo_name.split('/')[-1]}")
        print(f"  3. Run these commands:")
        print(f"     git remote add origin https://github.com/{repo_name}.git")
        print(f"     git push -u origin main")
        return

    # Step 4: Add all files and push
    run("git add -A", desc="Staging all files")
    run('git commit -m "Initial commit: Next Bazar Price Prediction Dashboard"',
        desc="Creating initial commit", check=False)
    run("git push -u origin main", desc="Pushing to GitHub")

    # Step 5: Enable GitHub Pages
    if gh_available:
        # Enable Pages from gh-pages branch (will be created by the workflow)
        print("\nNote: GitHub Pages will be activated automatically after the")
        print("first workflow run creates the gh-pages branch.")
        print()

    # Step 6: Trigger first workflow run
    if gh_available:
        print("Triggering first deployment workflow...")
        run(f"gh workflow run daily_update.yml", desc="Triggering workflow", check=False)

    # Summary
    print()
    print("=" * 60)
    print("DEPLOYMENT SETUP COMPLETE!")
    print("=" * 60)
    print()
    print(f"  Repository:   https://github.com/{repo_name}")
    print(f"  Dashboard:    https://{repo_name.split('/')[0]}.github.io/{repo_name.split('/')[-1]}/")
    print()
    print("  What happens next:")
    print("  1. GitHub Actions workflow runs (scrape + train + deploy)")
    print("  2. Creates gh-pages branch with dashboard files")
    print("  3. GitHub Pages serves your dashboard publicly")
    print()
    print("  After first run, go to:")
    print(f"  Settings > Pages > Source: Deploy from 'gh-pages' branch")
    print()
    print("  The workflow runs automatically every day at 9 AM BDT.")
    print("  You can also trigger it manually from the Actions tab.")


if __name__ == "__main__":
    main()
