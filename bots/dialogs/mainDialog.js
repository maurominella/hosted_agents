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

        // === OAUTH CONNECTION FLOW (Teams SSO) — DISABLED ===
        // Kept as a reference: to re-enable the user-token flow
        // (e.g. to obtain the "third token" / user assertion via OAuth
        // Connection) uncomment this OAuthPrompt and re-add promptStep
        // in the WaterfallDialog below. Remember to configure the
        // correct connection scope (NO longer ai.azure.com for token B).
        // this.addDialog(
        //     new OAuthPrompt(OAUTH_PROMPT, {
        //         connectionName: process.env.connectionName,
        //         text: 'Per favore accedi per continuare',
        //         title: 'Accedi',
        //         timeout: 300000
        //     })
        // );

        this.addDialog(
            new WaterfallDialog(WATERFALL, [
                // this.promptStep.bind(this), // <-- uncomment to re-enable the OAuthPrompt
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

    // 1) [DISABLED] Starts the OAuthPrompt: with Teams SSO the token arrives
    //    silently. Re-enable it together with the OAuthPrompt in the constructor.
    // async promptStep(stepContext) {
    //     // Save the user's text to use it after login.
    //     stepContext.values.userText = stepContext.options.userText;
    //     return await stepContext.beginDialog(OAUTH_PROMPT);
    // }

    // 2) Call Foundry with the app-only token (NO user sign-in).
    async callStep(stepContext) {
        // === [DISABLED] Retrieval of the user-token via OAuthPrompt ===
        // With the OAuth Connection flow re-enabled, the user token would
        // arrive here (stepContext.result). It would be used as the "third
        // token" (user assertion) to forward to Foundry in a custom header.
        // const tokenResponse = stepContext.result;
        // if (!tokenResponse || !tokenResponse.token) {
        //     await stepContext.context.sendActivity('Login non riuscito, riprova.');
        //     return await stepContext.endDialog();
        // }
        //
        // // --- TEMPORARY LOG: user-token claims (aud, name, oid, scp) ---
        // try {
        //     const payload = JSON.parse(
        //         Buffer.from(tokenResponse.token.split('.')[1], 'base64').toString('utf8')
        //     );
        //     console.log('--- TOKEN CLAIMS ---');
        //     console.log('aud :', payload.aud);
        //     console.log('name:', payload.name);
        //     console.log('upn :', payload.upn || payload.preferred_username);
        //     console.log('oid :', payload.oid);
        //     console.log('scp :', payload.scp);
        //     console.log('appid:', payload.appid || payload.azp);
        // } catch (e) {
        //     console.log('Impossibile decodificare il token:', e.message);
        // }

        // Without OAuthPrompt, callStep is the FIRST step of the waterfall:
        // the user's text arrives from stepContext.options.
        const userText = stepContext.options.userText || 'hello';
        try {
            // Token B: app-only (aud=https://ai.azure.com) signed by the dedicated SP.
            // The OAuthPrompt user token is no longer used here: it will serve
            // as the "third token" (user assertion) for the downstream OBO.
            const foundryToken = (await foundryCredential.getToken('https://ai.azure.com/.default')).token;
            const { answer, user } = await callFoundry(foundryToken, userText);
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