"""Isolated HTTP contract and concurrency checks; no seed or real .env changes.

Run in the main process with permission to create Windows local socketpairs:
pytest tests/test_server_contract.py --basetemp <workspace>/work/server-tests
"""
from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
import io
import json
import threading
import time
import zipfile

from fastapi.testclient import TestClient
import pytest

from storybook import config, providers, server, storage
from storybook.models import StoryInput
from storybook.retrieval import AssetSearch
from storybook.story import demo_story, make_project


@pytest.fixture
def isolated_server(tmp_path, monkeypatch):
    data = tmp_path / "data"
    projects = data / "projects"
    library = data / "library"
    projects.mkdir(parents=True)
    library.mkdir(parents=True)
    (library / "manifest.json").write_text('{"assets":[]}', encoding="utf-8")
    web = tmp_path / "web"
    web.mkdir()
    (web / "index.html").write_text("isolated test page", encoding="utf-8")
    for module in (config, server):
        monkeypatch.setattr(module, "ROOT", tmp_path)
    for module in (config, server, storage, providers):
        monkeypatch.setattr(module, "DATA", data)
    for module in (config, server, storage):
        monkeypatch.setattr(module, "PROJECTS", projects)
    monkeypatch.setattr(server, "searcher", AssetSearch(tmp_path))
    monkeypatch.setattr(server, "JOBS", {})
    monkeypatch.setattr(server, "TASKS", set())
    monkeypatch.setattr(server, "seed_projects", lambda: None)
    # Mount objects were constructed at module import. Redirect every mount so
    # even accidental static requests can only access the temporary fixture.
    mount_dirs = {"/files/projects": projects, "/files/library": library, "": web}
    for route in server.app.routes:
        if route.__class__.__name__ == "Mount" and route.path in mount_dirs:
            directory = str(mount_dirs[route.path])
            monkeypatch.setattr(route.app, "directory", directory)
            monkeypatch.setattr(route.app, "all_directories", [directory])
    params = StoryInput(name="隔离测试", mode="demo")
    project = make_project(demo_story(params), params, "test-project")
    storage.save_project(project)
    with TestClient(server.app, raise_server_exceptions=False) as client:
        yield client, project, tmp_path


