
import os
import msal       # On-Behalf-Of token exchange (Token C -> Microsoft Graph token)


def get_token_obo(user_assertion: str, scopes:list) -> str:
    tenant_id = os.environ.get("APP_OBO_TENANT_ID")
    client_id = os.environ.get("APP_OBO_CLIENT_ID")
    client_secret = os.environ.get("APP_OBO_CLIENT_SECRET")
    if not (tenant_id and client_id and client_secret):
        return (
            "[graph] OBO not configured "
            "(set APP_OBO_TENANT_ID / APP_OBO_CLIENT_ID / APP_OBO_CLIENT_SECRET)"
        )

    # Token D: App-OBO (confidential client) exchanges Token C for a Graph token.
    app = msal.ConfidentialClientApplication(
        client_id,
        client_credential=client_secret,
        authority=f"https://login.microsoftonline.com/{tenant_id}",
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