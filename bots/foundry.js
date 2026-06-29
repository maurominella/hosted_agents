const axios = require('axios');

// Calls the Foundry Hosted Agent passing the Foundry access token
// (aud=ai.azure.com) in Authorization (Token B, app-only). Forwards Token C
// (user assertion, aud=App-OBO) in the request body "metadata" — Foundry strips
// HTTP headers, so metadata is the channel the agent reads for the downstream OBO.
async function callFoundry(foundryToken, text, userAssertion) {
    const projectEndpoint = process.env.FOUNDRY_AGENT_PROJECT_ENDPOINT;
    const agentName = process.env.FOUNDRY_AGENT_NAME;
    const apiVersion = process.env.FOUNDRY_AGENT_API_VERSION;

    const url = `${projectEndpoint}/agents/${agentName}/endpoint/protocols/openai/responses?api-version=${apiVersion}`;

    // TEMPORARY LOG: invoked endpoint and identity of the outgoing token
    try {
        const p = JSON.parse(Buffer.from(foundryToken.split('.')[1], 'base64').toString('utf8'));
        console.log('--- FOUNDRY CALL (responses) ---');
        console.log('url  :', url);
        console.log('aud  :', p.aud);            // expected: https://ai.azure.com
        console.log('appid:', p.appid || p.azp); // expected: FOUNDRY_ACCESS_CLIENT_ID
        console.log('idtyp:', p.idtyp);          // 'app' = app-only token
    } catch (e) {
        console.log('Unable to decode the foundryToken:', e.message);
    }

    // Token B (app-only) in Authorization; Foundry validates it for RBAC and strips it.
    // Token C (user assertion) travels in the custom header "x-client-user-token",
    // which Foundry forwards to the agent container as-is (no chunking needed).
    const headers = {
        Authorization: `Bearer ${foundryToken}`,
        'Content-Type': 'application/json'
    };
    if (userAssertion) {
        headers['x-client-user-token'] = userAssertion;
        console.log(`user assertion in header x-client-user-token: Token C len=${userAssertion.length}`);
    }

    const res = await axios.post(
        url, // "http://localhost:8088/responses?api-version=2025-11-15-preview"
        { input: text },
        { headers }
    );

    // Text of the agent's response
    const answer = res.data.output?.[0]?.content?.[0]?.text ?? '(no text)';
    // "user" field as seen by Foundry (useful to verify the identity)
    const user = res.data.user ?? '';
    return { answer, user };
}

module.exports = { callFoundry };
