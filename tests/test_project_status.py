import sys
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import project_status
from project_status import issue_from_pr_title, proposed_change, transition_allowed


def event(title="feat(#6): agregar autenticación", draft=True, action="opened", head_repo="smishing-thesis/smishing-backend"):
    return {
        "action": action,
        "repository": {"full_name": "smishing-thesis/smishing-backend"},
        "pull_request": {
            "title": title,
            "draft": draft,
            "state": "open",
            "head": {"repo": {"full_name": head_repo}},
        },
    }


class ProjectStatusTests(unittest.TestCase):
    def test_title_accepts_one_story_only(self):
        self.assertEqual(issue_from_pr_title("feat(#6): agregar autenticación"), 6)
        self.assertEqual(issue_from_pr_title("feat: base FastAPI (#3)"), 3)
        self.assertIsNone(issue_from_pr_title("feat(#6): atender #7"))
        self.assertIsNone(issue_from_pr_title("feat: cambios #6"))

    def test_draft_and_ready_pr(self):
        self.assertEqual(proposed_change(event()).target, "In progress")
        self.assertEqual(proposed_change(event(draft=False, action="ready_for_review")).target, "In review")

    def test_other_repo_and_merged_pr_never_move_issues(self):
        self.assertIsNone(proposed_change(event(head_repo="outsider/fork")))
        self.assertIsNone(proposed_change(event(action="closed", draft=False)))

    def test_never_regress_review_or_done(self):
        self.assertFalse(transition_allowed("In review", "In progress"))
        self.assertFalse(transition_allowed("Done", "In progress"))
        self.assertFalse(transition_allowed("Done", "In review"))
        self.assertTrue(transition_allowed("Ready", "In review"))

    def test_live_path_moves_only_matching_issue(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            event_path = Path(directory) / "event.json"
            event_path.write_text(json.dumps(event(draft=False)), encoding="utf-8")
            items = [
                {"id": "backend", "content": {"number": 6, "state": "OPEN", "repository": {"nameWithOwner": "smishing-thesis/smishing-backend"}}, "fieldValueByName": {"name": "In progress"}},
                {"id": "other", "content": {"number": 6, "state": "OPEN", "repository": {"nameWithOwner": "smishing-thesis/smishing-mobile-app"}}, "fieldValueByName": {"name": "Backlog"}},
                {"id": "draft", "content": None, "fieldValueByName": None},
            ]
            with patch.dict(os.environ, {"GITHUB_EVENT_NAME": "pull_request_target", "GITHUB_EVENT_PATH": str(event_path), "GH_TOKEN": "test"}), patch.object(project_status, "load_project", return_value=("project", "field", {"In review": "option"}, items)), patch.object(project_status, "graphql", return_value={}) as mutation:
                self.assertEqual(project_status.main(), 0)
                mutation.assert_called_once()
                self.assertEqual(mutation.call_args.args[2]["item"], "backend")

    def test_full_column_does_not_mutate(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            event_path = Path(directory) / "event.json"
            event_path.write_text(json.dumps(event(draft=False)), encoding="utf-8")
            items = [{"id": "backend", "content": {"number": 6, "state": "OPEN", "repository": {"nameWithOwner": "smishing-thesis/smishing-backend"}}, "fieldValueByName": {"name": "In progress"}}]
            items.extend({"id": str(index), "content": None, "fieldValueByName": {"name": "In review"}} for index in range(5))
            with patch.dict(os.environ, {"GITHUB_EVENT_NAME": "pull_request_target", "GITHUB_EVENT_PATH": str(event_path), "GH_TOKEN": "test"}), patch.object(project_status, "load_project", return_value=("project", "field", {"In review": "option"}, items)), patch.object(project_status, "graphql") as mutation:
                self.assertEqual(project_status.main(), 0)
                mutation.assert_not_called()


if __name__ == "__main__":
    unittest.main()

