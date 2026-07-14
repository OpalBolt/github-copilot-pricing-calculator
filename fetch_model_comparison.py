#!/usr/bin/env python3
"""
fetch_model_comparison.py

Scrapes the GitHub Copilot AI model comparison page and outputs a JSON
summary of task areas, primary use cases, and task-based model recommendations.

Usage:
    python fetch_model_comparison.py              # fetch + write model_comparison.json

This module's functions are importable by generate_html.py for orchestration.

Requires: Python 3.8+ (stdlib only — urllib, re, json)
"""

import argparse
import json
import re
import urllib.request
from datetime import date
from pathlib import Path

API_URL = (
    "https://docs.github.com/api/article/body"
    "?pathname=/en/copilot/reference/ai-models/model-comparison"
)

# Regex patterns
SEPARATOR_RE = re.compile(r"^\|[-|: ]+\|$")
TASK_HEADING_RE = re.compile(r"^##\s+Task:\s+(.+)")
RECOMMENDED_MODELS_RE = re.compile(r"^###\s+Recommended models")


def fetch_markdown(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "fetch-model-comparison/1.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.read().decode("utf-8")


def is_separator(line: str) -> bool:
    return bool(SEPARATOR_RE.match(line)) and "-" in line


def parse_model_comparison(markdown: str) -> dict:
    """
    Parse the model comparison markdown into a structured dict.

    Returns:
        {
          "summary": [
            {"model": "...", "taskArea": "...", "excelsAt": "...", 
             "furtherReadingText": "...", "furtherReadingUrl": "..."}
          ],
          "tasks": [
            {"slug": "...", "title": "...", "intro": "...", 
             "recommended": [{"model": "...", "reason": "..."}],
             "useCases": ["..."], "useDifferent": "..."}
          ]
        }
    """
    summary = []
    tasks = []
    headers: list[str] = []
    current_task = None
    in_task_section = False
    capture_intro = False
    intro_done = False

    lines = markdown.splitlines()
    i = 0

    while i < len(lines):
        line = lines[i].rstrip()
        stripped = line.strip()

        # Check for ## Task: heading
        task_match = TASK_HEADING_RE.match(stripped)
        if task_match:
            # Save previous task if any
            if current_task:
                tasks.append(current_task)

            task_title = task_match.group(1).strip()
            task_slug = task_title.lower().replace(" ", "-").replace("(", "").replace(")", "").replace("/", "-").replace(",", "")
            current_task = {
                "slug": task_slug,
                "title": task_title,
                "intro": "",
                "recommended": [],
                "useCases": [],
                "useDifferent": "",
            }
            in_task_section = True
            capture_intro = True
            intro_done = False
            i += 1
            continue

        # Skip separator rows
        if is_separator(stripped):
            i += 1
            continue

        # Parse table rows
        if stripped.startswith("|") and stripped.endswith("|"):
            cells = [c.strip() for c in stripped.split("|")]
            cells = cells[1:-1]  # drop empty strings from leading/trailing |

            # Detect table header
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1
            is_header = j < len(lines) and is_separator(lines[j].strip())

            if is_header:
                headers = [c for c in cells]
                intro_done = True  # Stop capturing intro once we hit a table
                i = j + 1
                continue

            # Data row processing
            if headers and cells and any(c for c in cells):
                if not in_task_section:
                    # This is part of the main summary table
                    if "Model" in headers:
                        obj: dict = {}
                        for idx, header in enumerate(headers):
                            val = cells[idx].strip() if idx < len(cells) else ""
                            # Extract link if present (e.g., "[text](url)" -> text)
                            link_match = re.search(r"\[([^\]]+)\]\(([^)]+)\)", val)
                            if link_match:
                                obj[f"{header}_text"] = link_match.group(1)
                                obj[f"{header}_url"] = link_match.group(2)
                                obj[header] = link_match.group(1)
                            else:
                                obj[header] = val
                        if obj.get("Model"):
                            summary.append(obj)
                else:
                    # This is within a task section's table
                    if "Model" in headers:
                        model_idx = headers.index("Model")
                        # Find the reason column (various names possible)
                        reason_idx = -1
                        for ridx, rhead in enumerate(headers):
                            if "good fit" in rhead.lower() or "reason" in rhead.lower():
                                reason_idx = ridx
                                break
                        if model_idx < len(cells):
                            model_name = cells[model_idx].strip()
                            reason = cells[reason_idx].strip() if reason_idx >= 0 and reason_idx < len(cells) else ""
                            if model_name:
                                current_task["recommended"].append({"model": model_name, "reason": reason})

            i += 1
            continue

        # Extract intro text for current task (paragraphs between task heading and first table)
        if in_task_section and capture_intro and not intro_done and stripped and not stripped.startswith("#") and not stripped.startswith("|"):
            if stripped.startswith(">") or stripped.startswith("###"):
                # Skip blockquotes and subsection headings
                i += 1
                continue
            if stripped.startswith("*") or stripped.startswith("-"):
                # Start of bullet list - stop capturing intro
                capture_intro = False
                i += 1
                continue

            # Regular paragraph text - collect as intro
            if not current_task["intro"]:
                current_task["intro"] = stripped
            else:
                current_task["intro"] += " " + stripped

        # Collect "When to use these models" bullet points
        if in_task_section and stripped.startswith("* "):
            # Check if we're in a use cases section (look back for the heading)
            in_use_cases = False
            if i > 0:
                for k in range(max(0, i-5), i):
                    if "When to use these models" in lines[k]:
                        in_use_cases = True
                        break
            
            if in_use_cases:
                text = stripped.lstrip("* ").strip()
                if text and text not in current_task["useCases"]:
                    current_task["useCases"].append(text)

        # Collect "When to use a different model" section
        if in_task_section and stripped.startswith("### When to use a different"):
            # Capture the next few lines as the "different" guidance
            j = i + 1
            diff_parts = []
            while j < len(lines) and j - i < 8:
                next_line = lines[j].strip()
                if next_line.startswith("##"):  # Next task section
                    break
                if next_line.startswith("###"):  # Another subsection
                    break
                if next_line.startswith("|"):  # Table start
                    break
                if next_line and not next_line.startswith("#"):
                    diff_parts.append(next_line)
                j += 1
            current_task["useDifferent"] = " ".join(diff_parts)

        i += 1

    # Append last task
    if current_task:
        tasks.append(current_task)

    # Normalize summary table data
    normalized_summary = []
    for entry in summary:
        if entry.get("Model"):
            normalized_summary.append({
                "model": entry.get("Model", ""),
                "taskArea": entry.get("Task area", ""),
                "excelsAt": entry.get("Excels at (primary use case)", ""),
                "furtherReadingText": entry.get("Further reading_text", ""),
                "furtherReadingUrl": entry.get("Further reading_url", ""),
            })

    return {
        "summary": normalized_summary,
        "tasks": tasks,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch GitHub Copilot model comparison data.")
    args = parser.parse_args()

    print("Fetching model comparison data from GitHub docs...")
    markdown = fetch_markdown(API_URL)

    data = parse_model_comparison(markdown)

    today = date.today().isoformat()
    output = {
        "fetchDate": today,
        "summary": data["summary"],
        "tasks": data["tasks"],
    }

    out_path = Path(__file__).parent / "model_comparison.json"
    out_path.write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(f"\nWrote {out_path}")

    print(f"  Summary entries: {len(data['summary'])}")
    print(f"  Task sections: {len(data['tasks'])}")

    print("\nDone. Run generate_html.py to rebuild index.html with the updated comparison data.")


if __name__ == "__main__":
    main()
