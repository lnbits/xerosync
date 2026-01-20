Xero Sync Extension

LNbits -> Xero wallet sync. Push incoming LNbits payments into Xero as Bank
Transactions so your bookkeeping stays in sync.

Quick start

1. Create a Xero app (Web app) in the Xero Developer Portal.
2. Add your redirect URI: `https://<your-host>/xerosync/oauth/callback`
3. Paste the Client ID and Client Secret into the extension settings.
4. Connect your Xero account from the extension settings.
5. Create a wallet mapping and choose:
   - Revenue account (Reconcile mode)
   - Bank account (deposit target)
   - Tax treatment (optional)

Notes:

- Wallets must have a fiat currency enabled so LNbits can convert amounts.
- Transactions are created as Xero Bank Transactions (Receive Money).
