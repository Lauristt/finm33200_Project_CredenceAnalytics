# Deploying Credence Analytics Agent

This project is a pure Python web app. The UI entry point is:

```bash
financial-credibility-ui --host 0.0.0.0
```

The app reads `PORT` automatically, which is what most hosting platforms set.

## Required Environment Variables

At minimum, configure:

```text
OPENAI_API_KEY=...
OPENAI_MODEL=gpt-4.1-mini
SEC_USER_AGENT="Your Name your.email@example.com"
CREDIBILITY_LLM_PROVIDER=auto
CREDIBILITY_STRUCTURED_SOURCES=true
CREDIBILITY_TICKER_UNIVERSE_FILTER=true
CREDIBILITY_TICKER_UNIVERSE_FETCH=true
```

`SEC_USER_AGENT` is not an API key, but SEC requests should include a clear
contact string.

## Option 1: Render

1. Push this repo to GitHub.
2. Create a new Render Blueprint from the repo.
3. Render will read `render.yaml`.
4. Add secret values for:
   - `OPENAI_API_KEY`
   - `SEC_USER_AGENT`
5. Deploy.

Render will run:

```bash
financial-credibility-ui --host 0.0.0.0
```

and provide a public HTTPS URL.

## Option 2: Docker

Build and run locally:

```bash
docker build -t credence-analytics-agent .
docker run --env-file .env -p 8765:8765 credence-analytics-agent
```

Open:

```text
http://localhost:8765
```

Deploy the same image to Fly.io, Railway, AWS ECS, GCP Cloud Run, Azure
Container Apps, or another Docker host.

## Option 3: Quick Private Demo

Run the app on your machine:

```bash
PYTHONPATH=src python3 -m financial_credibility.webapp --host 0.0.0.0 --port 8765
```

Then expose it with a tunnel such as Cloudflare Tunnel or ngrok. This is good for
short demos, but not ideal for long-running public use.

## Production Notes

- Do not commit `.env`.
- Put the app behind an access control layer before public sharing. The app can
  call paid LLM APIs, so an open public URL can burn API credits.
- Use official-source rate limits politely. SEC fair access currently expects
  efficient requests and a declared user agent.
- The built-in Python server is fine for demos and small internal use. For
  heavier production traffic, put it behind a reverse proxy or wrap the app in a
  production web framework.