def wait_for_job(client, job_id, timeout=5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        response = client.get(f"/api/jobs/{job_id}")
        assert response.status_code == 200
        job = response.json()
        if job["status"] in {"completed", "failed"}:
            return job
        time.sleep(0.02)
    raise AssertionError("任务未在测试时间内完成")


def test_status_settings_routes_and_missing_project(isolated_server):
    client, project, root = isolated_server
    response = client.get("/api/status")
    assert response.status_code == 200
    assert response.json()["counts"] == {"projects": 1, "templates": 0, "images": 0, "sounds": 0}
    assert response.json()["clip_ready"] is False
    settings = client.get("/api/settings").json()
    assert settings["free_only"] is True
    assert "text_api_key" not in settings and "image_api_key" not in settings
    assert client.get("/api/projects/missing").status_code == 404
    assert client.get("/api/jobs/missing").status_code == 404


def test_remote_origin_write_is_rejected(isolated_server):
    client, project, root = isolated_server
    response = client.post("/api/settings", json={"mode": "live"}, headers={"Origin": "https://unrelated.example"})
    assert response.status_code == 403
    assert not (root / ".env").exists()


def test_settings_secrets_and_paid_model_guard_are_isolated(isolated_server, monkeypatch):
    client, project, root = isolated_server
    secret = "test-secret-only-in-temporary-env"
    response = client.post("/api/settings", json={"text_api_key": secret, "text_model": "paid-model"})
    assert response.status_code == 200
    assert secret not in response.text
    assert response.json()["text_key_set"] is True
    called = []
    async def forbid_network(self, *args, **kwargs):
        called.append(True)
        raise AssertionError("付费模型不应发出网络请求")
    monkeypatch.setattr(providers.ModelClient, "_post", forbid_network)
    test = client.post("/api/settings/test")
    assert test.status_code == 400
    assert "免费" in test.json()["detail"]
    assert secret not in test.text
    assert called == []
    assert (root / ".env").exists()


def test_live_missing_key_fails_without_demo_fallback(isolated_server, monkeypatch):
    client, project, root = isolated_server
    called = []
    async def forbid_network(self, *args, **kwargs):
        called.append(True)
        raise AssertionError("无密钥时不能访问模型")
    monkeypatch.setattr(providers.ModelClient, "_post", forbid_network)
    before = len(storage.list_projects())
    response = client.post("/api/projects", json={"name": "无密钥", "mode": "live"})
    assert response.status_code == 400
    assert "密钥" in response.json()["detail"]
    assert len(storage.list_projects()) == before
    assert called == []


def test_manually_edited_env_cannot_send_bearer_over_http(isolated_server, monkeypatch):
    client, project, root = isolated_server
    (root / ".env").write_text("TEXT_BASE_URL=http://open.bigmodel.cn/api/paas/v4\nTEXT_MODEL=glm-4.7-flash\nTEXT_API_KEY=isolated-fake-key\n", encoding="utf-8")
    called = []
    async def forbid_network(self, *args, **kwargs):
        called.append(True)
        raise AssertionError("必须在网络调用前拒绝明文HTTP")
    monkeypatch.setattr(providers.ModelClient, "_post", forbid_network)
    response = client.post("/api/settings/test")
    assert response.status_code == 400
    assert called == []


def test_demo_creation_does_not_call_text_or_image_api(isolated_server, monkeypatch):
    client, project, root = isolated_server
    async def forbidden(*args, **kwargs):
        raise AssertionError("demo不得访问真实模型")
    monkeypatch.setattr(providers.ModelClient, "story", forbidden)
    monkeypatch.setattr(providers.ModelClient, "images", forbidden)
    monkeypatch.setattr(server, "render_demo_images", lambda p, directory: p)
    response = client.post("/api/projects", json={"name": "本地示例", "mode": "demo"})
    assert response.status_code == 200
    assert response.json()["project"]["mode"] == "demo"
    assert "本地" in response.json()["project"]["provider"]


def test_export_excludes_env_hidden_files_and_root_secrets(isolated_server):
    client, project, root = isolated_server
    secret = "should-never-be-in-project-export"
    (root / ".env").write_text("TEXT_API_KEY=" + secret, encoding="utf-8")
    folder = storage.project_dir(project["id"])
    (folder / ".env").write_text(secret, encoding="utf-8")
    (folder / ".private").mkdir()
    (folder / ".private" / "secret.json").write_text(json.dumps({"key": secret}), encoding="utf-8")
    (folder / "notes.md").write_text("public project note", encoding="utf-8")
    response = client.get(f"/api/projects/{project['id']}/export.zip")
    assert response.status_code == 200
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        names = archive.namelist()
        assert "project.json" in names and "notes.md" in names
        assert not any(part.startswith(".") for name in names for part in name.split("/"))
        assert all(secret.encode() not in archive.read(name) for name in names)


def test_busy_project_rejects_pdf_render_that_could_overwrite_state(isolated_server, monkeypatch):
    client, project, root = isolated_server
    server.JOBS["active"] = {"id": "active", "project_id": project["id"], "status": "running", "label": "测试", "logs": []}
    rendered = []
    def fake_pdf(p, directory):
        rendered.append(True)
        path = directory / "test.pdf"
        path.write_bytes(b"%PDF-1.4\n%%EOF")
        return path
    monkeypatch.setattr(server, "render_pdf", fake_pdf)
    response = client.get(f"/api/projects/{project['id']}/book.pdf")
    assert response.status_code == 409
    assert rendered == []
    server.JOBS["active"]["status"] = "completed"


def test_two_revisions_never_mutate_same_project_concurrently(isolated_server, monkeypatch):
    client, project, root = isolated_server
    entered = threading.Event()
    inflight = 0
    maximum = 0
    async def fake_revision(p, instruction):
        nonlocal inflight, maximum
        inflight += 1
        maximum = max(maximum, inflight)
        entered.set()
        try:
            await asyncio.sleep(0.15)
            revised = dict(p, title=instruction)
            storage.save_project(revised)
            return revised
        finally:
            inflight -= 1
    monkeypatch.setattr(server, "revise_project", fake_revision)
    url = f"/api/projects/{project['id']}/revise"
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(client.post, url, json={"instruction": "第一次修订"})
        assert entered.wait(timeout=3)
        second = pool.submit(client.post, url, json={"instruction": "第二次修订"})
        statuses = [first.result(timeout=5).status_code, second.result(timeout=5).status_code]
    assert statuses[0] == 200
    assert statuses[1] in {200, 409, 423}
    assert maximum == 1, "两个await中的修订都通过ensure_idle，造成并发覆盖"


def test_failed_job_records_error_and_busy_job_is_rejected(isolated_server, monkeypatch):
    client, project, root = isolated_server
    async def fail_audio(*args, **kwargs):
        raise RuntimeError("测试配音连接失败")
    monkeypatch.setattr(server, "generate_audio", fail_audio)
    response = client.post(f"/api/projects/{project['id']}/audio")
    assert response.status_code == 200
    job = wait_for_job(client, response.json()["job_id"])
    assert job["status"] == "failed"
    assert "测试配音连接失败" in job["error"]
    assert any(step["status"] == "failed" for step in job["steps"])
    assert (root / "data" / "jobs" / f"{job['id']}.json").is_file()


def test_demo_agent_really_calls_writing_and_four_tools(isolated_server, monkeypatch):
    client, project, root = isolated_server
    called = []
    async def write(params, pid=None):
        called.append("write_story")
        return storage.load_project(pid)
    def images(p, directory):
        called.append("generate_images")
        return p
    async def audio(p, directory, log):
        called.append("generate_audio")
        return p
    def video(p, directory, log):
        called.append("render_video")
        return p
    async def forbidden_planning(*args, **kwargs):
        raise AssertionError("demo不能调用真实模型规划器")
    monkeypatch.setattr(server, "generate_story", write)
    monkeypatch.setattr(server, "render_demo_images", images)
    monkeypatch.setattr(server, "generate_audio", audio)
    monkeypatch.setattr(server, "render_video", video)
    monkeypatch.setattr(providers.ModelClient, "chat_json", forbidden_planning)
    response = client.post(f"/api/projects/{project['id']}/agent", json={})
    assert response.status_code == 200
    job = wait_for_job(client, response.json()["job_id"])
    assert job["status"] == "completed", job.get("error")
    assert called == ["write_story", "generate_images", "generate_audio", "render_video"]
    trace = json.loads((storage.project_dir(project["id"]) / "agent_trace.json").read_text(encoding="utf-8"))
    assert trace["planning_mode"] == "demo_rules"
