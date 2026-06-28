const { TeamsActivityHandler } = require('botbuilder');

// Teams bot: besides normal messages, it must handle the SSO "invoke"
// activities (signin/tokenExchange and signin/verifyState) that Teams sends
// during the silent token exchange. That is why it extends
// TeamsActivityHandler instead of the plain ActivityHandler.
class TeamsBot extends TeamsActivityHandler {
    constructor(conversationState, userState, dialog) {
        super();
        this.conversationState = conversationState;
        this.userState = userState;
        this.dialog = dialog;
        this.dialogState = conversationState.createProperty('DialogState');

        this.onMessage(async (context, next) => {
            await this.dialog.run(context, this.dialogState, context.activity.text);
            await next();
        });

        this.onMembersAdded(async (context, next) => {
            for (const member of context.activity.membersAdded) {
                if (member.id !== context.activity.recipient.id) {
                    await context.sendActivity('Hello! Write me something and I will send it to Foundry as you.');
                }
            }
            await next();
        });
    }

    // Save the state at the end of EVERY turn (including invokes).
    async run(context) {
        await super.run(context);
        await this.conversationState.saveChanges(context, false);
        await this.userState.saveChanges(context, false);
    }

    // Teams sends these invokes with the SSO token: the OAuthPrompt exchanges it.
    async handleTeamsSigninVerifyState(context, query) {
        await this.dialog.run(context, this.dialogState);
    }

    async handleTeamsSigninTokenExchange(context, query) {
        // TEMPORARY LOG: raw Teams SSO token (expected aud = api://bot-<appId>)
        try {
            const t = query?.token || context.activity?.value?.token;
            if (t) {
                const p = JSON.parse(Buffer.from(t.split('.')[1], 'base64').toString('utf8'));
                console.log('--- SSO TOKEN IN INGRESSO (Teams) ---');
                console.log('aud  :', p.aud);
                console.log('scp  :', p.scp);
                console.log('appid:', p.appid || p.azp);
                console.log('upn  :', p.upn || p.preferred_username);
            }
        } catch (e) {
            console.log('Unable to decode the SSO token:', e.message);
        }
        await this.dialog.run(context, this.dialogState);
    }
}

module.exports = { TeamsBot };
