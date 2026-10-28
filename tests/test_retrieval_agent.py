"""Meaningful offline retrieval, plan validation and intervention checks.

No API calls, paid services, model downloads or fabricated CLIP results.
"""
from __future__ import annotations

import asyncio
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

from storybook.agent import PIPELINE, run_agent, validate_plan
from storybook.retrieval import AssetSearch, translate_clip_query


@unittest.skipUnless(importlib.util.find_spec("sklearn"), "需要scikit-learn")
class RetrievalTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        library = self.root / "data" / "library"
        library.mkdir(parents=True)
        assets = [
            {"id": "forest", "type": "template", "title": "森林友谊", "description": "小兔在树林中找到朋友", "tags": ["森林", "友谊"]},
            {"id": "space", "type": "template", "title": "太空探险", "description": "火箭穿过星星前往月球", "tags": ["太空", "星球"]},
            {"id": "space-image", "type": "image", "title": "太空火箭插画", "tags": ["太空", "火箭"], "url": "/files/library/rocket.png"},
            {"id": "bird", "type": "sound", "title": "森林鸟鸣", "tags": ["森林", "小鸟"]},
        ]
        (library / "manifest.json").write_text(json.dumps({"assets": assets}, ensure_ascii=False), encoding="utf-8")
        self.search = AssetSearch(self.root)

    def tearDown(self):
        self.temporary.cleanup()

    def test_chinese_vector_search_and_modality_filter(self):
        response = self.search.search("太空月球", "template", 2)
        self.assertEqual(response["results"][0]["id"], "space")
        self.assertGreater(response["results"][0]["score"], response["results"][1]["score"])
        self.assertEqual(response["counts"], {"templates": 2, "images": 1, "sounds": 1})

    def test_absent_clip_is_explicitly_labelled_fallback(self):
        response = self.search.search("太空", "image")
        self.assertFalse(response["clip_ready"])
        self.assertIn("非CLIP", response["engine"])
        self.assertIn("标签", response["results"][0]["engine"])
        self.assertIn("setup_clip", response["warning"])

    def test_empty_query_and_limit_are_supported(self):
        self.assertEqual(len(self.search.search("", limit=1)["results"]), 1)
        self.assertEqual(self.search.search("", limit=0)["results"], [])
        with self.assertRaises(ValueError):
            self.search.search("太空", "anything")

    def test_library_path_cannot_escape_library(self):
        secret = self.root / "private.png"
        secret.write_bytes(b"not an image")
        self.assertIsNone(self.search._asset_path({"path": "../../private.png"}))


class PlanningTests(unittest.TestCase):
    def test_four_tools_and_dependencies_are_enforced(self):
        self.assertEqual(validate_plan(list(PIPELINE)), list(PIPELINE))
        for illegal in (["write_story", "exec_shell", "generate_audio", "render_video"], list(reversed(PIPELINE)), list(PIPELINE[:-1]), list(PIPELINE) + ["write_story"]):
            with self.assertRaises(ValueError):
                validate_plan(illegal)

    def test_dictionary_is_explicit_about_unknown_chinese(self):
        mapped = translate_clip_query("太空火箭和月亮，未知词")
        self.assertIn("outer space", mapped["text"])
        self.assertIn("rocket", mapped["text"])
        self.assertIn("未知词", mapped["unmapped_chinese"])

    def test_model_may_choose_retrieval_review_and_bounded_retry(self):
        plan = ["retrieve_materials", "write_story", "review_story", "generate_images", "generate_images", "generate_audio", "render_video"]
        self.assertEqual(validate_plan(plan), plan)
        with self.assertRaisesRegex(ValueError, "未授权"):
            validate_plan(plan, PIPELINE)
        self.assertEqual(validate_plan([*PIPELINE, "review_story"]), [*PIPELINE, "review_story"])
        self.assertEqual(validate_plan([*PIPELINE[:-1], "review_story", "render_video"]), [*PIPELINE[:-1], "review_story", "render_video"])


