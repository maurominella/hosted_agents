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
    const headers = {
        Authorization: `Bearer ${foundryToken}`,
        'Content-Type': 'application/json'
    };

    // Foundry enforces the OpenAI metadata limit (max 512 chars per value, up to
    // 16 keys). A JWT is longer, so the user assertion (Token C) is split into
    // chunks the agent reassembles. Keys: ua_n (chunk count) + ua_0..ua_{n-1}.
    // The adapter exposes metadata to the agent as self._request_headers.
    const metadata = {};
    if (userAssertion) {
        const SIZE = 500; // stay safely under the 512-char metadata value cap
        const n = Math.ceil(userAssertion.length / SIZE);
        metadata.ua_n = String(n);
        for (let i = 0; i < n; i++) {
            metadata[`ua_${i}`] = userAssertion.slice(i * SIZE, (i + 1) * SIZE);
        }
        console.log(`user assertion in metadata: Token C len=${userAssertion.length} in ${n} chunk(s)`);
    }

    const res = await axios.post(
        url,
        { input: text, metadata },
        { headers }
    );

    // Text of the agent's response
    const answer = res.data.output?.[0]?.content?.[0]?.text ?? '(no text)';
    // "user" field as seen by Foundry (useful to verify the identity)
    const user = res.data.user ?? '';
    return { answer, user };
}

module.exports = { callFoundry };
