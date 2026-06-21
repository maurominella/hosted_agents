const {
    ComponentDialog,
    OAuthPrompt,
    WaterfallDialog,
    DialogSet,
    DialogTurnStatus
} = require('botbuilder-dialogs');
const { callFoundry } = require('../foundry');

const MAIN_DIALOG = 'MainDialog';
const OAUTH_PROMPT = 'OAuthPrompt';
const WATERFALL = 'WaterfallDialog';

// Dialog che: 1) ottiene il token utente via OAuthPrompt (Teams SSO),
//             2) chiama Foundry con quel token.
class MainDialog extends ComponentDialog {
    constructor() {
        super(MAIN_DIALOG);

        this.addDialog(
            new OAuthPrompt(OAUTH_PROMPT, {
                connectionName: process.env.connectionName,
                text: 'Per favore accedi per continuare',
                title: 'Accedi',
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

    // Entry point chiamato dal bot ad ogni turno.
    async run(context, accessor, userText) {
        const dialogSet = new DialogSet(accessor);
        dialogSet.add(this);

        const dialogContext = await dialogSet.createContext(context);
        const results = await dialogContext.continueDialog();
        if (results.status === DialogTurnStatus.empty) {
            // Passo il testo dell'utente come opzione del dialog.
            await dialogContext.beginDialog(this.id, { userText });
        }
    }

    // 1) Avvia l'OAuthPrompt: con Teams SSO il token arriva in modo silenzioso.
    async promptStep(stepContext) {
        // Conservo il testo dell'utente per usarlo dopo il login.
        stepContext.values.userText = stepContext.options.userText;
        return await stepContext.beginDialog(OAUTH_PROMPT);
    }

    // 2) Ho il token: chiamo Foundry come quell'utente.
    async callStep(stepContext) {
        const tokenResponse = stepContext.result;
        if (!tokenResponse || !tokenResponse.token) {
            await stepContext.context.sendActivity('Login non riuscito, riprova.');
            return await stepContext.endDialog();
        }

        // --- LOG TEMPORANEO: decodifico i claim del token per verificare
        //     che sia il TUO token utente (aud, nome, oid, scope). ---
        try {
            const payload = JSON.parse(
                Buffer.from(tokenResponse.token.split('.')[1], 'base64').toString('utf8')
            );
            console.log('--- TOKEN CLAIMS ---');
            console.log('aud :', payload.aud);
            console.log('name:', payload.name);
            console.log('upn :', payload.upn || payload.preferred_username);
            console.log('oid :', payload.oid);
            console.log('scp :', payload.scp);
            console.log('appid:', payload.appid || payload.azp);
        } catch (e) {
            console.log('Impossibile decodificare il token:', e.message);
        }

        const userText = stepContext.values.userText || 'ciao';
        try {
            const { answer, user } = await callFoundry(tokenResponse.token, userText);
            await stepContext.context.sendActivity(
                `Foundry (utente: ${user || 'n/d'}):\n${answer}`
            );
        } catch (err) {
            console.error('[callFoundry]', err.response?.status, err.response?.data || err.message);
            await stepContext.context.sendActivity(
                `Errore chiamando Foundry: ${err.response?.status || ''} ${err.message}`
            );
        }
        return await stepContext.endDialog();
    }
}

module.exports = { MainDialog };