@unittest.skipUnless(importlib.util.find_spec("langchain_core"), "需要真实langchain-core")
class AgentTests(unittest.IsolatedAsyncioTestCase):
    def make_tools(self, project, calls):
        tools = {}
        for name in PIPELINE:
            def callback_factory(tool_name):
                async def callback():
                    calls.append((tool_name, project.get("hero", "男孩")))
                    return dict(project, last_tool=tool_name)
                return callback
            tools[name] = callback_factory(name)
        async def revise(instruction):
            calls.append(("revise_story", instruction))
            return dict(project, hero="女孩", revised_with=instruction)
        tools["revise_story"] = revise
        return tools

    async def test_rules_mode_really_runs_four_registered_tools(self):
        project, job, calls, saved = {"id": "test"}, {}, [], []
        result = await run_agent(project, self.make_tools(project, calls), None, job, lambda value: saved.append(dict(value)))
        self.assertEqual([name for name, _ in calls], list(PIPELINE))
        self.assertEqual(result["planning_mode"], "demo_rules")
        self.assertEqual(result["framework"], "langchain_core.StructuredTool")
        self.assertEqual(job["status"], "completed")
        self.assertEqual(job["progress"], 100)
        self.assertEqual(len(saved), 4)
        self.assertEqual(sum(row["event"] == "tool_end" for row in result["trace"]), 4)

    async def test_invalid_model_plan_stops_before_any_generation(self):
        project, job, calls = {"id": "test"}, {}, []
        async def planner(instruction, current):
            return ["write_story", "generate_images", "execute_python", "render_video"]
        with self.assertRaisesRegex(ValueError, "未授权"):
            await run_agent(project, self.make_tools(project, calls), planner, job, lambda value: None)
        self.assertEqual(calls, [])
        self.assertEqual(job["status"], "failed")

    async def test_pause_intervention_changes_downstream_outputs(self):
        project, job, calls = {"id": "test", "hero": "男孩"}, {"pause_after_story": True}, []
        task = asyncio.create_task(run_agent(project, self.make_tools(project, calls), None, job, lambda value: None))
        async def wait_until_paused():
            while job.get("status") != "paused":
                if task.done():
                    return await task
                await asyncio.sleep(0.01)
        await asyncio.wait_for(wait_until_paused(), timeout=5)
        self.assertEqual([name for name, _ in calls], ["write_story"])
        job["pending_instruction"] = "把主角改成女孩"
        job["resume_requested"] = True
        result = await asyncio.wait_for(task, timeout=5)
        self.assertEqual(project["hero"], "女孩")
        self.assertEqual([hero for name, hero in calls if name in PIPELINE[1:]], ["女孩"] * 3)
        self.assertTrue(any(row["event"] == "intervention" for row in result["trace"]))

    async def test_late_intervention_regenerates_already_created_images(self):
        project, job, calls = {"id": "test", "hero": "男孩"}, {}, []
        tools = self.make_tools(project, calls)
        original_images = tools["generate_images"]
        first = True
        async def images():
            nonlocal first
            result = await original_images()
            if first:
                first = False
                job["pending_instruction"] = "主角改成女孩"
            return result
        tools["generate_images"] = images
        await run_agent(project, tools, None, job, lambda value: None)
        self.assertEqual([hero for name, hero in calls if name == "generate_images"], ["男孩", "女孩"])
        self.assertEqual([hero for name, hero in calls if name == "render_video"], ["女孩"])

    async def test_instruction_queued_at_start_still_runs_initial_writing(self):
        project, job, calls = {"id": "test"}, {"pending_instruction": "改成女孩"}, []
        await run_agent(project, self.make_tools(project, calls), None, job, lambda value: None)
        self.assertEqual([name for name, _ in calls], ["write_story", "revise_story", *PIPELINE[1:]])

    async def test_model_selects_optional_tools_and_retries(self):
        project, job, calls = {"id": "test"}, {}, []
        tools = self.make_tools(project, calls)
        for optional in ("retrieve_materials", "review_story"):
            def factory(name):
                async def callback():
                    calls.append((name, "chosen"))
                    return dict(project, **{name: True})
                return callback
            tools[optional] = factory(optional)
        chosen = ["retrieve_materials", "write_story", "review_story", "generate_images", "generate_images", "generate_audio", "render_video"]
        async def planner(instruction, current):
            return chosen
        result = await run_agent(project, tools, planner, job, lambda current: None)
        self.assertEqual([name for name, _ in calls], chosen)
        self.assertEqual(result["planning_mode"], "model")
        self.assertEqual(len(result["registered_tools"]), 6)


if __name__ == "__main__":
    unittest.main()
