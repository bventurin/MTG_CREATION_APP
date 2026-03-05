# ⚡ AetherFlow – MTG Deck Builder

A web app for Magic: The Gathering players who want to build, manage, and improve their decks — with a little help from AI.

Built with Django, backed by AWS DynamoDB and Supabase, and deployed on AWS Elastic Beanstalk.

## What it does

**AetherFlow** lets you create MTG decks, browse card data pulled from [Scryfall](https://scryfall.com/), and get AI-powered recommendations to improve your builds. You can also generate QR codes to share your decks and add vouchers.

### Features

- 🃏 **Deck Builder** — Create, edit, and delete decks. Paste a deck list or build one card by card.
- 🤖 **AI Recommendations** — Uses Google Gemini to analyse your deck and suggest 3 cards that would improve it.
- 🧑🏽‍💻 **QR Code Sharing** — Generate a QR code for any deck so you can share it easily.
- 🎟️ **Vouchers** — Generate and attach vouchers to your decks, powered by an external voucher service.
- 🔐 **User Accounts** — Sign up, log in, and manage your own collection of decks.

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Django 6.0 (Python 3.12) |
| Database (Decks) | AWS DynamoDB |
| Database (Users) | Supabase (PostgreSQL) |
| AI | Google Gemini API (`google-genai`) |
| Card Data | Scryfall API → AWS S3 (synced via Lambda) |
| QR Codes | AWS Lambda + API Gateway |
| Vouchers | External API (third-party service) |
| Hosting | AWS Elastic Beanstalk |
| CI/CD | GitHub Actions |
| Monitoring | DataDog |

## Project Structure

```
├── core/               # Django project config (settings, URLs, WSGI)
├── deck_builder/       # Main app — decks, cards, views, templates
│   └── services/       # Scryfall S3, DynamoDB, QR code, voucher integrations
├── card_recommender/   # AI-powered deck improvement suggestions (Gemini)
├── accounts/           # User authentication (login, signup, logout)
├── assets/             # Static assets (CSS, JS, images)
├── .ebextensions/      # Elastic Beanstalk config
├── .github/workflows/  # CI/CD pipeline
└── manage.py
```

## Getting Started (Local Development)

### 1. Clone and set up your environment

```bash
git clone <your-repo-url>
cd "Magic Project"
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure environment variables

Create a `.env` file in the project root with:

```env
SECRET_KEY=your-django-secret-key
DEBUG=True
DATABASE_URL=postgresql://user:password@host:port/dbname
GEMINI_API_KEY=your-gemini-api-key
AWS_REGION=eu-west-1
DYNAMODB_TABLE_NAME=decks-db
AWS_S3_BUCKET_NAME=magic-card-data
QR_CODE_ENDPOINT=https://your-qr-endpoint
VOUCHER_SERVICE_ENDPOINT=https://your-voucher-endpoint
```

### 3. Run migrations and start the server

```bash
python manage.py migrate
python manage.py runserver
```

Then open [http://127.0.0.1:8000/](http://127.0.0.1:8000/) in your browser.

## Deployment

The app deploys automatically to **AWS Elastic Beanstalk** via GitHub Actions whenever you push to `main`.

The CI pipeline:
1. Runs tests
2. Injects environment secrets into the EB environment (from GitHub Actions secrets)
3. Zips the project and deploys it

Sensitive config (database URL, API keys, etc.) is stored in **GitHub Actions Secrets** — never hardcoded in the repo.

Additionally, the application is monitored using **DataDog**. 