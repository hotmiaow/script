#!/usr/bin/env python3
"""
YouTube Audio Transcriber - Optimized for Speed
Features:
- Parallel chunk transcription
- Optimized audio conversion (mono, 16kHz)
- Auto-detect best STT engine (Apple Speech / Whisper / Vosk)
- Faster chunking
"""

import sys
import os
import subprocess
import re
import json
import threading
import queue
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

def sanitize_filename(text):
    """Remove special characters from filename"""
    text = re.sub(r'[<>:"/\\|?*]', '', text)
    text = re.sub(r'[^a-zA-Z0-9\u4e00-\u9fff_\-]', '_', text)
    text = re.sub(r'_+', '_', text)
    return text.strip('_')[:100]

def detect_stt_engine():
    """Detect available speech-to-text engine"""
    # Check Apple Speech
    result = subprocess.run(['which', 'apple-speech'], capture_output=True, text=True)
    if result.returncode == 0:
        return 'apple'
    
    # Check whisper
    result = subprocess.run(['which', 'whisper'], capture_output=True, text=True)
    if result.returncode == 0:
        return 'whisper'
    
    # Check faster-whisper
    try:
        import faster_whisper
        return 'faster_whisper'
    except:
        pass
    
    # Check vosk
    try:
        import vosk
        return 'vosk'
    except:
        pass
    
    return None

def download_audio_fast(url, output_path):
    """Download YouTube audio directly (fastest method)"""
    print("[1/6] Downloading audio directly...")
    
    # Download best audio only (no video)
    result = subprocess.run([
        'yt-dlp',
        '-x',  # Extract audio
        '--audio-format', 'mp3',
        '--audio-quality', '128K',  # Lower quality for speed
        '--no-mtime',
        '-o', output_path,
        url
    ], capture_output=True, text=True)
    
    if result.returncode == 0 and os.path.exists(output_path):
        print("✓ Audio downloaded")
        return True
    
    # Fallback: download video and extract
    print("  Fallback: downloading video...")
    video_file = output_path + '.mp4'
    result = subprocess.run([
        'yt-dlp', '-f', 'bestaudio/best',
        '--no-mtime', '-o', video_file, url
    ], capture_output=True, text=True)
    
    if result.returncode == 0 and os.path.exists(video_file):
        # Extract audio with optimized settings
        subprocess.run([
            'ffmpeg', '-y', '-i', video_file,
            '-vn', '-acodec', 'libmp3lame',
            '-ab', '128k', '-ac', '1',  # Mono for speed
            '-ar', '16000',  # 16kHz for faster processing
            output_path,
            '-loglevel', 'quiet'
        ])
        os.remove(video_file)
        if os.path.exists(output_path):
            print("✓ Audio extracted")
            return True
    
    print("Error: Failed to download audio")
    return False

def chunk_audio_fast(audio_path, chunks_dir, chunk_duration=300):
    """Split audio into chunks (optimized)"""
    print("[2/6] Preparing audio chunks...")
    
    os.makedirs(chunks_dir, exist_ok=True)
    
    # Get duration
    result = subprocess.run([
        'ffprobe', '-v', 'quiet',
        '-show_entries', 'format=duration',
        '-of', 'default=noprint_wrappers=1:nokey=1',
        audio_path
    ], capture_output=True, text=True)
    
    duration = float(result.stdout.strip())
    print(f"  Duration: {int(duration)}s")
    
    if duration > chunk_duration:
        num_chunks = int((duration + chunk_duration - 1) / chunk_duration)
        print(f"  Splitting into {num_chunks} chunks...")
        
        # Use ffmpeg with copy (fastest, no re-encoding)
        subprocess.run([
            'ffmpeg', '-y', '-i', audio_path,
            '-f', 'segment', '-segment_time', str(chunk_duration),
            '-c', 'copy',
            os.path.join(chunks_dir, 'chunk_%03d.mp3')
        ], capture_output=True, text=True)
    else:
        print("  No chunking needed")
        import shutil
        shutil.copy(audio_path, os.path.join(chunks_dir, 'chunk_000.mp3'))
    
    chunks = sorted([f for f in os.listdir(chunks_dir) if f.endswith('.mp3')])
    print(f"  ✓ Created {len(chunks)} chunks")
    return chunks

