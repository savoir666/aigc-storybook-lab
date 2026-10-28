"""Provider/story contracts. MockTransport only; configuration/cache/logs use tmp."""
from contextlib import ExitStack
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, patch
import httpx

from storybook import config, providers, storage
from storybook.models import StoryInput
from storybook.providers import ModelClient, extract_json
from storybook.story import demo_story, make_project, normalize_story, revise_demo


class Sandbox:
    def setUp(self):
        temporary_base = Path(__file__).resolve().parents[3] / "work" / "provider-tests"
        temporary_base.mkdir(parents=True, exist_ok=True)
        temporary = tempfile.TemporaryDirectory(dir=temporary_base)
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.data = self.root / "data"
        self.secret = "isolated-mock-api-key-do-not-export"
        self.write_settings()
        stack = ExitStack()
        self.addCleanup(stack.close)
        stack.enter_context(patch.object(config, "ROOT", self.root))
        for module in (config, providers, storage):
            stack.enter_context(patch.object(module, "DATA", self.data))

    def write_settings(self, **changes):
        values = dict(TEXT_BASE_URL="https://open.bigmodel.cn/api/paas/v4", TEXT_MODEL="glm-4.7-flash", TEXT_API_KEY=self.secret,
                      IMAGE_BASE_URL="https://open.bigmodel.cn/api/paas/v4", IMAGE_MODEL="cogview-3-flash", IMAGE_API_KEY="")
        values.update(changes)
        (self.root / ".env").write_text("\n".join(f"{key}={value}" for key, value in values.items()) + "\n", encoding="utf-8")


class ConfigurationAndStoryTests(Sandbox, unittest.TestCase):
    def test_https_official_host_and_free_models_are_all_required(self):
        for change in ({"TEXT_BASE_URL": "http://open.bigmodel.cn/api/paas/v4"},
                       {"TEXT_BASE_URL": "https://open.bigmodel.cn.evil.example/api"},
                       {"TEXT_BASE_URL": "https://user:password@open.bigmodel.cn/api"},
                       {"TEXT_MODEL": "paid-model"}):
            with self.subTest(change=change):
                self.write_settings(**change)
                with self.assertRaisesRegex(ValueError, "免费"):
                    config.require_free("text")
        self.write_settings(IMAGE_MODEL="paid-image-model")
        with self.assertRaisesRegex(ValueError, "免费"):
            config.require_free("image")

    def test_public_settings_hide_keys_and_blank_input_preserves_key(self):
        public = config.public_settings()
        self.assertTrue(public["text_key_set"])
        self.assertTrue(public["image_key_set"])
        self.assertNotIn(self.secret, json.dumps(public))
        config.update_settings({"text_api_key": "", "free_only": False})
        self.assertEqual(config.settings()["TEXT_API_KEY"], self.secret)
        self.assertTrue(config.public_settings()["free_only"])

    def test_fenced_and_surrounding_text_json_are_parsed(self):
        expected = {"title": "星星", "count": 3}
        examples = [json.dumps(expected, ensure_ascii=False),
                    '```json\n{"title":"星星","count":3}\n```',
                    '结果如下，请查看：\n{"title":"星星","count":3}\n以上为生成结果。']
        for example in examples:
            with self.subTest(example=example):
                self.assertEqual(extract_json(example), expected)
        with self.assertRaisesRegex(ValueError, "合法JSON"):
            extract_json("这里没有JSON")
        with self.assertRaisesRegex(ValueError, "合法JSON"):
            extract_json('前言 {"characters":[{"name":"小栗"}],"text":"他说"你好""}')

    def test_three_demo_themes_have_valid_scenes_and_speaking_roles(self):
        for theme in ("forest", "space", "ocean"):
            with self.subTest(theme=theme):
                story = normalize_story(demo_story(StoryInput(theme=theme)))
                self.assertEqual(len(story["scenes"]), 6)
                speakers = {line["character"] for scene in story["scenes"] for line in scene["dialogues"]}
                self.assertGreaterEqual(len(speakers), 3)
                self.assertTrue(speakers.issubset({c["name"] for c in story["characters"]}))
                self.assertEqual([scene["scene_id"] for scene in story["scenes"]], list(range(1, 7)))

    def test_explicit_companion_quote_gets_its_own_voice_without_new_words(self):
        story = demo_story(StoryInput())
        story['scenes'][0]['dialogues'] = [{'character':'旁白','text':'米粒抬起头。“我们一起走。”米粒说道。小栗点头。','emotion':'温柔'}]
        result = normalize_story(story)
        rows = result['scenes'][0]['dialogues']
        self.assertEqual([r['character'] for r in rows], ['旁白','米粒','旁白'])
        self.assertEqual(rows[1]['text'], '我们一起走。')
        self.assertTrue(all(row['text'] in result['scenes'][0]['text'] for row in rows))
        self.assertEqual(result['processing']['attributed_quotes_reassigned'], 1)
        self.assertEqual(normalize_story(result)['scenes'][0]['dialogues'], rows)

    def test_long_demo_has_substantial_actual_speech_text(self):
        # Duration must still be measured from actual generated audio.
        for theme in ("forest", "space", "ocean"):
            with self.subTest(theme=theme):
                def spoken_length(length):
                    story = demo_story(StoryInput(theme=theme, length=length))
                    return sum(len(line["text"]) for scene in story["scenes"] for line in scene["dialogues"])
                self.assertGreaterEqual(spoken_length("long"), 1200)
                self.assertGreater(spoken_length("long"), spoken_length("short"))

    def test_demo_rename_and_theme_revision_preserve_identity(self):
        params = StoryInput(name="小栗", theme="forest")
        original = make_project(demo_story(params), params, "isolated-project")
        revised = revise_demo(original, "名字改成小星，场景换成太空")
        self.assertEqual(revised["id"], original["id"])
        self.assertEqual(revised["created_at"], original["created_at"])
        self.assertEqual(revised["inputs"]["name"], "小星")
        self.assertEqual(revised["theme"], "space")
        self.assertIn("小星", revised["title"])
        normalize_story(revised)
        self.assertEqual(original["inputs"]["name"], "小栗")
        self.assertEqual(original["theme"], "forest")


