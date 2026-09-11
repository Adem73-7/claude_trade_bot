import os
import requests
import asyncio
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# --- CONFIGURATION ENVIROMENT ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID_ALERTS = os.getenv("CHAT_ID_ALERTS")  # Ton ID Telegram pour recevoir les alertes BTC

btc_last_price = None

# --- FONCTION DE SÉCURITÉ TOKEN ---
def check_token_security(chain: str, address: str) -> dict:
    """ Interroge GoPlus Security ou RugCheck selon la blockchain """
    if chain == "solana":
        try:
            res = requests.get(f"https://api.rugcheck.xyz/v1/tokens/{address}/report/summary", timeout=5)
            if res.status_code == 200:
                data = res.json()
                score = data.get("score", 0)
                risks = [r.get("name", "") for r in data.get("risks", [])]
                is_safe = score < 1000 and "Mint Authority Still Enabled" not in risks
                return {
                    "safe": is_safe,
                    "details": f"Score de risque : {score}/5000\nAlertes : {', '.join(risks[:3]) if risks else 'Aucune majeure'}"
                }
        except Exception:
            pass

    # Repli ou autres chains via GoPlus Security
    try:
        chain_ids = {"ethereum": "1", "bsc": "56", "base": "8453", "solana": "solana"}
        c_id = chain_ids.get(chain, "1")
        url = f"https://api.gopluslabs.io/api/v1/token_security/{c_id}?contract_addresses={address}"
        res = requests.get(url, timeout=5).json()
        result = res.get("result", {}).get(address.lower(), {})
        
        is_honeypot = result.get("is_honeypot") == "1"
        mintable = result.get("is_mintable") == "1"
        is_open_source = result.get("is_open_source") == "1"
        
        safe = not is_honeypot and not mintable
        return {
            "safe": safe,
            "details": f"Honeypot: {'OUI 🔴' if is_honeypot else 'NON 🟢'} | Mintable: {'OUI 🔴' if mintable else 'NON 🟢'}"
        }
    except Exception:
        return {"safe": True, "details": "Analyse de contrat non disponible"}

# --- ANALYSE DE MEMECOIN ---
def analyze_token(address: str) -> str:
    url = f"https://api.dexscreener.com/latest/dex/tokens/{address}"
    try:
        res = requests.get(url, timeout=5).json()
        pairs = res.get("pairs")
        if not pairs:
            return "❌ Token introuvable sur DexScreener. Vérifie l'adresse du contrat."
        
        pair = pairs[0]
        chain = pair.get("chainId", "unknown")
        name = pair.get("baseToken", {}).get("name", "Inconnu")
        symbol = pair.get("baseToken", {}).get("symbol", "N/A")
        price = pair.get("priceUsd", "0")
        liquidity = pair.get("liquidity", {}).get("usd", 0)
        fdv = pair.get("fdv", 0)
        volume_24h = pair.get("volume", {}).get("h24", 0)
        price_change_24h = pair.get("priceChange", {}).get("h24", 0)
        
        sec_info = check_token_security(chain, address)
        
        # Logique de Verdict
        if not sec_info["safe"] or liquidity < 5000:
            verdict = "🔴 **DANGER : SCAM OU LIQUIDITÉ TROP FAIBLE**"
            conseil = "Ne tradais pas ce token. Risque extrême de Rug Pull ou Honeypot."
        elif liquidity < 30000 or volume_24h < 10000:
            verdict = "🟡 **PRUDENCE : HIGH RISK**"
            conseil = "Liquidité moyenne. Si tu rentres, mets uniquement du capital jetable."
        else:
            verdict = "🟢 **POTENTIELLEMENT TRADABLE**"
            conseil = "Indicateurs de base sains. Vérifie la distribution des holders sur Bubble Maps."

        msg = (
            f"🔍 **Analyse : {name} (${symbol})**\n"
            f"Chain : `{chain.upper()}`\n\n"
            f"💰 **Prix** : ${price} ({price_change_24h}% / 24h)\n"
            f"💧 **Liquidité** : ${liquidity:,.0f}\n"
            f"📊 **Volume 24h** : ${volume_24h:,.0f}\n"
            f"🧢 **Market Cap (FDV)** : ${fdv:,.0f}\n\n"
            f"🛡️ **Sécurité On-Chain** :\n{sec_info['details']}\n\n"
            f"⚖️ **Verdict** : {verdict}\n"
            f"💡 **Conseil** : {conseil}\n\n"
            f"🔗 [Voir sur DexScreener]({pair.get('url')})\n"
            f"🫧 [Vérifier les Holders sur Bubble Maps](https://bubblemaps.io/{chain}/token/{address})"
        )
        return msg
    except Exception as e:
        return f"Erreur lors de l'analyse : {str(e)}"

