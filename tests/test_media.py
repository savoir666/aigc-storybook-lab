"""Media integrity and truthful-export checks (no network requests)."""
import json
import tempfile
import unittest
import wave
from unittest.mock import patch
from pathlib import Path

from storybook.media import LIBRARY, _frame_schedule, _local_url_path, _subtitle_cards, render_demo_images, render_video


class MediaIntegrityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # The managed Windows environment can restrict its process TEMP folder.
        cls.temp_base=Path(__file__).resolve().parents[3]/"work"/"media-tests"
        cls.temp_base.mkdir(parents=True,exist_ok=True)

    def test_library_contains_real_files_and_unique_ids(self):
        manifest=json.loads((LIBRARY/"manifest.json").read_text(encoding="utf-8"))
        assets=manifest["assets"]
        self.assertEqual(len({a["id"] for a in assets}),len(assets))
        counts={kind:sum(a["type"]==kind for a in assets) for kind in ("image","template","sound")}
        self.assertGreaterEqual(counts["image"],20)
        self.assertGreaterEqual(counts["template"],10)
        self.assertGreaterEqual(counts["sound"],5)
        for asset in assets:
            self.assertTrue((LIBRARY/asset["path"]).is_file(),asset["path"])

    def test_demo_images_reuse_seed_files_without_redrawing(self):
        project={"theme":"forest","scenes":[{"title":str(i),"description":"保留原文"} for i in range(9)]}
        with tempfile.TemporaryDirectory(dir=self.temp_base) as directory:
            target=Path(directory)
            with patch("storybook.media.draw_demo_illustration",side_effect=AssertionError("Existing seeds must be reused")):
                render_demo_images(project,target)
            self.assertEqual((target/"scene-01.png").read_bytes(),(LIBRARY/"images/forest-01.png").read_bytes())
            self.assertEqual((target/"scene-09.png").read_bytes(),(LIBRARY/"images/forest-01.png").read_bytes())
            self.assertEqual(project["scenes"][0]["description"],"保留原文")
            self.assertEqual(project["generation_proof"]["images"]["reused_library_count"],9)
            self.assertEqual(project["generation_proof"]["images"]["newly_drawn_count"],0)
            self.assertEqual(project["generation_proof"]["images"]["scene_alignment"],"theme_demo_only")

    def test_demo_images_draw_only_when_seed_is_missing(self):
        project={"theme":"forest","scenes":[{"title":"新场景"}]}
        with tempfile.TemporaryDirectory(dir=self.temp_base) as directory:
            target=Path(directory)/"project";missing=Path(directory)/"missing-library"
            def draw(theme,index,destination,title):
                destination.write_bytes(b"technical-fixture")
            with patch("storybook.media.LIBRARY",missing),patch("storybook.media.draw_demo_illustration",side_effect=draw) as drawing:
                render_demo_images(project,target)
            drawing.assert_called_once()
            self.assertEqual(project["generation_proof"]["images"]["newly_drawn_count"],1)
            self.assertNotIn("image_asset_url",project["scenes"][0])

    def test_wav_assets_are_playable_and_non_silent(self):
        for filename in (LIBRARY/"sounds").glob("*.wav"):
            with wave.open(str(filename),"rb") as f:
                self.assertEqual(f.getsampwidth(),2)
                self.assertGreaterEqual(f.getframerate(),22050)
                self.assertGreater(f.getnframes()/f.getframerate(),3)
                frames=f.readframes(f.getnframes())
                self.assertTrue(any(frames),filename.name)

    def test_streamed_schedule_changes_scenes_and_captions_at_frame_boundaries(self):
        from types import GeneratorType
        frames=[(Path("first.png"),1.0),(Path("second.png"),1.0)]
        cards=[{"start":.5,"end":1.5}]
        schedule=_frame_schedule(frames,cards,2.0,fps=4)
        self.assertIsInstance(schedule,GeneratorType)
        self.assertEqual(list(schedule),[(0,None),(0,None),(0,0),(0,0),(1,0),(1,0),(1,None),(1,None)])

    def test_subtitles_use_real_word_boundaries(self):
        project={"segments":[{"start":0,"end":5,"text":"小栗和米粒一起出发。","words":[{"start":.38,"end":1.12,"text":"小栗"},{"start":1.12,"end":1.4,"text":"和"},{"start":1.4,"end":2.1,"text":"米粒"},{"start":2.3,"end":4.62,"text":"一起出发。"}]}]}
        with tempfile.TemporaryDirectory(dir=self.temp_base) as directory:
            cards=_subtitle_cards(project,Path(directory))
            self.assertEqual(cards[0]["start"],.38)
            self.assertEqual(cards[-1]["end"],4.62)
            self.assertTrue(cards[0]["path"].is_file())

    def test_video_requires_verified_real_speech(self):
        with tempfile.TemporaryDirectory(dir=self.temp_base) as directory:
            with self.assertRaisesRegex(RuntimeError,"真实角色配音"):
                render_video({"audio_url":"/fake.mp3","duration":120},Path(directory))

    def test_short_narration_is_not_padded_to_60_seconds(self):
        with tempfile.TemporaryDirectory(dir=self.temp_base) as directory:
            with self.assertRaisesRegex(RuntimeError,"少于 60 秒"):
                render_video({"audio_url":"/fake.mp3","duration":12,"audio_proof":{"real_tts":True}},Path(directory))

    def test_emotion_parameters_reach_tts_and_word_boundaries_remain_exact(self):
        import asyncio
        from types import SimpleNamespace
        from storybook.media import _save_speech, speech_prosody
        received=[]
        class Communicate:
            def __init__(self, **kwargs):
                received.append(kwargs)
            async def stream(self):
                yield {"type":"audio", "data":b"test-audio"}
                yield {"type":"WordBoundary", "offset":1_000_000, "duration":2_000_000, "text":"你好"}
        with tempfile.TemporaryDirectory(dir=self.temp_base) as directory:
            target=Path(directory)/"part.mp3"
            words=asyncio.run(_save_speech(SimpleNamespace(Communicate=Communicate),"你好。","voice",target,"兴奋"))
            self.assertEqual(received[0]["rate"],"+3%")
            self.assertEqual(received[0]["pitch"],"+4Hz")
            self.assertEqual(target.read_bytes(),b"test-audio")
            self.assertEqual(words,[{"start":0.1,"end":0.3,"text":"你好。"}])
        self.assertEqual(speech_prosody("低语")["volume"],"-8%")
        self.assertEqual(speech_prosody("未知情感"),speech_prosody("温柔"))

    def test_compaction_keeps_complete_quoted_sentences_and_roles(self):
        from storybook.story import _whole_sentences, compact_story
        source='小栗说：“你好。我们一起走吧！”米粒说：“好的！”大家走向森林。'
        self.assertEqual(_whole_sentences(source),['小栗说：“你好。我们一起走吧！”','米粒说：“好的！”','大家走向森林。'])
        rows=[{"character":name,"text":source*20,"emotion":"温柔"} for name in ['旁白','小栗','米粒']]
        story={"scenes":[{"title":"约定","description":"森林","dialogues":rows,"text":"原文"}]}
        result=compact_story(story,450)
        self.assertEqual({d['character'] for d in result['scenes'][0]['dialogues']},{'旁白','小栗','米粒'})
        self.assertLess(result['processing']['final_tts_characters'],result['processing']['original_tts_characters'])
        self.assertEqual(story['scenes'][0]['text'],'原文')
        for row in result['scenes'][0]['dialogues']:
            self.assertEqual(row['text'].count('“'),row['text'].count('”'))

    def test_local_media_rejects_directory_traversal(self):
        with tempfile.TemporaryDirectory(dir=self.temp_base) as directory:
            folder=Path(directory)/"example"
            folder.mkdir()
            with self.assertRaises(RuntimeError):
                _local_url_path("/files/library/../../src/storybook/media.py",folder)


if __name__=="__main__":
    unittest.main()
