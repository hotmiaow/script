---
name: recipe-collector
description: Extract, organize, and format cooking recipes from various sources (URLs, videos, social media like Instagram Reels) into structured Traditional Chinese Markdown documents with step-by-step instructions and visual captures.
---

# Recipe Collector Skill

This skill specializes in transforming raw cooking content from social media and video platforms into well-structured, easy-to-follow recipe guides in Traditional Chinese.

## Workflow

### 1. Source Extraction
- **Metadata**: Use `yt-dlp` to fetch titles, descriptions, and comments from video/social media URLs.
- **Audio/Transcription**: If the spoken content is relevant, use transcription tools (like `faster-whisper`) to extract spoken instructions.
- **External Search**: If comments are restricted or incomplete, search for the creator's recipe online (e.g., Google Search for "[Creator Name] [Dish Name] recipe").

### 2. Visual Documentation
- **Frames**: Extract key frames from the video using `ffmpeg` (e.g., `ffmpeg -i video.mp4 -vf "fps=1/5" frames/frame_%03d.jpg`).
- **Organization**: Place these frames in a folder named after the recipe (formatted for the file system).

### 3. Formatting (Standard Output)
Generate a Markdown file using the following structure in **Traditional Chinese**:

- **Title**: Meaningful dish name (no emojis for filenames).
- **Metadata**: Source URL, Creator, and relevant Tags.
- **Ingredients (材料準備)**: List all main ingredients and accessories.
- **Sauce/Seasoning (醬汁與醃料)**: Detailed list of seasonings and their proportions.
- **Steps (烹飪步驟與截圖)**: 
    - Each step must have a clear heading.
    - Descriptive text in Traditional Chinese explaining the action.
    - Corresponding screen capture image link.

## Guidelines

- **Filenames**: Use descriptive Traditional Chinese names without emojis or special characters (e.g., `泰式烤魷魚做法.md`).
- **Language**: Always use **Traditional Chinese** for the recipe content unless requested otherwise.
- **Consistency**: Ensure the image folder name matches the descriptive filename of the Markdown document.
- **Cleanup**: Remove large temporary video/audio files after processing to save space, but keep the final Markdown and the image folder.

## Example Tools Usage
- `yt-dlp -x --audio-format mp3 -o "temp_audio.mp3" "<URL>"`
- `ffmpeg -i video.mp4 -vf "fps=1/4" recipe_images/step_%03d.jpg`
- `jq -r '.description' metadata.json`
