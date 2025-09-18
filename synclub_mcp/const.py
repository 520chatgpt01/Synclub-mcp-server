# speech model default values
DEFAULT_VOICE_ID = "female-shaonv"
DEFAULT_SPEECH_MODEL = "speech-02-hd"
DEFAULT_SPEED = 1.0
DEFAULT_VOLUME = 1.0
DEFAULT_PITCH = 0
DEFAULT_EMOTION = "happy"
DEFAULT_SAMPLE_RATE = 32000
DEFAULT_BITRATE = 128000
DEFAULT_CHANNEL = 1
DEFAULT_FORMAT = "mp3"
DEFAULT_LANGUAGE_BOOST = "auto"

# video model default values
DEFAULT_T2V_MODEL = "T2V-01"

# image model default values
DEFAULT_T2I_MODEL = "image-01"

# ENV variables
ENV_SYNCLUB_MCP_API = "SYNCLUB_MCP_API"
ENV_MINIMAX_API_KEY = "MINIMAX_API_KEY"
ENV_MINIMAX_API_HOST = "MINIMAX_API_HOST"
ENV_synclub_mcp_BASE_PATH = "synclub_mcp_BASE_PATH"
ENV_RESOURCE_MODE = "MINIMAX_API_RESOURCE_MODE"

RESOURCE_MODE_LOCAL = "local" # save resource to local file system
RESOURCE_MODE_URL = "url" # provide resource url

ENV_FASTMCP_LOG_LEVEL = "FASTMCP_LOG_LEVEL"

NANO_PROMPT_DICT = {
    "three_view": "Please generate three views (front view, side view, back view) of the IP character in this image. \
        Display the three views in a single row, keep the character's appearance unchanged, and use a pure white \
    background with no text.",
    "emoji_pack": """Please create a 9-grid meme pack based on the image I sent, with 3 memes per row. 
Maintain the character's features, the color scheme and art style of the image. The descriptions of the 9 actions are as follows:
Give a thumbs-up + squint with a smile + small hearts above the head
Cover face with both hands + wavy eyebrows + pink-tipped ears
Slump over the table + spiral eyes + low-battery icon above the head
Hold a watermelon with both hands + shocked wide eyes + stiff cowlick on the head
Make gun gestures with both hands + wink with one eye + emit heart-shaped light waves
Hold head in frustration + glitchy pupils + smoke coming out of the head
Lean sideways and peek out + glowing reflection on glasses lenses + sneaky smile on the lips
Wave hands frantically + motion blur effect + panicked text emoticon
Rub hands with a coquettish smile + dollar-sign-shaped eyes + palms facing up""",
    "oc_character_card": "Based on the IP image, maintaining the character's original appearance, create OC character display cards. \
        On the left side of the card is a full-body display of the character, and in the lower right corner, two close-up head photos \
        of the character \(happy and angry) are placed from top to bottom. In the upper right corner, the main color card display of \
        the image is placed.  The background is in a simple letterpress style and well integrates with the character. The overall color tone \
        of the background is compatible with the character, and there are no words.",
    "figure_display": "create a 1/7 scale commercialized figure of thecharacter in the illustration, \
        in a realistic styie and environment. Place the figure on a computer desk, using a circular transparent acrylic base without any text. \
        On the computer screen, display the ZBrush modeling process of the figure.Next to the computer screen, place a BANDAl-style toy \
        packaging box printedwith the original artwork.",
}