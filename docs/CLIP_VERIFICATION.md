# Clip-to-Script Verification System

**Date:** 2025-01-08
**Feature:** Automated video clip verification using Gemini Vision

## Overview

The AI Ad Agent now includes **automatic clip-to-script verification** to ensure generated video clips accurately match their intended script content.

### The Problem It Solves

When Veo 3.1 generates video clips from prompts, there's no guarantee the visual content matches what the script describes. For example:

- **Script says:** "Looking at leaky roofs"
- **Generated video might show:** Generic house exterior without visible roof damage
- **Result:** Misalignment between what's said and what's shown

This verification system uses **Gemini Vision** to analyze each generated clip and verify it matches the script segment.

## How It Works

### Step-by-Step Process

1. **Prompt Generation (Step 1)**
   - Script is broken into segments
   - Each segment gets a Veo prompt
   - **Example:**
     ```
     Script: "Looking for your dream home? I can help you find it."

     Segment 1: "Looking for your dream home?"
     Prompt 1: "Medium shot of Heather in front of modern house..."

     Segment 2: "I can help you find it."
     Prompt 2: "Close-up of Heather inside bright living room..."
     ```

2. **Video Generation (Step 2)**
   - Veo 3.1 generates videos from prompts
   - Each clip is 7 seconds max

3. **Clip Verification (Step 2.5) - NEW**
   - **For each completed clip:**
     - Download the video file
     - Send to Gemini Vision for analysis
     - Compare visual content against script segment
     - Generate confidence score (0.0 to 1.0)

   - **Gemini Vision analyzes:**
     - What's visible in the scene
     - Character actions and expressions
     - Setting and environment
     - Alignment with script intent

4. **Verification Results**
   - Each clip gets:
     - ✅ **Verified** (confidence ≥ threshold) or ❌ **Failed** (confidence < threshold)
     - **Confidence score** (0.0 to 1.0)
     - **Visual description** (what Gemini sees)
     - **Alignment feedback** (how well it matches)

5. **Pipeline Continues**
   - Verified clips proceed to merging
   - Failed clips are logged as warnings
   - Job continues with available clips

## Configuration

### Enable/Disable Verification

Verification is **enabled by default** but can be controlled:

```json
{
  "script": "Your ad script here",
  "character_image": "BASE64_IMAGE",
  "enable_verification": true,  // Set to false to skip verification
  "verification_threshold": 0.6  // Confidence threshold (0.0 to 1.0)
}
```

### Verification Threshold

The threshold determines how strict verification is:

- **0.6 (default)** - Moderate: Clips must reasonably match
- **0.8** - Strict: Clips must closely match
- **0.4** - Lenient: Accept broader interpretations
- **1.0** - Perfect: Only exact matches pass (not recommended)

## API Usage

### Request Example

```bash
curl -X POST http://localhost:8000/api/ad-agent/create \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "campaign_id": "campaign_123",
    "script": "Looking for your dream home? I can help you find it.",
    "character_image": "BASE64_ENCODED_IMAGE",
    "character_name": "Heather",
    "enable_verification": true,
    "verification_threshold": 0.7
  }'
```

### Job Status Response

During verification (Step 2.5):

```json
{
  "job_id": "ad_1234567890",
  "status": "verifying_clips",
  "progress": 52,
  "current_step": "Verifying video clips match script content...",
  "video_clips": [
    {
      "clip_number": 1,
      "prompt": "Medium shot of Heather...",
      "script_segment": "Looking for your dream home?",
      "video_url": "https://storage.googleapis.com/...",
      "status": "completed",
      "verification": {
        "verified": true,
        "confidence_score": 0.85,
        "visual_description": "Video shows a professional woman standing in front of a modern house entrance...",
        "alignment_feedback": "Excellent match. Visual content aligns perfectly with script segment...",
        "retry_count": 0
      }
    }
  ]
}
```

## Verification Results

### What Gets Verified

For each clip, Gemini Vision checks:

1. **Scene Setting**
   - Does the location match? (house, office, outdoors, etc.)
   - Is the environment appropriate?

2. **Character Actions**
   - Are gestures appropriate for the dialogue?
   - Does facial expression match tone?

3. **Visual Elements**
   - If script mentions "leaky roofs", are roofs visible?
   - If script mentions "bright living room", is it bright?
   - Do props/objects match script references?

4. **Overall Alignment**
   - Does the visual story support the spoken words?
   - Is the tone consistent?

### Example Verification Results

#### ✅ Good Match (Score: 0.92)

**Script:** "Looking for your dream home?"
**Visual:** Woman standing in front of modern house, welcoming gesture
**Feedback:** "Excellent alignment. Scene shows professional real estate agent at attractive property, matching the 'dream home' theme perfectly."

#### ⚠️ Moderate Match (Score: 0.65)

**Script:** "I specialize in fixing leaky roofs"
**Visual:** Person on ladder near a house
**Feedback:** "Partial match. Shows roofing context but 'leaky' aspect not clearly visible. Consider prompt adjustment."

#### ❌ Poor Match (Score: 0.35)

**Script:** "Our state-of-the-art kitchen"
**Visual:** Generic living room scene
**Feedback:** "Misalignment detected. Video shows living room, not kitchen. Re-generate with kitchen-specific prompt."

## Logs and Monitoring

### What Gets Logged

The pipeline logs detailed verification information:

```
[ad_1234567890] Step 2.5: Verifying clips match script segments
[ad_1234567890] Verifying clip 1: https://storage.googleapis.com/...
[ad_1234567890] Video analysis complete: confidence=0.85
[ad_1234567890] Clip 1 verification: verified=True, confidence=0.85
[ad_1234567890] Verification complete: 3/3 clips verified (avg confidence: 0.82)
```

