"""Make one real analysis request with a synthetic transcript; never print keys."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import services
from app.security import redact

transcript = ('Alex: We decided to delay the release until Friday. I will fix the login bug by Thursday.\n'
              'Sam: I will test the authentication module after Alex finishes.\n'
              'Alex: We agreed to use PostgreSQL for meeting history.')
try:
    result = services.analyze(transcript)
    assert result.summary and len(result.decisions) >= 1 and len(result.action_items) >= 2
    assert any(task.owner.casefold() == 'alex' for task in result.action_items)
    print(f'Live Groq analysis passed: summary, {len(result.decisions)} decisions, {len(result.action_items)} action items and owners.')
except Exception as error:
    print(redact(str(error)) if isinstance(error, ValueError) else 'Live analysis could not reach the provider. Secret withheld.')
    sys.exit(1)
