// test with external URI using `devtunnel host -p 3978 --allow-anonymous`

// Load the variables from the .env file into process.env
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

// 1) Authentication: tells the adapter what the bot credentials are
//    (App Id / Password). It reads them from .env.
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

// 2) Adapter: the "translator" between incoming HTTP requests and your bot.
const adapter = new CloudAdapter(botFrameworkAuthentication);

// Error handling: if something goes wrong, we log it.
adapter.onTurnError = async (context, error) => {
    console.error('[onTurnError]', error);
    await context.sendActivity('Si è verificato un errore nel bot.');
};

// 3) State: needed by OAuthPrompt to remember where the login is.
const memoryStorage = new MemoryStorage();
const conversationState = new ConversationState(memoryStorage);
const userState = new UserState(memoryStorage);

// 4) Dialog (OAuthPrompt + Foundry call) and Teams bot.
const dialog = new MainDialog();
const bot = new TeamsBot(conversationState, userState, dialog);

// 4) Web server listening.
const server = restify.createServer();
server.use(restify.plugins.bodyParser());

server.listen(process.env.PORT || 3978, () => {
    console.log(`\nBot is listening on http://localhost:${server.address().port}`);
    console.log('Message endpoint: POST /api/messages');
});

// 5) The endpoint that Teams/Copilot will call.
server.post('/api/messages', async (req, res) => {
    // Pass the request to the adapter, which then invokes the bot.
    await adapter.process(req, res, (context) => bot.run(context));
});
