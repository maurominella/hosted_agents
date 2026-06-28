const axios = require('axios');

// Calls the Foundry Hosted Agent passing the Foundry access token
// (aud=ai.azure.com) in Authorization (Token B, app-only). Optionally forwards
// Token C (user assertion, aud=App-OBO) in a custom header that Foundry passes
// through to the agent for the downstream OBO.
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
    const headers = {
        Authorization: `Bearer ${foundryToken}`,
        'Content-Type': 'application/json'
    };

    // Token C (user assertion) in the custom header; Foundry passes it through to
    // the agent, which uses it as the OBO assertion to mint downstream tokens.
    const assertionHeader = process.env.FOUNDRY_USER_ASSERTION_HEADER;
    if (userAssertion && assertionHeader) {
        headers[assertionHeader] = userAssertion;
        console.log('user-assertion header:', assertionHeader, '(Token C forwarded)');
    }

    const res = await axios.post(
        url,
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