### Failed Clip Warnings

```
[ad_1234567890] 1 clips failed verification:
  - Clip 2: confidence=0.45, feedback: Misalignment detected. Scene shows...
```

## Performance Impact

### Additional Time

Verification adds approximately:
- **10-15 seconds per clip** (video download + Gemini Vision analysis)
- **30-45 seconds total** for 3-clip ad

### Additional Cost

- **Gemini Vision:** ~$0.002 per clip analysis
- **Total impact:** ~$0.006 per ad (negligible)

### When to Disable

Consider disabling verification if:
- Speed is critical (tight deadlines)
- Testing/development (rapid iteration)
- You're confident in prompt quality
- Manual review will happen anyway

## Architecture

### Components

1. **ClipVerifierAgent** (`clip_verifier.py`)
   - Orchestrates verification process
   - Manages confidence thresholds
   - Provides summary statistics

2. **GeminiClient.analyze_video_content()** (`gemini_client.py`)
   - Downloads video from URL
   - Encodes as base64
   - Calls Gemini Vision API
   - Parses JSON response

3. **ClipVerification Schema** (`ad_schemas.py`)
   - Stores verification results
   - Part of VideoClip model
   - Persisted in Firestore

### Data Flow

```
Script → Prompts + Segments
         ↓
     Veo 3.1 (generates clips)
         ↓
     Clip URLs
         ↓
  Download + Encode (base64)
         ↓
   Gemini Vision Analysis
         ↓
  Confidence Score + Feedback
         ↓
    Store in VideoClip
         ↓
   Continue Pipeline
```

## Future Enhancements

### Planned Features

1. **Automatic Retry**
   - If clip fails verification, regenerate with adjusted prompt
   - Up to 2 retry attempts per clip
   - Learn from verification feedback to improve prompts

2. **Detailed Element Verification**
   - Check specific objects mentioned in script
   - Verify colors, sizes, quantities
   - Face detection for character consistency

3. **Multi-Model Verification**
   - Use multiple vision models for consensus
   - Combine Gemini Vision + Claude Vision
   - Higher confidence through agreement

4. **Verification Reports**
   - Generate PDF verification report
   - Include screenshots with annotations
   - Export verification metrics

5. **Training Data Collection**
   - Collect verified/failed examples
   - Fine-tune prompts based on patterns
   - Improve Veo prompt quality over time

## Troubleshooting

### Verification Always Fails

**Problem:** All clips score below threshold
**Possible causes:**
- Threshold too high (try 0.5-0.6)
- Script too specific (Veo can't match detail)
- Poor prompt quality

**Solution:**
```json
{
  "verification_threshold": 0.5  // Lower threshold
}
```

### Verification Takes Too Long

**Problem:** Step 2.5 exceeds 2 minutes
**Possible causes:**
- Large video files (slow download)
- Gemini API throttling
- Network issues

**Solution:**
```json
{
  "enable_verification": false  // Disable for this job
}
```

### Gemini Vision Errors

**Problem:** `Gemini Vision API error: 400`
**Possible causes:**
- Invalid video format
- Video too large (>10MB)
- API quota exceeded

**Solution:** Check Gemini API quotas and video file sizes

## Examples

### Real Estate Ad

**Script:**
```
"Looking for your dream home? I specialize in luxury properties.
Let me show you the finest homes in the area."
```

**Verification Results:**

| Clip | Segment | Confidence | Verified |
|------|---------|------------|----------|
| 1 | "Looking for your dream home?" | 0.88 | ✅ |
| 2 | "I specialize in luxury properties." | 0.92 | ✅ |
| 3 | "Let me show you the finest homes..." | 0.75 | ✅ |

**Average Confidence:** 0.85 - Excellent match

### Product Demo Ad

**Script:**
```
"Our new blender makes smoothies in seconds.
Watch how easy it is to create healthy drinks."
```

**Verification Results:**

| Clip | Segment | Confidence | Verified |
|------|---------|------------|----------|
| 1 | "Our new blender makes smoothies..." | 0.65 | ✅ |
| 2 | "Watch how easy it is..." | 0.42 | ❌ |

**Average Confidence:** 0.54
**Issue:** Clip 2 didn't clearly show "ease of use" - needs prompt refinement

## Summary

### Key Benefits

✅ **Quality Assurance** - Catch misalignments before final export
✅ **Script Accuracy** - Ensure visuals match spoken content
✅ **Automated** - No manual review required
✅ **Configurable** - Adjust strictness per project
✅ **Transparent** - Detailed feedback for each clip

### When to Use

- **Always for client-facing ads** - Ensure quality
- **First-time prompts** - Validate new prompt styles
- **Specific visual requirements** - Script mentions exact elements
- **High-stakes campaigns** - Quality critical

### When to Skip

- **Testing/development** - Rapid iteration
- **Time-critical** - Need speed over perfection
- **Manual review planned** - Human verification anyway
- **Generic content** - Less specific requirements

---

**Status:** ✅ Implemented and Ready
**Impact:** Major - Ensures visual-script alignment
**Cost:** ~$0.006 per ad
**Time:** +30-45 seconds per ad

**Files Modified:**
- `backend/app/ad_agent/clients/gemini_client.py` - Added video analysis
- `backend/app/ad_agent/agents/clip_verifier.py` - NEW verification agent
- `backend/app/ad_agent/agents/prompt_generator.py` - Script segmentation
- `backend/app/ad_agent/interfaces/ad_schemas.py` - Verification schemas
- `backend/app/ad_agent/pipelines/ad_creation_pipeline.py` - Added Step 2.5
- `backend/app/routes/ad_agent.py` - Verification settings
