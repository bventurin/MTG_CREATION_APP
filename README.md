# ⚡ AetherFlow – MTG Deck Builder

Hey there! AetherFlow is a web app I built for Magic: The Gathering players who want to create, manage, and improve their decks with a little help from AI.

It's built with Django and deployed on AWS, combining multiple services to give you a smooth deck-building experience.

## What it does

**AetherFlow** helps you build and organize your MTG decks. You can paste in an existing deck list or build one from scratch, get AI-powered suggestions to make it better, and even share your creations via QR code. Plus, there's a voucher system for tracking discounts on your deck purchases.

### Features

- 🃏 **Deck Builder** — Create, edit, and organize your decks. Just paste a deck list or add cards one by one.
- 🤖 **AI Recommendations** — Stuck on what to add? Google Gemini analyzes your deck and suggests 3 cards that could improve it.
- 🧑🏽‍💻 **QR Code Sharing** — Share your deck with friends by generating a QR code they can scan.
- 🎟️ **Vouchers** — Generate vouchers for your decks to help you save money when buying cards.
- 🔐 **User Accounts** — Sign up, log in, and keep all your decks in one place.

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

## Want to run it locally?

### 1. Clone and set up your environment

```bash
git clone <your-repo-url>
cd "Magic Project"
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Set up your environment variables

Create a `.env` file in the project root with your own credentials:

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

### 3. Run migrations and fire it up

```bash
python manage.py migrate
python manage.py runserver
```

Head over to [http://127.0.0.1:8000/](http://127.0.0.1:8000/) and you're good to go!

## Deployment

The app automatically deploys to **AWS Elastic Beanstalk** whenever I push to `main`, thanks to GitHub Actions.

Here's what happens:
1. Tests run to make sure nothing's broken
2. Environment secrets get injected from GitHub Actions (so no credentials leak into the code)
3. Everything gets zipped up and deployed

All the sensitive stuff (database URLs, API keys, etc.) lives safely in **GitHub Secrets**, not in the code itself.

I'm also using **DataDog** to keep an eye on performance and catch any issues in production. 