import csv
import hashlib
import importlib.util
import json
from concurrent.futures import ThreadPoolExecutor
from importlib.machinery import SourceFileLoader
from pathlib import Path

import pytest

from smishing_backend.data.export_files import write_corpus
from smishing_backend.data.repositories.contributions import (
    PostgresContributionRepository,
)
from smishing_backend.data.repositories.quarantine import PostgresQuarantineRepository
from smishing_backend.data.repositories.review import PostgresReviewRepository
from smishing_backend.domain.contributions import Label, NewContribution
from smishing_backend.domain.corpus_export import InvalidCorpusExport, render_corpus
from smishing_backend.domain.review import ReviewDecision


@pytest.fixture
def accepted_rows(pg):
    saved = []
    repo = PostgresContributionRepository(pg)
    for i, label in enumerate(["smishing", "smishing", "safe", "safe"]):
        saved.append(
            repo.save(
                NewContribution(
                    f'Mensaje sintético {i}, con "comillas" y <URL>',
                    str(i) * 64,
                    (Label(label, "1.0.0"),),
                )
            )
        )
    review = PostgresReviewRepository(pg)
    review.decide(
        saved[0].id,
        "reviewer-demo",
        ReviewDecision("accepted", "quality_checked", "safe"),
    )
    review.decide(
        saved[1].id,
        "reviewer-demo",
        ReviewDecision("accepted", "quality_checked", "smishing"),
    )
    review.decide(
        saved[2].id,
        "reviewer-demo",
        ReviewDecision("rejected", "invalid_content", "safe"),
    )
    return PostgresQuarantineRepository(pg).accepted_for_training()


def test_exports_only_accepted_and_preferred_manual_label(accepted_rows, tmp_path):
    assert len(accepted_rows) == 2
    artifact = render_corpus(accepted_rows)
    file = write_corpus(artifact, tmp_path)
    with file.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert {r["label"] for r in rows} == {"0", "1"}
    assert {r["label_origin"] for r in rows} == {"manual"}
    assert all(
        r["model_version"] == "1.0.0" and r["corpus_version"] == artifact.version
        for r in rows
    )
    assert not any(
        "sintético 2" in r["text"] or "sintético 3" in r["text"] for r in rows
    )
    assert set(rows[0]) == {
        "text",
        "label",
        "label_origin",
        "model_version",
        "corpus_version",
    }
    manifest = json.loads((file.parent / "manifest.json").read_bytes())
    assert (
        manifest["rows"] == 2
        and manifest["sha256"] == hashlib.sha256(file.read_bytes()).hexdigest()
    )


def test_identical_content_is_byte_reproducible_across_order_and_ids(
    accepted_rows, tmp_path
):
    first = render_corpus(accepted_rows)
    second = render_corpus(
        [{**row, "id": "different-record-id"} for row in reversed(accepted_rows)]
    )
    assert first == second
    assert write_corpus(first, tmp_path) == write_corpus(second, tmp_path)
    assert not list(tmp_path.glob(".corpus-*"))


def test_device_fallback_and_content_change_version():
    row = {
        "text": "Mensaje sintético",
        "label": "safe",
        "label_origin": "device",
        "model_version": "1.0.0",
    }
    first = render_corpus([row])
    second = render_corpus([{**row, "label": "smishing"}])
    assert first.version != second.version
    assert b"device" in first.csv_bytes and b"1.0.0" in first.csv_bytes


def test_empty_corpus_stable_and_tampered_existing_export_rejected(tmp_path):
    artifact = render_corpus([])
    path = write_corpus(artifact, tmp_path)
    assert artifact == render_corpus([]) and artifact.count == 0
    assert path.read_bytes().count(b"\n") == 1
    path.write_bytes(b"synthetic corruption")
    with pytest.raises(InvalidCorpusExport):
        write_corpus(artifact, tmp_path)


def test_concurrent_export_same_content_is_safe(accepted_rows, tmp_path):
    artifact = render_corpus(accepted_rows)
    with ThreadPoolExecutor(max_workers=2) as pool:
        files = list(pool.map(lambda _: write_corpus(artifact, tmp_path), range(2)))
    assert files[0] == files[1] and files[0].read_bytes() == artifact.csv_bytes


def test_real_unmodified_model_loader_reads_export(accepted_rows, tmp_path):
    # Pinned, byte-for-byte upstream consumer; no TensorFlow or training is invoked.
    source = Path("tests/compat/charcnn-sources-b9c72dc.py.txt")
    assert (
        hashlib.sha256(source.read_bytes()).hexdigest()
        == "2302f3c51b816e613aff3558112d7da1bcef42b25e3e3435f414d91824622b0a"
    )
    loader = SourceFileLoader("upstream_model_sources", str(source))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    path = write_corpus(render_corpus(accepted_rows), tmp_path)
    frame = module.load_local_legit_corpus(path)
    assert len(frame) == 2 and set(frame["y"]) == {0, 1}
    assert set(frame.columns) == {"text", "y", "source", "lang"}
    assert frame["text"].str.contains("sintético").all()
    assert not frame["text"].str.contains("<URL>", regex=False).any()


def test_operator_command_exports_database_without_logging_text(
    pg, accepted_rows, tmp_path, monkeypatch, capsys
):
    from smishing_backend import export_corpus

    monkeypatch.setattr(export_corpus, "create_database_engine", lambda _: pg)
    monkeypatch.setattr("sys.argv", ["export_corpus", "--output-dir", str(tmp_path)])
    assert export_corpus.main() == 0
    output = capsys.readouterr().out
    assert "Exported 2 accepted contributions" in output
    assert "Mensaje" not in output and "reviewer-demo" not in output
    assert len(list(tmp_path.glob("backend-*/corpus.csv"))) == 1
