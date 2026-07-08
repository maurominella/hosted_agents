
import os
import ast
import msal       # On-Behalf-Of token exchange (Token C -> Microsoft Graph token)
import requests   # Microsoft Graph REST call

GRAPH_ROOT_CHILDREN = (
    "https://graph.microsoft.com/v1.0/me/drive/root/children"
    "?$select=name,size,folder&$top=200"
)


def token_exchange(user_assertion: str, scopes:list) -> str:
    app_obo_tenant_id = os.environ.get("APP_OBO_TENANT_ID")
    app_obo_client_id = os.environ.get("APP_OBO_CLIENT_ID")
    app_obo_client_secret = os.environ.get("APP_OBO_CLIENT_SECRET") # retrieved from Azure Key Vault in main.py
    if not (app_obo_tenant_id and app_obo_client_id and app_obo_client_secret):
        return (
            "[graph] OBO not configured "
            "(set APP_OBO_TENANT_ID / APP_OBO_CLIENT_ID / APP_OBO_CLIENT_SECRET)"
        )

    # Token D: App-OBO (confidential client) exchanges Token C for a Graph token.
    app = msal.ConfidentialClientApplication(
        app_obo_client_id,
        client_credential=app_obo_client_secret,
        authority=f"https://login.microsoftonline.com/{app_obo_tenant_id}",
    )
    result = app.acquire_token_on_behalf_of(
        user_assertion=user_assertion, scopes=scopes
    )
    if "access_token" not in result:
        return (
            f"[graph] OBO failed: {result.get('error')}: "
            f"{str(result.get('error_description', ''))[:300]}"
        )
    
    return result["access_token"]


def _human_size(num: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if num < 1024:
            return f"{num:.1f} {unit}"
        num /= 1024
    return f"{num:.1f} PB"


def onedrive_root_folders(user_assertion: str) -> list[dict]:
    """OBO-exchange the user assertion (Token C) for a Microsoft Graph token, then
    return the biggest folder in the user's OneDrive root. Returns a human-readable
    string and never raises (any failure is reported in the returned text)."""
    scopes = ast.literal_eval(
        os.environ.get("GRAPH_SCOPES", '["https://graph.microsoft.com/Files.Read"]')
    )
    token = token_exchange(user_assertion, scopes)  # Token D
    if token.startswith("[graph]"):  # token_exchange returns an error string on failure
        return token
    try:
        resp = requests.get(
            GRAPH_ROOT_CHILDREN,
            headers={"Authorization": f"Bearer {token}"},
            timeout=30,
        )
        if resp.status_code != 200:
            return f"[graph] /me/drive/root/children -> {resp.status_code}: {resp.text[:300]}"
        folders = [{"name": it["name"], "size": it["size"], "childCount": it["folder"]["childCount"]} for it in resp.json().get("value", []) if "folder" in it]
        if not folders:
            return "No folders found in the OneDrive root."
        return f"Here are the folders on your OneDrive root: {folders}"
        
    except Exception as e:  # noqa: BLE001 - report any failure as text, never crash the tool
        return f"[graph] error: {type(e).__name__}: {e}"