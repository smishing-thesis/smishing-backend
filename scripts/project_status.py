"""Move a backend issue on the organization Project when its PR changes stage.

Run only from trusted default-branch code in a pull_request_target workflow.
PR titles are data, never shell input or executable code.
"""

from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen


REPOSITORY = "smishing-thesis/smishing-backend"
PROJECT_OWNER = "smishing-thesis"
PROJECT_NUMBER = 1
STATUS_LIMITS = {"In progress": 3, "In review": 5}

PROJECT_QUERY = """
query($owner: String!, $number: Int!, $after: String) {
  organization(login: $owner) {
    projectV2(number: $number) {
      id
      fields(first: 100) {
        nodes {
          ... on ProjectV2SingleSelectField {
            id
            name
            options { id name }
          }
        }
      }
      items(first: 100, after: $after) {
        pageInfo { hasNextPage endCursor }
        nodes {
          id
          content {
            ... on Issue {
              number
              state
              repository { nameWithOwner }
            }
          }
          fieldValueByName(name: "Status") {
            ... on ProjectV2ItemFieldSingleSelectValue { name }
          }
        }
      }
    }
  }
}
"""

UPDATE_MUTATION = """
mutation($project: ID!, $item: ID!, $field: ID!, $option: String!) {
  updateProjectV2ItemFieldValue(input: {
    projectId: $project,
    itemId: $item,
    fieldId: $field,
    value: { singleSelectOptionId: $option }
  }) { projectV2Item { id } }
}
"""


@dataclass(frozen=True)
class Change:
    issue_number: int
    target: str


def issue_from_pr_title(title: str) -> int | None:
    """Accept the team's feat(#6): form or an unambiguous trailing (#6)."""
    conventional = re.match(r"^[a-z][a-z0-9_-]*\(#([1-9][0-9]*)\):\s+\S", title)
    trailing = re.search(r"\(#([1-9][0-9]*)\)$", title)
    matches = re.findall(r"(?<![A-Za-z0-9/])#([1-9][0-9]*)\b", title)
    if len(matches) != 1 or not (conventional or trailing):
        return None
    return int(matches[0])


def proposed_change(payload: dict) -> Change | None:
    pr = payload.get("pull_request", {})
    if payload.get("repository", {}).get("full_name") != REPOSITORY:
        return None
    if pr.get("head", {}).get("repo", {}).get("full_name") != REPOSITORY:
        return None
    if pr.get("state") != "open":
        return None
    number = issue_from_pr_title(pr.get("title", ""))
    if number is None:
        return None
    action = payload.get("action")
    if action not in {"opened", "reopened", "edited", "synchronize", "ready_for_review", "converted_to_draft"}:
        return None
    target = "In progress" if pr.get("draft") else "In review"
    return Change(number, target)


def transition_allowed(current: str | None, target: str) -> bool:
    if target == "In progress":
        return current in {"Backlog", "Ready"}
    if target == "In review":
        return current in {"Backlog", "Ready", "In progress"}
    return False


def graphql(token: str, query: str, variables: dict) -> dict:
    body = json.dumps({"query": query, "variables": variables}).encode("utf-8")
    request = Request(
        "https://api.github.com/graphql",
        data=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "User-Agent": "smishing-backend-project-status",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=20) as response:
            result = json.load(response)
    except HTTPError as error:
        raise RuntimeError(f"GitHub GraphQL HTTP {error.code}; check App Project permissions") from error
    if result.get("errors"):
        raise RuntimeError(f"GitHub GraphQL rejected Project access: {result['errors']}")
    return result["data"]


def load_project(token: str) -> tuple[str, str, dict[str, str], list[dict]]:
    cursor = None
    items: list[dict] = []
    project_id = ""
    status_field_id = ""
    options: dict[str, str] = {}
    while True:
        data = graphql(token, PROJECT_QUERY, {"owner": PROJECT_OWNER, "number": PROJECT_NUMBER, "after": cursor})
        project = (data.get("organization") or {}).get("projectV2")
        if not project:
            raise RuntimeError("Organization Project unavailable to this GitHub App")
        project_id = project["id"]
        for field in project["fields"]["nodes"]:
            if field and field.get("name") == "Status":
                status_field_id = field["id"]
                options = {option["name"]: option["id"] for option in field["options"]}
        page = project["items"]
        items.extend(page["nodes"])
        if not page["pageInfo"]["hasNextPage"]:
            break
        cursor = page["pageInfo"]["endCursor"]
        if not cursor:
            raise RuntimeError("Project pagination had no cursor")
    if not status_field_id or not all(name in options for name in STATUS_LIMITS):
        raise RuntimeError("Status field or expected column missing from Project")
    return project_id, status_field_id, options, items


def main() -> int:
    if os.environ.get("GITHUB_EVENT_NAME") != "pull_request_target":
        raise RuntimeError("Run only from pull_request_target on trusted main")
    payload = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text(encoding="utf-8"))
    change = proposed_change(payload)
    if change is None:
        print("No backend story with an unambiguous #N in this PR title; no change")
        return 0
    token = os.environ["GH_TOKEN"]
    project_id, field_id, options, items = load_project(token)
    matching = [
        item for item in items
        if (item.get("content") or {}).get("number") == change.issue_number
        and (item["content"].get("repository") or {}).get("nameWithOwner") == REPOSITORY
    ]
    if len(matching) != 1:
        print(f"Issue #{change.issue_number} has {len(matching)} Project cards; no change")
        return 0
    item = matching[0]
    if item["content"]["state"] != "OPEN":
        print(f"Issue #{change.issue_number} is closed; no change")
        return 0
    current = (item.get("fieldValueByName") or {}).get("name")
    if current == change.target:
        print(f"Issue #{change.issue_number} already in {current}; no change")
        return 0
    if not transition_allowed(current, change.target):
        print(f"Issue #{change.issue_number}: {current} -> {change.target} is not allowed; no change")
        return 0
    occupied = sum(
        (candidate.get("fieldValueByName") or {}).get("name") == change.target
        for candidate in items
    )
    if occupied >= STATUS_LIMITS[change.target]:
        print(f"::warning::Project {change.target} limit {STATUS_LIMITS[change.target]} reached; move issue #{change.issue_number} manually after a slot opens")
        return 0
    graphql(token, UPDATE_MUTATION, {
        "project": project_id,
        "item": item["id"],
        "field": field_id,
        "option": options[change.target],
    })
    print(f"Issue #{change.issue_number}: {current} -> {change.target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

