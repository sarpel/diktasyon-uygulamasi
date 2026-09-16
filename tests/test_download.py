import io

from dikte.stt.download import download_model


def test_download_model_reports_progress_via_injected_downloader(tmp_path):
    calls = []

    def fake_downloader(*, repo_id, cache_dir, tqdm_class):
        assert repo_id  # faster_whisper.utils._MODELS'ten çözümlenmiş bir kimlik olmalı
        assert cache_dir == str(tmp_path)
        bar = tqdm_class(total=100, file=io.StringIO())
        bar.update(40)
        bar.update(60)
        return str(tmp_path / "snapshot")

    result = download_model(
        "large-v3-turbo",
        tmp_path,
        progress=lambda done, total: calls.append((done, total)),
        downloader=fake_downloader,
    )
    assert result == tmp_path / "snapshot"
    assert calls == [(40, 100), (100, 100)]


def test_download_model_resolves_repo_id_from_model_name(tmp_path):
    seen = {}

    def fake_downloader(*, repo_id, cache_dir, tqdm_class):
        seen["repo_id"] = repo_id
        return str(tmp_path)

    download_model("large-v3-turbo", tmp_path, progress=lambda *a: None, downloader=fake_downloader)
    assert seen["repo_id"] == "mobiuslabsgmbh/faster-whisper-large-v3-turbo"


def test_download_model_falls_back_to_model_name_when_unmapped(tmp_path):
    seen = {}

    def fake_downloader(*, repo_id, cache_dir, tqdm_class):
        seen["repo_id"] = repo_id
        return str(tmp_path)

    download_model(
        "custom-org/whatever-model", tmp_path, progress=lambda *a: None, downloader=fake_downloader
    )
    assert seen["repo_id"] == "custom-org/whatever-model"
