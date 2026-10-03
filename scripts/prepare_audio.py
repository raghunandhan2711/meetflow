"""Download the local Whisper model and transcribe a real test recording."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
from app.config import settings
from app.services import whisper, transcribe

settings.transcription_provider = 'local'
settings.diarization_enabled = False
print('Preparing local faster-Whisper model...')
whisper()
audio = ROOT / 'tests' / 'fixtures' / 'meeting.wav'
if audio.exists():
    transcript, segments, duration = transcribe(audio)
    (ROOT / 'artifacts').mkdir(exist_ok=True)
    (ROOT / 'artifacts' / 'transcription-result.txt').write_text(transcript,encoding='utf-8')
    print(f'Transcribed {duration:.1f}s into {len(segments)} timestamped segments.')
    print(transcript)
    if not any(word in transcript.casefold() for word in ['meeting','release','login']):
        raise RuntimeError('Transcription did not capture expected speech.')
