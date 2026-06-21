// Test locale del bot SENZA server/tunnel/auth, usando il TestAdapter dell'SDK.
// Serve a verificare che la logica di estrazione del token funzioni.
const { TestAdapter } = require('botbuilder');
const { EchoBot } = require('./bot');

const bot = new EchoBot();

// Il TestAdapter simula un canale: gli passiamo la funzione del bot.
const adapter = new TestAdapter(async (context) => {
    await bot.run(context);
});

// Costruiamo a mano un'Activity "ricca": testo + un token dentro channelData.
const fakeActivity = {
    type: 'message',
    text: 'ciao con token',
    channelData: {
        userToken: 'FAKE-USER-TOKEN-123'   // <-- qui simuliamo il token utente
    }
};

(async () => {
    // Inviamo l'activity e stampiamo le risposte del bot.
    await adapter.send(fakeActivity);

    // Diamo un attimo agli handler asincroni e leggiamo le risposte in coda.
    setTimeout(() => {
        console.log('\n=== RISPOSTE DEL BOT ===');
        let reply;
        while ((reply = adapter.activityBuffer.shift())) {
            console.log(reply.text);
        }
    }, 300);
})();
