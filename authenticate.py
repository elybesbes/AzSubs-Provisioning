import json
import requests
from pathlib import Path

VARS_FILE = "variables.json"

def authenticate_with_secret(tenant_id: str, client_id: str, client_secret: str) -> str:
    
    url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/token"
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    data = {
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
        "resource": "https://management.azure.com/"
    }
    print(
        f"Authenticating with secret on Azure:\n"
        f"\tTenant ID: {tenant_id}\n"
        f"\tClient ID: {client_id}"
    )
    resp = requests.post(url, data=data, headers=headers, timeout=60)  # verify=True by default
    resp.raise_for_status()
    token = resp.json().get("access_token")
    if not token:
        raise RuntimeError(f"No access_token in response:\n{resp.text}")
    print("Authentication successful.")
    return token


if __name__ == "__main__":
    if not Path(VARS_FILE).is_file():
        raise SystemExit(f"{VARS_FILE} not found")
    with open(VARS_FILE, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    auth = cfg["auth"]
    token = authenticate_with_secret(auth["tenant_id"], auth["client_id"], auth["client_secret_value"])
    print("Auth OK — token (start):", token[:60] + "...")
