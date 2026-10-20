# Delta Crypto Scanner — Website Starter

This project adapts the existing observation-only Delta Exchange India scanner into a Streamlit web dashboard. It uses public candle data and does not place orders or require exchange API keys.

## Deploy free with Streamlit Community Cloud

1. Extract this ZIP.
2. Create/sign in to a GitHub account and create a **private or public repository** named `delta-crypto-scanner`.
3. Upload `app.py` and `requirements.txt` to the repository (repository root).
4. Open https://share.streamlit.io/ and connect GitHub.
5. Choose the repository, branch `main`, and main file path `app.py`; deploy.
6. Open the generated app link and check its timestamp, scan count and results against your Colab dashboard.

## Important limitations

- This starter has not yet been deployed or verified against live hosted API results. Validate it against the working Colab notebook before relying on it.
- Free hosting can sleep, restart, rate-limit, or change its policies. Browser refresh is not a guarantee of uninterrupted 24/7 background execution.
- This app fetches public market candles only. It does not place orders and does not ask for exchange credentials.
- Signals are screening outputs, not predictions or guarantees of profitability.
- Keep your original Colab notebook as a backup.
