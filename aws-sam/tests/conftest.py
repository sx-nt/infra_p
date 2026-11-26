import os
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path[:0] = [str(HERE.parent / "functions"), str(HERE)]

# Credenciais fictícias: os testes nunca falam com a AWS real.
os.environ.update(
    AWS_ACCESS_KEY_ID="testing",
    AWS_SECRET_ACCESS_KEY="testing",
    AWS_SECURITY_TOKEN="testing",
    AWS_SESSION_TOKEN="testing",
    AWS_REGION="us-east-1",
    AWS_DEFAULT_REGION="us-east-1",
)
for name in ("LOCAL_DEV_USER", "SENDER_EMAIL", "APP_URL"):
    os.environ.pop(name, None)
os.environ["ADMIN_EMAILS"] = "coordenacao@classly.test"
