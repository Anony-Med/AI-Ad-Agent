# ViMax Architecture Reference

**Note:** This document preserves useful concepts from the original ViMax project for future reference.
The ViMax directory has been removed from this project as we've built our own AI Ad Agent system.

## What Was ViMax?

ViMax was a multi-agent video generation system that converted ideas/scripts into videos using a pipeline of specialized agents.

## Useful Architecture Patterns

### 1. Multi-Agent Pipeline Pattern

ViMax used specialized agents for different tasks:

```python
# Pattern: Each agent has a specific responsibility
class CharacterExtractor:
    """Extract character information from script"""

class SceneExtractor:
    """Extract scene information from script"""

class StoryboardArtist:
    """Create visual storyboards"""

class CameraImageGenerator:
    """Generate images with camera angles"""
```

**What We Adopted:**
- ✅ We used this same pattern in our AI Ad Agent
- ✅ Created specialized agents: PromptGenerator, VideoGenerator, AudioCompositor, etc.

### 2. Interface-Based Design

ViMax defined clear interfaces for data structures:

```python
# interfaces/character.py
class Character:
    name: str
    description: str
    appearance: str

# interfaces/scene.py
class Scene:
    location: str
    time: str
    characters: List[Character]
    actions: List[str]
```

**What We Adopted:**
- ✅ Created `ad_schemas.py` with clear Pydantic models
- ✅ Defined VideoClip, AdJob, CreativeSuggestion interfaces

### 3. Pipeline Orchestration

ViMax pipelines orchestrated multiple agents:

```python
# Pattern: Step-by-step processing with state management
class Idea2VideoPipeline:
    def run(self, idea: str):
        # Step 1: Extract characters
        characters = self.character_extractor.extract(idea)

        # Step 2: Generate scenes
        scenes = self.scene_extractor.extract(idea, characters)

        # Step 3: Create storyboard
        storyboard = self.storyboard_artist.create(scenes)

        # Step 4: Generate images
        images = self.image_generator.generate(storyboard)

        # Step 5: Generate video
        video = self.video_generator.generate(images)

        return video
```

**What We Adopted:**
- ✅ Created `AdCreationPipeline` with 8 sequential steps
- ✅ Each step updates job status and progress
- ✅ Error handling at each step

### 4. Tool Abstractions

ViMax abstracted different API providers:

```python
# tools/video_generator_veo_google_api.py
class VeoVideoGenerator:
    def generate(self, prompt: str) -> str:
        # Call Veo API

# tools/image_generator_nanobanana_google_api.py
class NanoBananaImageGenerator:
    def generate(self, prompt: str) -> str:
        # Call Imagen API
```

**What We Adopted:**
- ✅ Created separate clients: `gemini_client.py`, `elevenlabs_client.py`
- ✅ Used Unified API for video generation instead of direct calls
- ✅ Abstracted away API differences

### 5. Retry and Error Handling

ViMax had robust retry logic:

```python
# utils/retry.py
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def call_api():
    # API call with automatic retry
```

**What We Adopted:**
- ✅ Used same `tenacity` library in our clients
- ✅ Applied retry decorators to API calls
- ✅ Exponential backoff for transient failures

## Key Differences from Our Implementation

### ViMax Approach
- **Goal:** Convert novels/stories into full movies
- **Complexity:** Very complex with character tracking, scene understanding, etc.
- **Video Generation:** Direct API calls to multiple providers
- **Output:** Long-form videos with complex narratives

### Our AI Ad Agent Approach
- **Goal:** Create short ad videos from scripts
- **Complexity:** Simpler, focused workflow
- **Video Generation:** Uses Unified API for consistency
- **Output:** Short, polished ad videos (7-21 seconds)

## Useful Code Snippets for Future Reference

### 1. Video Merging with ffmpeg (from ViMax)

```python
# ViMax had sophisticated video merging
def merge_videos_with_transitions(clips: List[str], output: str):
    """Merge videos with cross-fade transitions"""
    filter_complex = []

    for i in range(len(clips) - 1):
        filter_complex.append(
            f"[{i}:v][{i+1}:v]xfade=transition=fade:duration=0.5:offset={i*5}[v{i}]"
        )

    cmd = [
        "ffmpeg",
        *[f"-i {clip}" for clip in clips],
        "-filter_complex", ";".join(filter_complex),
        output
    ]

    subprocess.run(cmd)
```

**Note:** We used simpler concatenation, but this could be useful for smoother transitions.

### 2. Image Reranking (from ViMax)

```python
# ViMax used BGE reranker to select best images
from reranker import BGEReranker

def select_best_image(prompt: str, images: List[str]) -> str:
    """Select image that best matches prompt"""
    reranker = BGEReranker()
    scores = reranker.rank(prompt, images)
    return images[scores.argmax()]
```

**Note:** Could be useful if we generate multiple variations and want to select the best.

### 3. Character Consistency (from ViMax)

```python
# ViMax generated character portraits for reference
def generate_character_portraits(character: Character):
    """Generate reference images from multiple angles"""
    angles = ["front view", "side view", "three-quarter view"]
    portraits = []

    for angle in angles:
        prompt = f"{character.description}, {angle}, portrait style"
        image = image_generator.generate(prompt)
        portraits.append(image)

    return portraits
```

**Note:** Similar to our character_image approach, but more comprehensive.

## What We Could Add from ViMax

### Future Enhancements Inspired by ViMax

1. **Multiple Variations**
   - Generate 3-4 versions of each clip
   - Use reranker to select best
   - Gives better quality control

2. **Advanced Video Effects**
   - Cross-fade transitions between clips
   - Zoom effects
   - Pan and scan

3. **Character Reference Library**
   - Store character portraits
   - Reuse across multiple ads
   - Maintain brand consistency

4. **Scene Planning**
   - More sophisticated script analysis
   - Extract entities and actions
   - Better prompt engineering

5. **Quality Scoring**
   - Rate generated clips
   - Auto-retry low-quality clips
   - Ensemble best clips

## ViMax Agent Breakdown

For reference, here's what each ViMax agent did:

| Agent | Purpose | Useful for Us? |
|-------|---------|----------------|
| `character_extractor.py` | Extract character info from script | ✅ Could improve our script analysis |
| `scene_extractor.py` | Break script into scenes | ✅ Already doing this with prompt generation |
| `event_extractor.py` | Extract key events | ⏳ Future: Better prompt creation |
| `screenwriter.py` | Enhance script quality | ⏳ Future: Script improvement |
| `script_planner.py` | Plan shot composition | ⏳ Future: Better camera work |
| `storyboard_artist.py` | Create storyboards | ⏳ Future: Visual preview |
| `camera_image_generator.py` | Generate with camera angles | ✅ We handle this in prompts |
| `best_image_selector.py` | Rank and select images | ⏳ Future: Quality control |
| `reference_image_selector.py` | Find reference images | ✅ We use character_image |

## Conclusion

ViMax was a sophisticated system for long-form video generation. We've adopted its best patterns (multi-agent architecture, clear interfaces, retry logic) while simplifying for our ad creation use case.

The original ViMax code has been removed from this project but these concepts remain valuable for future enhancements.

---

**Original ViMax Repository:** (if you want to reference it later)
- Location: Was in `ViMax/` directory
- Removed: 2025-01-08
- Reason: Not needed for AI Ad Agent, built our own simpler system