def transcribe_chunk_apple(chunk_path, lang):
    """Transcribe single chunk using Apple Speech"""
    lang_map = {'en': 'en-US', 'zh': 'zh-TW'}
    lang_code = lang_map.get(lang, 'en-US')
    
    result = subprocess.run([
        'apple-speech', 'transcribe',
        '--source', chunk_path,
        '--language', lang_code,
        '-q'
    ], capture_output=True, text=True, timeout=600)
    
    if result.returncode == 0:
        try:
            data = json.loads(result.stdout)
            if 'segments' in data:
                return ''.join([seg['substring'] for seg in data['segments']])
        except:
            pass
    return ""

def transcribe_chunk_whisper(chunk_path, lang):
    """Transcribe single chunk using Whisper (if available)"""
    lang_map = {'en': 'en', 'zh': 'zh'}
    lang_code = lang_map.get(lang, 'en')
    
    result = subprocess.run([
        'whisper', chunk_path,
        '--language', lang_code,
        '--model', 'tiny',  # Fastest model
        '--output_format', 'txt',
        '--output_dir', os.path.dirname(chunk_path)
    ], capture_output=True, text=True, timeout=600)
    
    txt_file = chunk_path.replace('.mp3', '.txt')
    if os.path.exists(txt_file):
        with open(txt_file, 'r') as f:
            return f.read()
    return ""

def transcribe_chunk_faster_whisper(chunk_path, lang):
    """Transcribe using faster-whisper (fastest)"""
    from faster_whisper import WhisperModel
    
    lang_map = {'en': 'en', 'zh': 'zh'}
    lang_code = lang_map.get(lang, 'en')
    
    # Load tiny model (fastest)
    model = WhisperModel("tiny", device="cpu", compute_type="int8")
    
    segments, _ = model.transcribe(
        chunk_path,
        language=lang_code,
        beam_size=1,
        vad_filter=True
    )
    
    return ' '.join([segment.text for segment in segments])

def transcribe_chunks_parallel(chunks_dir, trans_dir, language, engine):
    """Transcribe all chunks in parallel"""
    print(f"[3/6] Transcribing with {engine} (parallel)...")
    
    os.makedirs(trans_dir, exist_ok=True)
    
    chunks = sorted([f for f in os.listdir(chunks_dir) if f.endswith('.mp3')])
    
    # Select transcribe function
    if engine == 'apple':
        transcribe_func = lambda path: transcribe_chunk_apple(path, language)
    elif engine == 'whisper':
        transcribe_func = lambda path: transcribe_chunk_whisper(path, language)
    elif engine == 'faster_whisper':
        transcribe_func = lambda path: transcribe_chunk_faster_whisper(path, language)
    else:
        print("No transcription engine available!")
        return ""
    
    results = {}
    
    # Parallel execution
    with ThreadPoolExecutor(max_workers=4) as executor:
        future_to_chunk = {
            executor.submit(transcribe_func, os.path.join(chunks_dir, chunk)): chunk
            for chunk in chunks
        }
        
        for i, future in enumerate(as_completed(future_to_chunk), 1):
            chunk = future_to_chunk[future]
            try:
                text = future.result(timeout=600)
                results[chunk] = text
                print(f"  [{i}/{len(chunks)}] ✓ {chunk}")
            except Exception as e:
                print(f"  [{i}/{len(chunks)}] ✗ {chunk}: {e}")
    
    # Save individual results
    for chunk, text in results.items():
        trans_file = os.path.join(trans_dir, chunk.replace('.mp3', '.txt'))
        with open(trans_file, 'w', encoding='utf-8') as f:
            f.write(text)
    
    return results

def combine_transcriptions(trans_dir):
    """Combine all transcriptions"""
    print("[4/6] Combining transcriptions...")
    
    trans_files = sorted([f for f in os.listdir(trans_dir) if f.endswith('.txt')])
    combined = ""
    
    for trans_file in trans_files:
        with open(os.path.join(trans_dir, trans_file), 'r', encoding='utf-8') as f:
            combined += f.read() + "\n"
    
    return combined

