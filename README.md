## Magic Project – Django MTG Creation App

This project is a Django application for creating and managing new decks in  Magic: The Gathering (MTG).
The application using AI will suggeste new decks based on the user's preferences. 
The main Django app is called `MTG_CREATION_APP`.

### Getting started

1. **Create/activate virtual environment**

```bash
cd "/Users/brennoventurini/Magic Project"
source .venv/bin/activate
```

2. **Run migrations**

```bash
python manage.py migrate
```

3. **Start development server**

```bash
python manage.py runserver
```

Then open `http://127.0.0.1:8000/` in your browser.

### Project structure (high level)

- **core** – Django project configuration (settings, URLs, WSGI/ASGI).
- **MTG_CREATION_APP** – main application for MTG-related features.
- **manage.py** – Django management script.

### Notes

Use this README to document:
- **Project goals and features**
- **How to install dependencies**
- **API endpoints or pages**
- **Any MTG-specific rules or logic**


