"""Fail safely if the real key appears in served assets or project source."""
import sys
from pathlib import Path
import re
from urllib.parse import urlsplit, unquote
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.config import ROOT, settings

secrets = [value.encode() for value in [settings.groq_api_key, settings.jira_api_token, settings.hf_token] if value]
password = urlsplit(settings.database_url).password
if password:
    secrets.append(unquote(password).encode())
files = [path for folder in ['app', 'static', 'scripts', 'tests', 'migrations', 'docs'] for path in (ROOT / folder).rglob('*')
         if path.is_file() and '__pycache__' not in path.parts and path.suffix in {'.py','.js','.mjs','.html','.css','.svg','.ps1','.sql','.md'}]
files += [ROOT / name for name in ['.env.example','README.md','API_KEYS.md','PROJECT_NOTES.md','package.json','package-lock.json','docker-compose.yml']]
pattern = re.compile(rb'(?:gsk_[A-Za-z0-9]{24,}|ATATT3[A-Za-z0-9_=-]{40,}|gh[pousr]_[A-Za-z0-9]{30,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----)')
exposed = sum(any(secret in path.read_bytes() for secret in secrets if len(secret) >= 8) or bool(pattern.search(path.read_bytes())) for path in files)
if exposed:
    raise SystemExit(f'Secret exposure check failed in {exposed} files. Values withheld.')
print(f'Secret exposure check passed across {len(files)} source, asset and documentation files.')