def generate_summary(combined_text, language, output_dir, url):
    """Generate summary and markdown"""
    print("[5/6] Generating summary...")
    
    paragraphs = [p.strip() for p in combined_text.split('\n\n') if p.strip()]
    
    if language == 'zh':
        summary = "## 摘要\n\n以下是這段影片的重點整理：\n\n"
        key_points = []
        for para in paragraphs[:5]:
            sentences = para.split('。')
            if sentences and len(sentences[0].strip()) > 5:
                key_points.append(sentences[0].strip() + '。')
        
        if key_points:
            summary += "### 重點\n"
            for point in key_points[:10]:
                summary += f"- {point}\n"
            summary += "\n"
        summary += "### 完整內容\n\n"
    else:
        summary = "## Summary\n\nKey points:\n\n"
        key_points = []
        for para in paragraphs[:5]:
            sentences = para.split('.')
            if sentences and len(sentences[0].strip()) > 5:
                key_points.append(sentences[0].strip() + '.')
        
        if key_points:
            summary += "### Key Points\n"
            for point in key_points[:10]:
                summary += f"- {point}\n"
            summary += "\n"
        summary += "### Full Transcription\n\n"
    
    first_line = combined_text.split('\n')[0][:50].strip()
    video_title = first_line if first_line else "YouTube_Video"
    safe_title = sanitize_filename(video_title)
    if not safe_title:
        safe_title = "youtube_transcription"
    
    filename = f"{safe_title}.md"
    output_path = os.path.join(output_dir, filename)
    
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M')
    
    md_content = f"# {video_title}\n\n"
    md_content += f"**Original Link:** {url}\n\n"
    md_content += f"**Transcribed:** {timestamp}\n\n"
    md_content += "---\n\n"
    md_content += summary
    md_content += combined_text
    md_content += "\n\n---\n*Generated by YouTube Transcriber (Fast Mode)*\n"
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(md_content)
    
    print("[6/6] Complete!")
    print(f"Output: {output_path}")
    return output_path

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 youtube_transcriber_fast.py <URL> [language]")
        print("  language: en (default) or zh (Traditional Chinese)")
        sys.exit(1)
    
    url = sys.argv[1]
    language = sys.argv[2] if len(sys.argv) > 2 else 'en'
    
    print("=== YouTube Audio Transcriber (Fast Mode) ===")
    print(f"URL: {url}")
    print(f"Language: {language}")
    print()
    
    # Detect STT engine
    engine = detect_stt_engine()
    if engine:
        print(f"Using engine: {engine}")
    else:
        print("⚠️ No STT engine found! Installing faster-whisper...")
        subprocess.run(['pip', 'install', 'faster-whisper'], check=True)
        engine = 'faster_whisper'
    
    # Setup directories
    work_dir = f"/home/keith/youtube_transcriber/workspace/youtube_fast_{os.getpid()}"
    audio_dir = os.path.join(work_dir, 'audio')
    chunks_dir = os.path.join(work_dir, 'chunks')
    trans_dir = os.path.join(work_dir, 'transcriptions')
    output_dir = "/home/keith/youtube_transcriber/attachments"
    
    os.makedirs(audio_dir, exist_ok=True)
    
    # Workflow
    audio_path = os.path.join(audio_dir, 'audio.mp3')
    
    if not download_audio_fast(url, audio_path):
        sys.exit(1)
    
    chunks = chunk_audio_fast(audio_path, chunks_dir)
    if not chunks:
        sys.exit(1)
    
    results = transcribe_chunks_parallel(chunks_dir, trans_dir, language, engine)
    if not results:
        print("Error: No transcription generated")
        sys.exit(1)
    
    combined = combine_transcriptions(trans_dir)
    if not combined.strip():
        print("Error: Empty transcription")
        sys.exit(1)
    
    generate_summary(combined, language, output_dir, url)
    
    # Cleanup
    import shutil
    shutil.rmtree(work_dir, ignore_errors=True)
    
    print("\nDone! Check /home/keith/youtube_transcriber/attachments/")

if __name__ == '__main__':
    main()
