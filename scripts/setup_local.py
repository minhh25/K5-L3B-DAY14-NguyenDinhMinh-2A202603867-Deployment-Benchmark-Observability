"""Create an ignored local .env once. Does not print the generated API key."""
import secrets
from pathlib import Path

root=Path(__file__).resolve().parents[1]
path=root/'06-lab-complete/.env'
if not path.exists():
    content=(root/'06-lab-complete/.env.example').read_text()
    content=content.replace('AGENT_API_KEY=\n','AGENT_API_KEY='+secrets.token_urlsafe(32)+'\n')
    path.write_text(content)
    path.chmod(0o600)
    print('Created 06-lab-complete/.env with a random local key; value omitted.')
else:
    print('Kept existing 06-lab-complete/.env.')
