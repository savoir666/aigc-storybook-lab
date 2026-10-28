from typing import Literal
from pydantic import BaseModel, Field, ConfigDict, model_validator

class StoryInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str = Field(default='小栗', min_length=1, max_length=20)
    age: int = Field(default=6, ge=3, le=12)
    audience_age: int = Field(default=6, ge=3, le=12)

    @model_validator(mode='before')
    @classmethod
    def legacy_audience_age(cls, value):
        # Older books used age for both meanings; explicit audience ages stay independent.
        if isinstance(value, dict) and 'audience_age' not in value:
            value = {**value, 'audience_age': value.get('age', 6)}
        return value

    interest: str = Field(default='寻找星星、结交朋友', max_length=120)
    theme: Literal['forest', 'space', 'ocean'] = 'forest'
    setting: str = Field(default='', max_length=180)
    length: Literal['short', 'medium', 'long'] = 'long'
    strategy: Literal['zero_shot', 'few_shot', 'role_play'] = 'role_play'
    mode: Literal['demo', 'live'] = 'demo'

class Instruction(BaseModel):
    instruction: str = Field(min_length=1, max_length=500)

class AgentRequest(BaseModel):
    instruction: str = Field(default='', max_length=500)
    pause_after_story: bool = False

class CompareRequest(BaseModel):
    project_id: str
    mode: Literal['demo', 'live'] | None = None

class Character(BaseModel):
    name: str = Field(min_length=1, max_length=30)
    traits: str
    appearance: str
    role: str = 'character'
    voice: str = ''
    id: str = ''

class Dialogue(BaseModel):
    character: str
    text: str = Field(min_length=1)
    emotion: str = '温柔'

class Scene(BaseModel):
    scene_id: int
    title: str = ''
    description: str
    text: str = Field(min_length=10)
    mood: str
    visual_prompt: str
    dialogues: list[Dialogue] = Field(min_length=1)

class StoryOutput(BaseModel):
    processing: dict = Field(default_factory=dict)
    title: str = Field(min_length=1, max_length=100)
    characters: list[Character] = Field(min_length=3)
    scenes: list[Scene] = Field(min_length=3, max_length=12)
    moral: str
