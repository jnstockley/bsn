# BSN
Python application, running in Docker to deliver consitent, low-latency notification when new content is posted on social networks like YouTube and Twitch

## Notice
This application has been placed on the back burner, I will merge depdency update PR submitted by Rennovate, but don't currently plan on adding new features/ fixing bugs.

## Setup
Simplest setup is to start from [compose.yml](https://github.com/jnstockley/BSN/blob/main/compose.yml) and [sample.env](https://github.com/jnstockley/BSN/blob/main/sample.env), which should be renamed to `.env`
### Import YouTube Channels
Follow the steps found in [docs/setup.md](https://github.com/jnstockley/BSN/blob/dev/docs/setup.md)

### Environment Vairables
- `YOUTUBE_API_KEYS` - List of YouTube Data V3 API Keys. The more keys provided, the quicker BSN can check for new uploads.
- `APPRISE_URLS` - Apprise is how we send notification, [follow the documentation here on how to set up the URL(s)](https://github.com/caronc/apprise?tab=readme-ov-file#supported-notifications)
