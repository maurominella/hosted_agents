const {
    ComponentDialog,
    OAuthPrompt,
    WaterfallDialog,
    DialogSet,
    DialogTurnStatus
} = require('botbuilder-dialogs');
const { ClientSecretCredential } = require('@azure/identity');
const { callFoundry } = require('../foundry');

// App-only credential (client credentials) of the service principal dedicated
// to Foundry access. Locally it uses client id + secret from .env; on Azure
// you can replace it with a Managed Identity (e.g. DefaultAzureCredential).
const foundryCredential = new ClientSecretCredential(
    process.env.FOUNDRY_ACCESS_TENANT_ID,
    process.env.FOUNDRY_ACCESS_CLIENT_ID,
    process.env.FOUNDRY_ACCESS_CLIENT_SECRET
);

const MAIN_DIALOG = 'MainDialog';
const OAUTH_PROMPT = 'OAuthPrompt';
const WATERFALL = 'WaterfallDialog';

// Dialog that: 1) gets the user token via OAuthPrompt (Teams SSO),
//              2) calls Foundry with that token.
class MainDialog extends ComponentDialog {
    constructor() {
        super(MAIN_DIALOG);

        // === OAUTH CONNECTION FLOW (Token C / user assertion) — ENABLED ===
        // OAuthPrompt against the dedicated OBO connection. With Teams SSO the
        // token arrives silently. Its result is the "third token" (Token C),
        // a delegated user token with aud=api://app-obo/<App-OBO-clientid>,
        // later forwarded to the agent in a custom header for the downstream OBO.
        this.addDialog(
            new OAuthPrompt(OAUTH_PROMPT, {
                connectionName: process.env.OBO_CONNECTION_NAME,
                // FALLBACK ONLY: with Teams SSO the token is exchanged silently and
                // this card is NEVER shown. These strings appear only if the SSO
                // token exchange fails (e.g. outside Teams, missing consent, or no
                // webApplicationInfo in the manifest).
                text: 'Please sign in to continue',
                title: 'Sign in',
                timeout: 300000
            })
        );

        this.addDialog(
            new WaterfallDialog(WATERFALL, [
                this.promptStep.bind(this),
                this.callStep.bind(this)
            ])
        );

        this.initialDialogId = WATERFALL;
    }

    // Entry point called by the bot on every turn.
    async run(context, accessor, userText) {
        const dialogSet = new DialogSet(accessor);
        dialogSet.add(this);

        const dialogContext = await dialogSet.createContext(context);
        const results = await dialogContext.continueDialog();
        if (results.status === DialogTurnStatus.empty) {
            // Pass the user's text as a dialog option.
            await dialogContext.beginDialog(this.id, { userText });
        }
    }

    // 1) Starts the OAuthPrompt against the OBO connection: with Teams SSO the
    //    token (Token C) arrives silently.
    async promptStep(stepContext) {
        // Save the user's text to use it after login.
        stepContext.values.userText = stepContext.options.userText;
        return await stepContext.beginDialog(OAUTH_PROMPT);
    }

    // 2) Retrieve Token C (user assertion) and call Foundry with Token B (app-only).
    async callStep(stepContext) {
        // === Retrieval of Token C (user assertion) via OAuthPrompt ===
        // The delegated user token arrives here (stepContext.result). It is the
        // "third token" (Token C, aud=api://app-obo/<App-OBO-clientid>) that will
        // be forwarded to the agent in a custom header for the downstream OBO.
        const tokenResponse = stepContext.result;
        if (!tokenResponse || !tokenResponse.token) {
            await stepContext.context.sendActivity('Sign-in failed, please try again.');
            return await stepContext.endDialog();
        }
        const userAssertion = tokenResponse.token; // Token C

        // --- TEMPORARY LOG: Token C claims (aud, name, oid, scp) ---
        try {
            const payload = JSON.parse(
                Buffer.from(userAssertion.split('.')[1], 'base64').toString('utf8')
            );
            console.log('--- TOKEN C CLAIMS (user assertion) ---');
            console.log('aud :', payload.aud);   // expected: api://app-obo/<App-OBO-clientid>
            console.log('name:', payload.name);
            console.log('upn :', payload.upn || payload.preferred_username);
            console.log('oid :', payload.oid);
            console.log('scp :', payload.scp);    // expected: access_as_user
            console.log('appid:', payload.appid || payload.azp);
        } catch (e) {
            console.log('Unable to decode Token C:', e.message);
        }

        // With promptStep first, the user's text was saved in stepContext.values.
        const userText = stepContext.values.userText || 'hello';
        try {
            // Token B: app-only (aud=https://ai.azure.com) signed by the dedicated SP.
            // Token C (userAssertion) is retrieved above and will be forwarded to
            // the agent in a custom header (next step: foundry.js) for the OBO.
            const foundryToken = (await foundryCredential.getToken('https://ai.azure.com/.default')).token;
            const { answer, user } = await callFoundry(foundryToken, userText, userAssertion);
            await stepContext.context.sendActivity(
                `Foundry (user: ${user || 'n/a'}):\n${answer}`
            );
        } catch (err) {
            console.error('[callFoundry] status:', err.response?.status);
            // Print the full body (the Foundry message explains which
            // permission/action is missing; the nested console output is truncated).
            console.error('[callFoundry] body:', JSON.stringify(err.response?.data, null, 2) || err.message);
            console.error('[callFoundry] message:', err.response?.data?.error?.message);
            await stepContext.context.sendActivity(
                `Error calling Foundry: ${err.response?.status || ''} ${err.message}`
            );
        }
        return await stepContext.endDialog();
    }
}

module.exports = { MainDialog };