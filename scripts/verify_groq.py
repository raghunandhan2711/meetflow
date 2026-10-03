"""Check the configured credential without printing secrets or provider bodies."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import httpx
from app.config import settings

try:
    with httpx.Client(timeout=10) as client:
        response = client.get('https://api.groq.com/openai/v1/models',
                              headers={'Authorization': 'Bearer ' + settings.groq_api_key})
    if response.status_code != 200:
        print(f'Groq credential check returned HTTP {response.status_code}. Secret and response body withheld.')
        sys.exit(1)
    models = {model['id'] for model in response.json().get('data', [])}
    print('Groq credential accepted. Configured analysis model available:', settings.groq_model in models)
    if settings.groq_model not in models:
        print('Available model IDs:', ', '.join(sorted(models)))
except httpx.RequestError:
    print('Groq credential check could not reach the provider. Secret withheld.')
    sys.exit(2)
