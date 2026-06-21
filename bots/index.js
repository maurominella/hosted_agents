// test with external URI using `devtunnel host -p 3978 --allow-anonymous`

// Carica le variabili dal file .env in process.env
require('dotenv').config();

const restify = require('restify');
const {
    CloudAdapter,
    ConfigurationServiceClientCredentialFactory,
    ConfigurationBotFrameworkAuthentication,
    MemoryStorage,
    ConversationState,
    UserState
} = require('botbuilder');

const { TeamsBot } = require('./bot');
const { MainDialog } = require('./dialogs/mainDialog');

// 1) Autenticazione: dice all'adapter quali sono le credenziali del bot
//    (App Id / Password). Le legge da .env.
const credentialsFactory = new ConfigurationServiceClientCredentialFactory({
    MicrosoftAppId: process.env.MicrosoftAppId,
    MicrosoftAppPassword: process.env.MicrosoftAppPassword,
    MicrosoftAppType: process.env.MicrosoftAppType,
    MicrosoftAppTenantId: process.env.MicrosoftAppTenantId
});

const botFrameworkAuthentication = new ConfigurationBotFrameworkAuthentication(
    {},
    credentialsFactory
);

// 2) Adapter: il "traduttore" tra le richieste HTTP in arrivo e il tuo bot.
const adapter = new CloudAdapter(botFrameworkAuthentication);

// Gestione errori: se qualcosa va storto, lo logghiamo.
adapter.onTurnError = async (context, error) => {
    console.error('[onTurnError]', error);
    await context.sendActivity('Si è verificato un errore nel bot.');
};

// 3) Stato: serve a OAuthPrompt per ricordare a che punto e' il login.
const memoryStorage = new MemoryStorage();
const conversationState = new ConversationState(memoryStorage);
const userState = new UserState(memoryStorage);

// 4) Dialog (OAuthPrompt + chiamata Foundry) e bot Teams.
const dialog = new MainDialog();
const bot = new TeamsBot(conversationState, userState, dialog);

// 4) Web server in ascolto.
const server = restify.createServer();
server.use(restify.plugins.bodyParser());

server.listen(process.env.PORT || 3978, () => {
    console.log(`\nBot in ascolto su http://localhost:${server.address().port}`);
    console.log('Endpoint messaggi: POST /api/messages');
});

// 5) L'endpoint che Teams/Copilot chiameranno.
server.post('/api/messages', async (req, res) => {
    // Passa la richiesta all'adapter, che poi invoca il bot.
    await adapter.process(req, res, (context) => bot.run(context));
});
