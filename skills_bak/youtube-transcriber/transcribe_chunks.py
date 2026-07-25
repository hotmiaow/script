#!/usr/bin/env python3
"""
Transcribe audio chunks using apple-speech
Usage: transcribe_chunks.py <chunk_dir> <trans_dir> <language>
"""

import sys
import os
import subprocess
import json

def transcribe_file(audio_path, language):
    """Transcribe a single audio file using apple-speech"""
    try:
        # Map language codes
        lang_map = {
            'en': 'en-US',
            'zh': 'zh-TW'  # Traditional Chinese
        }
        lang = lang_map.get(language, 'en-US')
        
        # Run apple-speech transcribe
        result = subprocess.run(
            ['apple-speech', 'transcribe', '--source', audio_path, '--language', lang, '-q'],
            capture_output=True,
            text=True,
            timeout=300  # 5 minute timeout per chunk
        )
        
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
        else:
            # Try without language specification
            result2 = subprocess.run(
                ['apple-speech', 'transcribe', '--source', audio_path, '-q'],
                capture_output=True,
                text=True,
                timeout=300
            )
            if result2.returncode == 0 and result2.stdout.strip():
                return result2.stdout.strip()
        
        return ""
    except Exception as e:
        print(f"Error transcribing {audio_path}: {e}")
        return ""

def main():
    if len(sys.argv) < 3:
        print("Usage: transcribe_chunks.py <chunk_dir> <trans_dir> <language>")
        sys.exit(1)
    
    chunk_dir = sys.argv[1]
    trans_dir = sys.argv[2]
    language = sys.argv[3] if len(sys.argv) > 3 else 'en'
    
    os.makedirs(trans_dir, exist_ok=True)
    
    # Get all audio files
    audio_files = sorted([f for f in os.listdir(chunk_dir) if f.endswith('.mp3') or f.endswith('.m4a')])
    
    if not audio_files:
        print("No audio files found")
        sys.exit(1)
    
    print(f"Found {len(audio_files)} audio chunk(s) to transcribe")
    
    for i, audio_file in enumerate(audio_files, 1):
        audio_path = os.path.join(chunk_dir, audio_file)
        trans_file = audio_file.replace('.mp3', '.txt').replace('.m4a', '.txt')
        trans_path = os.path.join(trans_dir, trans_file)
        
        print(f"  Transcribing chunk {i}/{len(audio_files)}: {audio_file}")
        
        # Transcribe
        text = transcribe_file(audio_path, language)
        
        if text:
            with open(trans_path, 'w', encoding='utf-8') as f:
                f.write(text)
            print(f"    ✓ Saved: {trans_file}")
        else:
            print(f"    ✗ Failed: {audio_file}")
    
    print("Transcription complete!")

if __name__ == '__main__':
    main()