# --- COMMANDES TELEGRAM ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.chat_id
    await update.message.reply_text(
        f"👋 Salut ! Je suis ton **Claude Trade Bot**.\n\n"
        f" Ton ID Telegram est : `{user_id}` (à conserver pour activer les alertes BTC).\n\n"
        f"📌 **Comment m'utiliser ?**\n"
        f"1. Envoie-moi simplement un **Contract Address (CA)** pour analyser un memecoin.\n"
        f"2. Pose-moi n'importe quelle question sur le trading ou tes idées d'entrée/sortie.",
        parse_mode="Markdown"
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    
    # Si le message ressemble à une adresse de contrat (longue chaîne alphanumérique)
    if len(text) >= 32 and not " " in text:
        await update.message.reply_text("🔎 Analyse du token en cours...")
        report = analyze_token(text)
        await update.message.reply_text(report, parse_mode="Markdown", disable_web_page_preview=True)
    else:
        # Réponse IA / Assistant Trade
        prompt_reply = (
            f"🤖 **Analyse Trading :**\n\n"
            f"Concernant ta demande : *\"{text}\"*\n\n"
            f"En trading de memecoins, garde toujours ces règles en tête :\n"
            f"• **Prends tes profits par paliers** (ex: retire ta mise initiale à +100%).\n"
            f"• Ne trade jamais sans vérifier la répartition de la supply sur Bubble Maps (si 1 seul wallet détient >10%, fuis).\n"
            f"• Si tu veux que j'analyse un token précis, envoie-moi directement son **Contract Address (CA)**."
        )
        await update.message.reply_text(prompt_reply, parse_mode="Markdown")

# --- SURVEILLANCE BITCOIN (ALERTES) ---
async def btc_monitor(app: Application):
    global btc_last_price
    while True:
        try:
            res = requests.get("https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT", timeout=5).json()
            current_price = float(res["price"])
            
            if btc_last_price and CHAT_ID_ALERTS:
                variation = ((current_price - btc_last_price) / btc_last_price) * 100
                if abs(variation) >= 2.0:  # Déclenche une alerte si la variation est >= 2%
                    direction = "🚀 **PUMP**" if variation > 0 else "🚨 **DUMP**"
                    msg = (
                        f"{direction} **Bitcoin Alert**\n\n"
                        f"Prix actuel : **${current_price:,.2f}**\n"
                        f"Mouvement : **{variation:+.2f}%** sur les dernières minutes !"
                    )
                    await app.bot.send_message(chat_id=CHAT_ID_ALERTS, text=msg, parse_mode="Markdown")
            
            btc_last_price = current_price
        except Exception:
            pass
        await asyncio.sleep(300) # Vérifie toutes les 5 minutes

# --- MAIN ---
def main():
    if not TELEGRAM_BOT_TOKEN:
        print("Erreur: TELEGRAM_BOT_TOKEN non configuré.")
        return

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Lancement de la boucle de surveillance BTC en arrière-plan
    loop = asyncio.get_event_loop()
    loop.create_task(btc_monitor(app))

    print("Bot démarré avec succès !")
    app.run_polling()

if __name__ == "__main__":
    main()
