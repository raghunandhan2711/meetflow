# Required API credentials

The website's backend keeps credentials in `.env`. Restart the server after adding them. The local speech model and PostgreSQL database are already configured on this machine. No database API key or OpenAI key is needed.

| Feature                                     | What you need                                 | Where to get it                                                                                                                                        |
| ------------------------------------------- | --------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------ |
| AI summaries, decisions and extracted tasks | `GROQ_API_KEY`                                | [Groq Console](https://console.groq.com/keys)                                                                                                          |
| Automatic speaker detection                 | `HF_TOKEN` and accepted model access          | [Hugging Face tokens](https://huggingface.co/settings/tokens), [pyannote community-1](https://huggingface.co/pyannote/speaker-diarization-community-1) |
| Jira issue creation                         | Atlassian token, email, site URL, project key | [Atlassian API tokens](https://id.atlassian.com/manage-profile/security/api-tokens)                                                                    |

## Groq

The supplied Groq key is configured on this machine and live analysis has been verified. For a new installation, create a key at [Groq Console](https://console.groq.com/keys) and add it as `GROQ_API_KEY`. The configured analysis model is `qwen/qwen3.8-27b`; the original Llama model is no longer available to this account. Local transcription remains available without a key. If you choose hosted transcription, set `TRANSCRIPTION_PROVIDER=groq`; the same Groq key is used for speech-to-text.

```dotenv
GROQ_API_KEY=your_key
GROQ_MODEL=qwen/qwen3.8-27b
TRANSCRIPTION_PROVIDER=local
```

The key is sufficient to enable real analysis of saved transcripts. It is used only for outbound backend requests and is excluded from browser responses. Windows file permissions are protected; `.env` and environment variants are ignored by source control. AI submissions are limited to 3 per minute and 20 per hour. Account quotas and model permissions apply. A key pasted into chat should be replaced using the Groq console; replacing it in `.env` and restarting preserves meeting data. [Official quickstart](https://console.groq.com/docs/quickstart), [models](https://console.groq.com/docs/models), [speech-to-text](https://console.groq.com/docs/speech-to-text).

## Hugging Face

Create a read token at [Access Tokens](https://huggingface.co/settings/tokens). While signed into the same account, accept the conditions on [pyannote/speaker-diarization-community-1](https://huggingface.co/pyannote/speaker-diarization-community-1). Then configure:

```dotenv
HF_TOKEN=hf_your_token
DIARIZATION_ENABLED=true
```

The audio packages are installed. The first speaker-detection run downloads the gated models and requires connectivity to Hugging Face. This machine's Hub connection has been unreliable; Whisper is already prepared locally, while gated speaker inference still needs model access and a successful download. Speaker detection labels distinct voices; you assign real names in the transcript review.

[Official token guide](https://huggingface.co/docs/hub/security-tokens), [model instructions](https://huggingface.co/pyannote/speaker-diarization-community-1).

## Jira

Create a token at [Atlassian API tokens](https://id.atlassian.com/manage-profile/security/api-tokens). The account needs permission to create issues in your Jira Cloud project. Provide these values:

```dotenv
JIRA_BASE_URL=https://your-team.atlassian.net
JIRA_EMAIL=your-account-email@example.com
JIRA_API_TOKEN=your_token
JIRA_PROJECT_KEY=ENG
JIRA_ISSUE_TYPE=Task
JIRA_CLOUD_ID=
```

The project key is the prefix in an issue number: `ENG` in `ENG-123`. Use an issue type supported by that project. Scoped tokens also require the site's cloud ID and issue-creation scopes; requests then use Atlassian's `api.atlassian.com/ex/jira/{cloudId}` endpoint. Unscoped tokens use the site URL directly. Cloud ID is available from your site's `/_edge/tenant_info` endpoint.

The website sends tasks when you click **Create Jira issue**, or confirm **Create pending Jira issues**. Projects with extra mandatory fields require adding those fields in `app/services.py`.

[Official token instructions](https://support.atlassian.com/atlassian-account/docs/manage-api-tokens-for-your-atlassian-account/), [Jira issue API](https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-issues/).

## Database

PostgreSQL is already initialized on `127.0.0.1:55432`. Its generated connection string is in `.env`; the launcher starts it automatically. No Supabase, Firebase, or separate PostgreSQL API key is required.
