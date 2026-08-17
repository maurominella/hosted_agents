assertion = context.client_headers.get("x-client-user-token")

tenant = os.environ.get("APP_OBO_TENANT_ID")
client_id = os.environ.get("APP_OBO_CLIENT_ID")
client_secret = os.environ.get("APP_OBO_CLIENT_SECRET")

GRAPH_SCOPES = ["https://graph.microsoft.com/Files.Read"]
app = msal.ConfidentialClientApplication(
    client_id,
    authority=f"https://login.microsoftonline.com/{tenant}",
    client_credential=client_secret,
)
result = app.acquire_token_on_behalf_of(
    user_assertion=user_assertion, scopes=GRAPH_SCOPES
)
if "access_token" not in result:
    return (
        f"[graph] OBO failed: {result.get('error')}: "
        f"{str(result.get('error_description', ''))[:300]}"
    )
# One-shot Graph call: list OneDrive root children, pick the biggest folder.
resp = requests.get(
    GRAPH_ROOT_CHILDREN,
    headers={"Authorization": f"Bearer {result['access_token']}"},
    timeout=30,
)
