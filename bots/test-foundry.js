// TEST A - Fase 1: chiamare il Foundry Hosted Agent con SOLO l'app token.
// Scopo: confermare endpoint, audience del token e formato della risposta.
const { execSync } = require('child_process');
const axios = require('axios');

// --- Config dell'agent (dal portale Foundry) ---
const PROJECT_ENDPOINT = 'https://foundry7159.services.ai.azure.com/api/projects/aif7159-standard-agent-project';
const AGENT_NAME = 'ha01-echoagent';

// API version richiesta dall'endpoint responses (la stessa che usi nel tuo REST client)
const API_VERSION = '2025-11-15-preview';

// Endpoint del protocollo "responses" (compatibile OpenAI) + api-version
const url = `${PROJECT_ENDPOINT}/agents/${AGENT_NAME}/endpoint/protocols/openai/responses?api-version=${API_VERSION}`;

// 1) Ottengo un APP token (machine-to-machine) per la tua identità az.
//    Audience tipica del data-plane Foundry: https://ai.azure.com
const APP_TOKEN = execSync(
    'az account get-access-token --scope https://ai.azure.com/.default --query accessToken -o tsv'
).toString().trim();

(async () => {
    try {
        // Costruisco gli header. Aggiungo x-ms-user-token SOLO se fornito
        // via variabile d'ambiente USER_TOKEN, così posso confrontare i due casi.
        const headers = {
            Authorization: `Bearer ${APP_TOKEN}`,
            'Content-Type': 'application/json'
        };
        if (process.env.USER_TOKEN) {
            headers['x-ms-user-token'] = process.env.USER_TOKEN;
            console.log('>> Invio ANCHE header x-ms-user-token');
        } else {
            console.log('>> Nessun x-ms-user-token (solo Authorization)');
        }

        const res = await axios.post(
            url,
            {
                // Corpo "responses": solo input in linguaggio naturale
                input: 'ciao dal test A'
            },
            { headers }
        );

        console.log('=== SUCCESSO ===');
        console.log('HTTP status:', res.status);
        console.log('Campo "user" nella risposta:', JSON.stringify(res.data.user));
        console.log('Testo agent:', res.data.output?.[0]?.content?.[0]?.text);
    } catch (err) {
        console.log('=== ERRORE ===');
        if (err.response) {
            // Il server ha risposto con un errore: questo ci INSEGNA cosa correggere
            console.log('HTTP status:', err.response.status);
            console.log('Corpo errore:');
            console.log(JSON.stringify(err.response.data, null, 2));
        } else {
            console.log(err.message);
        }
    }
})();
