const axios = require('axios');

// Chiama il Foundry Hosted Agent passando il TOKEN UTENTE (aud=ai.azure.com)
// ottenuto via Teams SSO. Cosi' Foundry "vede" lo stesso utente di Teams.
async function callFoundry(userToken, text) {
    const projectEndpoint = process.env.FOUNDRY_PROJECT_ENDPOINT;
    const agentName = process.env.FOUNDRY_AGENT_NAME;
    const apiVersion = process.env.FOUNDRY_API_VERSION;

    const url = `${projectEndpoint}/agents/${agentName}/endpoint/protocols/openai/responses?api-version=${apiVersion}`;

    const res = await axios.post(
        url,
        { input: text },
        {
            headers: {
                Authorization: `Bearer ${userToken}`,
                'Content-Type': 'application/json'
            }
        }
    );

    // Testo della risposta dell'agente
    const answer = res.data.output?.[0]?.content?.[0]?.text ?? '(nessun testo)';
    // Campo "user" come visto da Foundry (utile per verificare l'identita')
    const user = res.data.user ?? '';
    return { answer, user };
}

module.exports = { callFoundry };
