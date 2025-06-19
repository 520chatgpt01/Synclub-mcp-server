<h1 align="center">SynClub MCP Server</h1>

<p align="center">
  Official SynClub Model Context Protocol (MCP) Server that enables powerful AI generation capabilities including text-to-speech, voice cloning, video generation, image generation, and more. Compatible with MCP clients like <a href="https://www.anthropic.com/claude">Claude Desktop</a>, <a href="https://www.cursor.so">Cursor</a>, <a href="https://codeium.com/windsurf">Windsurf</a>, and others.
</p>

## Features

-  **Text-to-Speech**: Convert text to natural speech with multiple voice options
-  **Voice Cloning**: Clone voices from audio samples
-  **Video Generation**: Generate videos from text prompts or images
-  **Image Generation**: Create images from text descriptions
-  **Image Recognition**: Analyze and understand image content
-  **Background Removal**: Automatically remove backgrounds from images
-  **HD Image Restoration**: Enhance image quality and resolution
-  **AI Search**: Intelligent search with AI-powered results
-  **Japanese TTS**: Specialized Japanese text-to-speech

## Quick Start

### 1. Install uv (Python Package Manager)

```bash
# macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows (PowerShell)
powershell -c "irm https://astral.sh/uv/install.sh | iex"

# Or via package managers
# brew install uv
# pip install uv
```

### 2. Get Your API Key

Obtain your API key from your account information page on the SynClub server website.

### 3. Configure Your MCP Client

#### Claude Desktop

Edit your `claude_desktop_config.json` file:

```json
{
  "mcpServers": {
    "SynClub": {
      "command": "uvx",
      "args": [
          "synclub-mcp"
      ],
      "env": {
          "SYNCLUB_MCP_API": "your api key"
      }
    }
  }
}
```

##  Available Tools

| Tool Name | Description |
|-----------|-------------|
| `minimax_text_to_audio` | Convert text to speech with customizable voice settings |
| `minimax_list_voices` | List all available voices | Free |
| `minimax_voice_clone` | Clone voices from audio files |
| `minimax_text_to_image` | Generate images from text prompts |
| `generate_text_to_video` | Generate videos from text descriptions using Kling models|
| `generate_image_to_video` | Generate videos from images with text prompts using Kling models|
| `image_recognition` | Analyze and recognize image content |
| `remove_bg` | Automatically remove image backgrounds | Free |
| `hd_restore` | Enhance image quality and resolution | Free |
| `generate_image` | Generate images using alternative models |
| `ai_search` | Perform AI-powered search queries |
| `japanese_tts` | Japanese text-to-speech conversion |

### Environment Variables

- `SYNCLUB_MCP_API`: Your API key (required)

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## From
https://github.com/520chatgpt01/Synclub-mcp-server