#!/usr/bin/env python3
"""
YouTube Audio Transcriber - Complete workflow
Usage: python3 youtube_transcriber.py <URL> [language]
"""

import sys
import os
import subprocess
import re
import json
from datetime import datetime

def sanitize_filename(text):
    """Remove special characters from filename"""
    text = re.sub(r'[<>:"/\\|?*]', '', text)
    text = re.sub(r'[^a-zA-Z0-9\u4e00-\u9fff_\-]', '_', text)
    text = re.sub(r'_+', '_', text)
    text = text.strip('_')
    return text[:100] if len(text) > 100 else text

def download_audio(url, output_path):
    """Download YouTube video and extract audio"""
    print("[1/6] Downloading video and extracting audio...")
    
    # Download video (no format selection = best available)
    result = subprocess.run([
        'yt-dlp', '--no-mtime',
        '-o', output_path + '.video', url
    ], capture_output=True, text=True)
    
    if result.returncode != 0:
        print(f"Error downloading: {result.stderr}")
        return False
    
    video_file = output_path + '.video'
    if not os.path.exists(video_file):
        print("Error: Video file not created")
        return False
    
    # Extract audio
    print("Extracting audio...")
    result = subprocess.run([
        'ffmpeg', '-y', '-i', video_file,
        '-vn', '-acodec', 'libmp3lame', '-ab', '192k',
        output_path + '.mp3'
    ], capture_output=True, text=True)
    
    os.remove(video_file)
    
    if result.returncode != 0 or not os.path.exists(output_path + '.mp3'):
        print("Error extracting audio")
        return False
    
    print("✓ Audio downloaded successfully")
    return True

def chunk_audio(audio_path, chunks_dir, chunk_duration=300):
    """Split audio into chunks"""
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
    print(f"Audio duration: {int(duration)} seconds")
    
    if duration > chunk_duration:
        num_chunks = int((duration + chunk_duration - 1) / chunk_duration)
        print(f"Splitting into {num_chunks} chunks...")
        
        result = subprocess.run([
            'ffmpeg', '-y', '-i', audio_path,
            '-f', 'segment', '-segment_time', str(chunk_duration),
            '-c', 'copy',
            os.path.join(chunks_dir, 'chunk_%03d.mp3')
        ], capture_output=True, text=True)
    else:
        print("Audio is short enough, no chunking needed")
        import shutil
        shutil.copy(audio_path, os.path.join(chunks_dir, 'chunk_000.mp3'))
    
    chunks = sorted([f for f in os.listdir(chunks_dir) if f.endswith('.mp3')])
    print(f"Created {len(chunks)} audio chunk(s)")
    return chunks

def transcribe_chunks(chunks_dir, trans_dir, language):
    """Transcribe all chunks"""
    print("[3/6] Transcribing audio chunks...")
    
    os.makedirs(trans_dir, exist_ok=True)
    
    lang_map = {'en': 'en-US', 'zh': 'zh-TW'}
    lang = lang_map.get(language, 'en-US')
    
    chunks = sorted([f for f in os.listdir(chunks_dir) if f.endswith('.mp3')])
    
    for i, chunk_file in enumerate(chunks, 1):
        chunk_path = os.path.join(chunks_dir, chunk_file)
        trans_file = chunk_file.replace('.mp3', '.txt')
        trans_path = os.path.join(trans_dir, trans_file)
        
        print(f"  Transcribing chunk {i}/{len(chunks)}: {chunk_file}")
        
        result = subprocess.run([
            'apple-speech', 'transcribe',
            '--source', chunk_path,
            '--language', lang,
            '-q'
        ], capture_output=True, text=True, timeout=600)
        
        if result.returncode == 0 and result.stdout.strip():
            with open(trans_path, 'w', encoding='utf-8') as f:
                f.write(result.stdout.strip())
            print(f"    ✓ Saved: {trans_file}")
        else:
            # Try without language
            result2 = subprocess.run([
                'apple-speech', 'transcribe',
                '--source', chunk_path,
                '-q'
            ], capture_output=True, text=True, timeout=600)
            
            if result2.returncode == 0 and result2.stdout.strip():
                with open(trans_path, 'w', encoding='utf-8') as f:
                    f.write(result2.stdout.strip())
                print(f"    ✓ Saved: {trans_file}")
            else:
                print(f"    ✗ Failed: {chunk_file}")

def combine_transcriptions(trans_dir):
    """Combine all transcription files"""
    print("[4/6] Combining transcriptions...")
    
    trans_files = sorted([f for f in os.listdir(trans_dir) if f.endswith('.txt')])
    combined = ""
    
    for trans_file in trans_files:
        trans_path = os.path.join(trans_dir, trans_file)
        with open(trans_path, 'r', encoding='utf-8') as f:
            combined += f.read() + "\n"
    
    combined_path = os.path.join(trans_dir, 'combined.txt')
    with open(combined_path, 'w', encoding='utf-8') as f:
        f.write(combined)
    
    return combined

def generate_summary(combined_text, language, output_dir, url):
    """Generate summary and create markdown file"""
    print("[5/6] Generating summary...")
    
    paragraphs = [p.strip() for p in combined_text.split('\n\n') if p.strip()]
    
    # Generate summary
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
        summary = "## Summary\n\nKey points from this video:\n\n"
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
    
    # Get title from first line
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
    md_content += "\n\n---\n"
    md_content += f"*Generated by YouTube Transcriber Skill*\n"
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(md_content)
    
    print("[6/6] Complete!")
    print(f"Output file: {output_path}")
    return output_path

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 youtube_transcriber.py <URL> [language]")
        print("  language: en (default) or zh (Traditional Chinese)")
        sys.exit(1)
    
    url = sys.argv[1]
    language = sys.argv[2] if len(sys.argv) > 2 else 'en'
    
    print("=== YouTube Audio Transcriber ===")
    print(f"URL: {url}")
    print(f"Language: {language}")
    print()
    
    # Setup directories
    work_dir = f"/home/keith/youtube_transcriber/workspace/youtube_transcribe_{os.getpid()}"
    audio_dir = os.path.join(work_dir, 'audio')
    chunks_dir = os.path.join(work_dir, 'chunks')
    trans_dir = os.path.join(work_dir, 'transcriptions')
    output_dir = "/home/keith/youtube_transcriber/attachments"
    
    os.makedirs(audio_dir, exist_ok=True)
    
    # Execute workflow
    audio_path = os.path.join(audio_dir, 'audio.mp3')
    
    if not download_audio(url, audio_path):
        sys.exit(1)
    
    chunks = chunk_audio(audio_path, chunks_dir)
    if not chunks:
        sys.exit(1)
    
    transcribe_chunks(chunks_dir, trans_dir, language)
    combined = combine_transcriptions(trans_dir)
    
    if not combined.strip():
        print("Error: No transcription generated")
        sys.exit(1)
    
    output_path = generate_summary(combined, language, output_dir, url)
    
    # Cleanup
    import shutil
    shutil.rmtree(work_dir, ignore_errors=True)
    
    print()
    print("Done! Check /home/keith/youtube_transcriber/attachments/ for the markdown file.")

if __name__ == '__main__':
    main()
