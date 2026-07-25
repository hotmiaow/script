---
name: youtube-transcriber
description: Download YouTube audio, convert to text using auto-detected STT engine, and create a summarized markdown file.
---

# YouTube Audio Transcriber & Summarizer Skill

## Description
Download YouTube audio, convert to text using auto-detected STT engine (Apple Speech / Whisper / faster-whisper), and create a summarized markdown file. Supports parallel processing for speed. Works on iOS, macOS, and Linux.

## Features
- **Auto-Detect STT Engine**: Automatically uses Apple Speech (iOS/macOS), Whisper, or faster-whisper (Linux)
- **Parallel Processing**: Transcribes multiple chunks simultaneously (4x faster)
- **Smart Chunking**: Automatically splits audio >5 minutes into 5-minute chunks
- **Optimized Audio**: Uses 16kHz mono for faster processing
- **Summary Generation**: Creates concise summaries with key points
- **Clean Output**: Markdown file with sanitized filename (no special characters)
- **Bilingual**: Supports English and Traditional Chinese (繁體中文)
- **Progress Tracking**: Shows progress at each step (6 steps total)
- **Cross-Platform**: Works on iOS, macOS, and Linux

## Triggers
Use this skill when the user:
- Asks to transcribe a YouTube video
- Wants to convert YouTube audio to text
- Provides a YouTube URL and asks for summary/transcription
- Mentions "YouTube transcription", "YouTube to text", "summarize YouTube", "YouTube 字幕", "YouTube 摘要"
- Wants to process long YouTube videos with chunking

## Instructions

### 1. Ensure dependencies are installed:
```bash
which yt-dlp || apk add yt-dlp
which ffmpeg || apk add ffmpeg
```

### 2. Use the main script:
```bash
# Fast mode (parallel processing, default)
/root/transcribe_youtube.sh "<YouTube URL>" "[language]" "fast"

# Standard mode (sequential processing)
/root/transcribe_youtube.sh "<YouTube URL>" "[language]" "standard"

# language: Optional, "en" for English (default) or "zh" for Traditional Chinese
# mode: Optional, "fast" (default) or "standard"
```

### 3. Script workflow (6 steps with progress):

**Step 1: Download Audio (Optimized)**
- Downloads audio-only stream (faster than video)
- Converts to 128kbps MP3, 16kHz mono (optimized for STT)

**Step 2: Chunk Audio (if needed)**
- Checks audio duration
- If >5 minutes: splits into 5-minute chunks using ffmpeg (copy mode, no re-encoding)
- If ≤5 minutes: processes as single file

**Step 3: Transcribe Chunks (Parallel)**
- Auto-detects best STT engine:
  - **Apple Speech** (iOS/macOS) - Native, high accuracy
  - **faster-whisper** (Linux) - Fastest, uses tiny model
  - **Whisper** (fallback) - Good accuracy
- Transcribes 4 chunks in parallel
- Supports English (en-US) and Traditional Chinese (zh-TW)

**Step 4: Combine Transcriptions**
- Merges all chunk transcriptions in order
- Creates unified text file

**Step 5: Generate Summary**
- Creates structured summary with key points
- English or Traditional Chinese based on language setting

**Step 6: Create Markdown File**
- Sanitized filename (alphanumeric, dashes, underscores only)
- Includes: original link, timestamp, summary, full transcription
- Saved to `/home/keith/youtube_transcriber/attachments/`

### 4. Output format:
- **Location**: `/home/keith/youtube_transcriber/attachments/`
- **Format**: Markdown (.md)
- **Filename**: Sanitized video title (alphanumeric, dashes, underscores only)
- **Content Structure**:
  ```markdown
  # Video Title
  
  **Original Link:** https://youtube.com/watch?v=...
  
  **Transcribed:** 2026-03-28 01:30
  
  ---
  
  ## Summary/摘要
  Key points from the video
  
  ### Key Points/重點
  - Point 1
  - Point 2
  
  ### Full Transcription/完整內容
  [Complete transcription text]
  ```

### 5. Speed Comparison:

| Mode | 30-min video | Notes |
|------|-------------|-------|
| **Fast (parallel)** | ~5-8 min | 4x faster, uses parallel processing |
| Standard | ~15-20 min | Sequential processing |

### 6. Language support:
- English (default)
- Traditional Chinese (when language="zh")

## Example Usage

**User:** "Transcribe this video: https://youtu.be/qebKa0Ncsqk"
**Assistant:** 
```bash
/root/transcribe_youtube.sh "https://youtu.be/qebKa0Ncsqk" "en"
```

**User:** "幫我把這段 YouTube 轉成文字並總結：https://youtu.be/example"
**Assistant:**
```bash
/root/transcribe_youtube.sh "https://youtu.be/example" "zh"
```

## Notes
- **Auto-Detect STT**: Automatically detects and uses the best available engine (Apple Speech > faster-whisper > Whisper)
- **Parallel Processing**: Transcribes up to 4 chunks simultaneously (4x speedup)
- **Optimized Audio**: Uses 16kHz mono audio for faster STT processing
- **Chunking**: Audio >5 minutes is split into 5-minute chunks
- **Cross-Platform**: Works on iOS, macOS, and Linux
- **Language Support**: English (en-US) and Traditional Chinese (zh-TW)
- **Filename Sanitization**: Removes special characters, keeps alphanumeric + dashes/underscores
- **Progress Tracking**: 6-step progress display throughout execution
- **Output Location**: All markdown files saved to `/home/keith/youtube_transcriber/attachments/`
- **Original Link**: Always included at the top of the markdown file
- **Speed**: Fast mode is 3-4x faster than standard mode for long videos
