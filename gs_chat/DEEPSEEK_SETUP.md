# DeepSeek AI Configuration for GS Chat

This guide will help you configure GS Chat to use DeepSeek AI instead of OpenAI.

## What's Changed

The following files have been updated to support DeepSeek AI:

1. **Chatbot Settings DocType** (`gs_chat/doctype/chatbot_settings/chatbot_settings.json`)
   - Added `provider` field (OpenAI/DeepSeek)
   - Added `base_url` field for DeepSeek API endpoint
   - Added DeepSeek models to the model options

2. **Chat Controller** (`controllers/chat.py`)
   - Updated to use provider-specific configuration
   - Added base_url support for DeepSeek API

3. **Test Controller** (`controllers/test.py`)
   - Updated to support DeepSeek configuration

## Manual Configuration Steps

### Step 1: Update Database Schema
Since we've modified the DocType, you need to migrate the database:

```bash
# Run this in your ERPNext/Frappe environment
bench migrate
```

### Step 2: Configure Chatbot Settings

1. Go to **Chatbot Settings** in your ERPNext system
2. Set the following values:
   - **AI Provider**: DeepSeek
   - **API Key**: `sk-ae2bfc754a4040e595a2acbcdf7483f5`
   - **Base URL**: `https://api.deepseek.com` (auto-filled)
   - **Model**: Choose from:
     - `deepseek-chat` (DeepSeek-V3-0324) - General purpose
     - `deepseek-reasoner` (DeepSeek-R1-0528) - Reasoning tasks

### Step 3: Test the Configuration

1. Open the chatbot in your ERPNext system
2. Send a test message
3. Verify that responses are coming from DeepSeek

## Automated Setup

Alternatively, you can run the automated setup script:

```bash
# Navigate to the gs_chat directory
cd path/to/gs_chat

# Run the setup script
python setup_deepseek.py
```

## Available DeepSeek Models

- **deepseek-chat**: General-purpose conversational AI (DeepSeek-V3-0324)
- **deepseek-reasoner**: Specialized for reasoning and complex problem-solving (DeepSeek-R1-0528)

## API Key Information

Your DeepSeek API key: `sk-ae2bfc754a4040e595a2acbcdf7483f5`

## Troubleshooting

### Common Issues

1. **"Module not found" errors**: Make sure you've run `bench migrate` after updating the DocType
2. **API connection errors**: Verify your API key is correct and you have internet connectivity
3. **Model not found**: Ensure you're using one of the supported DeepSeek models

### Switching Back to OpenAI

If you want to switch back to OpenAI:
1. Change **AI Provider** to "OpenAI"
2. Update the **API Key** to your OpenAI key
3. Select an OpenAI model (gpt-4 or gpt-3.5-turbo)

## Support

If you encounter any issues, check:
1. DeepSeek API status: https://status.deepseek.com/
2. Your API key balance and limits
3. Network connectivity to api.deepseek.com
