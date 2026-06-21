const { TeamsActivityHandler } = require('botbuilder');

// Bot per Teams: oltre ai messaggi normali, deve gestire gli "invoke"
// dell'SSO (signin/tokenExchange e signin/verifyState) che Teams invia
// durante lo scambio silenzioso del token. Per questo estende
// TeamsActivityHandler invece del semplice ActivityHandler.
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
                    await context.sendActivity('Ciao! Scrivimi qualcosa e lo invierò a Foundry come te.');
                }
            }
            await next();
        });
    }

    // Salva lo stato al termine di OGNI turno (anche invoke).
    async run(context) {
        await super.run(context);
        await this.conversationState.saveChanges(context, false);
        await this.userState.saveChanges(context, false);
    }

    // Teams invia questi invoke con il token SSO: l'OAuthPrompt lo scambia.
    async handleTeamsSigninVerifyState(context, query) {
        await this.dialog.run(context, this.dialogState);
    }

    async handleTeamsSigninTokenExchange(context, query) {
        await this.dialog.run(context, this.dialogState);
    }
}

module.exports = { TeamsBot };