class ProviderBoundaryTests(Sandbox, unittest.IsolatedAsyncioTestCase):
    async def test_rate_limit_retries_then_returns_valid_json(self):
        requests = []
        def respond(request):
            requests.append(request)
            self.assertEqual(request.headers["Authorization"], "Bearer " + self.secret)
            if len(requests) == 1:
                return httpx.Response(429, json={"error": {"message": "rate limited"}})
            return httpx.Response(200, json={"choices": [{"message": {"content": '```json\n{"ok":true}\n```'}}]})
        with patch("storybook.providers.asyncio.sleep", new=AsyncMock()) as sleep:
            async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as transport:
                result = await ModelClient(transport).chat_json([{"role": "user", "content": "mock"}], cache=False)
        self.assertEqual(result, {"ok": True})
        self.assertEqual(len(requests), 2)
        self.assertGreaterEqual(sleep.await_count, 1)
        logs = (self.data / "api_usage.jsonl").read_text(encoding="utf-8")
        self.assertIn('"status": 429', logs)
        self.assertNotIn(self.secret, logs)

    async def test_unauthorized_does_not_retry_and_redacts_echoed_secret(self):
        requests = []
        def respond(request):
            requests.append(request)
            return httpx.Response(401, json={"error": {"message": "invalid key " + self.secret}})
        with patch("storybook.providers.asyncio.sleep", new=AsyncMock()) as sleep:
            async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as transport:
                with self.assertRaises(ValueError) as caught:
                    await ModelClient(transport).chat_json([{"role": "user", "content": "mock"}], cache=False)
        self.assertEqual(len(requests), 1)
        sleep.assert_not_awaited()
        self.assertIn("401", str(caught.exception))
        self.assertNotIn(self.secret, str(caught.exception))
        for path in self.data.rglob("*") if self.data.exists() else []:
            if path.is_file():
                self.assertNotIn(self.secret, path.read_text(encoding="utf-8"))

    async def test_repeated_prompt_uses_cache_without_another_request(self):
        requests = []
        def respond(request):
            requests.append(request)
            return httpx.Response(200, json={"choices": [{"message": {"content": '{"cached":"result"}'}}], "usage": {"total_tokens": 12}})
        messages = [{"role": "user", "content": "same safe prompt"}]
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as transport:
            client = ModelClient(transport)
            first = await client.chat_json(messages)
            second = await client.chat_json(messages)
        self.assertEqual(first, second)
        self.assertEqual(len(requests), 1)
        logs = [json.loads(line) for line in (self.data / "api_usage.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertTrue(any(row.get("cache_hit") is True for row in logs))
        self.assertNotIn(self.secret, json.dumps(logs))

    async def test_array_root_is_repaired_and_raw_response_kept_without_secret(self):
        requests=[]
        params=StoryInput(theme="forest")
        def respond(request):
            requests.append(json.loads(request.content))
            content=[{"bad":"array-root"}] if len(requests)==1 else demo_story(params)
            return httpx.Response(200,json={"choices":[{"message":{"content":json.dumps(content,ensure_ascii=False)},"finish_reason":"stop"}]})
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as transport:
            story,messages=await ModelClient(transport).story(params)
        self.assertEqual(len(requests),2)
        self.assertEqual(len(story["scenes"]),6)
        self.assertIn("array-root",messages[-2]["content"])
        evidence=[p.read_text(encoding="utf-8") for p in (self.data/"responses").glob("*.json")]
        self.assertEqual(len(evidence),2)
        self.assertNotIn(self.secret,"".join(evidence))

    async def test_too_short_story_is_expanded_once_with_measured_feedback(self):
        requests=[]
        params=StoryInput(length="long")
        def respond(request):
            requests.append(json.loads(request.content))
            content=demo_story(params)
            if len(requests)==1:
                content["characters"][0]={"name":"旁白"}
                for scene in content["scenes"]:
                    for line in scene["dialogues"]:
                        line["text"]="你好。"
            return httpx.Response(200,json={"choices":[{"message":{"content":json.dumps(content,ensure_ascii=False)},"finish_reason":"stop"}]})
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as transport:
            story,messages=await ModelClient(transport).story(params)
        self.assertEqual(len(requests),2)
        self.assertIn("配音正文",messages[-1]["content"])
        self.assertGreaterEqual(sum(len(d["text"]) for scene in story["scenes"] for d in scene["dialogues"]),1400)

    async def test_valid_repair_is_reused_when_agent_repeats_same_story(self):
        requests=[]
        params=StoryInput(length="long")
        def respond(request):
            requests.append(json.loads(request.content))
            content=demo_story(params)
            if len(requests)==1:
                for scene in content["scenes"]:
                    for line in scene["dialogues"]:
                        line["text"]="你好。"
            return httpx.Response(200,json={"choices":[{"message":{"content":json.dumps(content,ensure_ascii=False)}}]})
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as transport:
            first,_=await ModelClient(transport).story(params)
            second,_=await ModelClient(transport).story(params)
        self.assertEqual(first,second)
        self.assertEqual(len(requests),2,"accepted repair must not be requested again by write_story")

    async def test_story_schema_failure_is_repaired_once(self):
        requests = []
        params = StoryInput(theme="space")
        def respond(request):
            requests.append(json.loads(request.content))
            content = {"title": "incomplete"} if len(requests) == 1 else demo_story(params)
            return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(content, ensure_ascii=False)}}]})
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as transport:
            story, messages = await ModelClient(transport).story(params)
        self.assertEqual(len(requests), 2)
        self.assertEqual(len(story["scenes"]), 6)
        self.assertIn("修复", messages[-1]["content"])


if __name__ == "__main__":
    unittest.main()
