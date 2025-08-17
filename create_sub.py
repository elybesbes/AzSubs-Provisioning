import sys
import json
import time
import uuid
import requests
from pathlib import Path
from authenticate import authenticate_with_secret

VARS_FILE = "variables.json"
API_ALIAS = "2021-10-01"

def create_subscription_alias(token, alias_name, display_name, billing_scope,
                              tenant_id, management_group_id, tags=None,
                              max_retries=6):
    url = f"https://management.azure.com/providers/Microsoft.Subscription/aliases/{alias_name}?api-version={API_ALIAS}"

    additional_props = {
        "subscriptionTenantId": tenant_id,
        "managementGroupId": management_group_id
    }
    if tags:
        additional_props["tags"] = tags

    body = {
        "properties": {
            "displayName": display_name,
            "workload": "Production",
            "billingScope": billing_scope,
            "additionalProperties": additional_props
        }
    }

    backoff = 30
    for attempt in range(1, max_retries + 1):
        print(f"[alias create] attempt {attempt} → PUT {url}")
        r = requests.put(
            url,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json=body,
            timeout=120
        )

        if r.status_code in (200, 201, 202):
            print("[alias create] accepted by Azure (200/201/202).")
            return

        if r.status_code == 403:
            raise SystemExit(
                "403 InsufficientPermissionsOnInvoiceSection:\n"
                "- Ensure the invoice section exists and matches the billing profile.\n"
                "- Grant your service principal 'Azure subscription creator' on that invoice section.\n"
                f"Response: {r.text}"
            )

        if r.status_code == 429:
            print(f"[alias create] 429 throttled, sleeping {backoff}s then retrying…")
            time.sleep(backoff)
            backoff = min(backoff * 2, 300)
            continue

        raise SystemExit(f"[alias create] {r.status_code} {r.text}")

    raise SystemExit("Exceeded max retries for alias creation after repeated 429s.")

def poll_alias_until_succeeded(token, alias_name, timeout=900, every=10):
    url = f"https://management.azure.com/providers/Microsoft.Subscription/aliases/{alias_name}?api-version={API_ALIAS}"
    start = time.time()
    print("[alias poll] Waiting for provisioning to complete…")
    while True:
        r = requests.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=60)
        r.raise_for_status()
        props = (r.json() or {}).get("properties", {}) or {}
        state = props.get("provisioningState")
        sub_id = props.get("subscriptionId")
        print(f"[alias poll] state={state}, subscriptionId={sub_id}")
        if state == "Succeeded" and sub_id:
            print(f"[alias poll] Subscription created: {sub_id}")
            return sub_id
        if state in ("Failed", "Canceled"):
            raise SystemExit(f"[alias poll] {state}: {r.text}")
        if time.time() - start > timeout:
            raise SystemExit(f"[alias poll] timeout, last state={state}")
        time.sleep(every)

def main():
    # --- 1) Read the dynamic name from CLI ---
    if len(sys.argv) < 2:
        raise SystemExit("Usage: python create_sub.py <NamePart>  (ex: python create_sub.py Marie)")
    name_part = sys.argv[1]
    dynamic_display_name = f"Sandbox-{name_part}"
    print(f"[start] dynamic display_name = {dynamic_display_name}")

    # --- 2) Load config ---
    if not Path(VARS_FILE).is_file():
        raise SystemExit(f"{VARS_FILE} not found in current folder.")
    with open(VARS_FILE, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    auth = cfg["auth"]
    billing = cfg["billing"]
    sub_cfg = cfg["subscription"]

    # --- 3) Authenticate ---
    token = authenticate_with_secret(auth["tenant_id"], auth["client_id"], auth["client_secret_value"])

    # --- 4) Build billing scope ---
    billing_scope = (
        f"/billingAccounts/{billing['billing_account']}"
        f"/billingProfiles/{billing['billing_profile']}"
        f"/invoiceSections/{billing['invoice_section']}"
    )
    print(f"[billing] scope = {billing_scope}")

    # --- 5) Resolve management group id ---
    mg_id = sub_cfg.get("management_group_id")
    if not mg_id:
        mg_name = sub_cfg["management_group_name"]
        # NOTE: check spelling of 'Sandboxes' vs 'Sanboxes'
        mg_id = f"/providers/Microsoft.Management/managementGroups/{mg_name}"
    print(f"[mg] management_group_id = {mg_id}")

    tags = sub_cfg.get("tags")

    # --- 6) Create alias (starts provisioning) ---
    alias_name = str(uuid.uuid4())
    print(f"[alias] creating '{alias_name}' for '{dynamic_display_name}' …")
    create_subscription_alias(
        token=token,
        alias_name=alias_name,
        display_name=dynamic_display_name,   # ← use dynamic name here
        billing_scope=billing_scope,
        tenant_id=auth["tenant_id"],
        management_group_id=mg_id,
        tags=tags
    )

    # --- 7) Poll until subscription is ready ---
    subscription_id = poll_alias_until_succeeded(token, alias_name)

    print(f"[done] Created subscription {subscription_id} and attached to MG. Goodbye!")

if __name__ == "__main__":
    main()
