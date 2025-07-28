"""
SynClub MCP Server

⚠️ IMPORTANT: This server connects to SynClub API endpoints which may involve costs.
Any tool that makes an API call is clearly marked with a cost warning. Please follow these guidelines:

1. Only use these tools when users specifically ask for them
2. For audio generation tools, be mindful that text length affects the cost
3. Voice cloning features are charged upon first use after cloning

Note: Tools without cost warnings are free to use as they only read existing data.
"""
import asyncio
import os
import base64
import requests
import time
import json
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP
from mcp.types import TextContent
from synclub_mcp.utils import (
    build_output_path,
    build_output_file,
    process_input_file,
    play
)
import httpx
from typing import Optional, List, Dict, Any, Union

from synclub_mcp.const import *
from synclub_mcp.exceptions import SynclubAPIError, SynclubRequestError
from synclub_mcp.client import SynclubAPIClient
import logging
# 配置日志，避免输出到stdout干扰MCP通信
logging.basicConfig(level=logging.ERROR)



load_dotenv()
api_key = os.getenv(ENV_SYNCLUB_MCP_API, "123456")
base_path = os.getenv(ENV_synclub_mcp_BASE_PATH) or "~/Desktop"
api_host = os.getenv(ENV_MINIMAX_API_HOST)
resource_mode = os.getenv(ENV_RESOURCE_MODE) or RESOURCE_MODE_URL
fastmcp_log_level = os.getenv(ENV_FASTMCP_LOG_LEVEL) or "WARNING"

# 统一的占位 Base URL，可通过环境变量 UNIFIED_API_BASE_URL 覆盖
UNIFIED_BASE_URL = os.getenv("UNIFIED_API_BASE_URL", "https://api.synclubmcp.com")

# if not api_key:
#     raise ValueError("MINIMAX_API_KEY environment variable is required")
# if not api_host:
#     raise ValueError("MINIMAX_API_HOST environment variable is required")

mcp = FastMCP("SynClub", log_level=fastmcp_log_level, version="0.1.0", request_timeout=300)

# 创建统一的 MiniMax API Client，但使用 UNIFIED_BASE_URL
api_client = SynclubAPIClient(api_key, UNIFIED_BASE_URL)

# 创建通用的 HTTP 客户端用于其他 API 调用
async def make_unified_request(
    method: str,
    path: str,
    data: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
    files: Optional[Dict[str, Any]] = None,
    timeout: float = 120.0,
    stream: bool = False
) -> Union[Dict[str, Any], str]:
    """
    统一的请求函数，用于所有非 MiniMax API 调用
    
    Args:
        stream: 是否启用流式响应，如果为True，返回文本内容而非JSON
    """
    url = f"{UNIFIED_BASE_URL}{path}"
    default_headers = {
        'Content-Type': 'application/json',
        'User-Agent': 'synclub-mcp-server/1.0.0',
        'x-api-key': api_key
    }
    
    if headers:
        default_headers.update(headers)
    
    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            if method.upper() == "POST":
                if files:
                    # multipart/form-data 请求，不设置 Content-Type (httpx会自动设置)
                    del default_headers['Content-Type']
                    response = await client.post(url, headers=default_headers, data=data, files=files)
                else:
                    response = await client.post(url, headers=default_headers, json=data)
            elif method.upper() == "GET":
                response = await client.get(url, headers=default_headers, params=data)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")
            
            response.raise_for_status()
            
            if stream:
                # process stream response
                content_parts = []
                
                async for chunk in response.aiter_text():
                    if chunk:
                        # split chunk by line, because it may contain multiple lines of data
                        lines = chunk.split('\n')
                        for line in lines:
                            line = line.strip()
                            if not line:
                                continue
                                
                            # check if it is SSE data format
                            if line.startswith('data: '):
                                try:
                                    # extract JSON data
                                    json_str = line[6:]  # remove 'data: ' prefix
                                    json_data = json.loads(json_str)
                                    
                                    # extract content
                                    if (isinstance(json_data, dict) and 
                                        'data' in json_data and 
                                        isinstance(json_data['data'], dict) and 
                                        'content' in json_data['data']):
                                        content = json_data['data']['content']
                                        if content:  # only collect non-empty content
                                            content_parts.append(content)
                                    
                                except json.JSONDecodeError:
                                    # if parsing fails, continue to process the next line
                                    continue
                
                # merge all content parts and return
                return ''.join(content_parts)
            else:
                # process normal JSON response
                return response.json()
            
        except httpx.HTTPStatusError as e:
            error_msg = f"HTTP error {e.response.status_code}"
            try:
                error_detail = e.response.json()
                error_msg += f": {error_detail}"
            except:
                error_msg += f": {e.response.text}"
            raise Exception(error_msg)
            
        except httpx.TimeoutException:
            raise Exception("Request timeout")
            
        except Exception as e:
            raise Exception(f"Request failed: {str(e)}")


@mcp.tool(
    description="""Convert text to audio with a given voice and save the output audio file to a given directory.
    Directory is optional, if not provided, the output file will be saved to $HOME/Desktop.
    Voice id is optional, if not provided, the default voice will be used.

    COST WARNING: This tool makes an API call to Minimax which may incur costs. Only use when explicitly requested by the user.

    Args:
        text (str): The text to convert to speech.
        voice_id (str, optional): The id of the voice to use. For example, "male-qn-qingse"/"audiobook_female_1"/"cute_boy"/"Charming_Lady"/"Wise_Woman"...
        model (string, optional): The model to use.
        speed (float, optional): Speed of the generated audio. Controls the speed of the generated speech. Values range from 0.5 to 2.0, with 1.0 being the default speed. 
        vol (float, optional): Volume of the generated audio. Controls the volume of the generated speech. Values range from 0 to 10, with 1 being the default volume.
        pitch (float, optional): Pitch of the generated audio. Controls the pitch of the generated speech. Values range from -12.0 to 12.0, with 0.0 being the default pitch.
        emotion (str, optional): Emotion of the generated audio. Controls the emotion of the generated speech. Values range ["happy", "sad", "angry", "fearful", "disgusted", "surprised", "neutral"], with "neutral" being the default emotion.
        english_normalization (bool, optional): Whether to enable English normalization. Default is False.
        sample_rate (int, optional): Sample rate of the generated audio. Controls the sample rate of the generated speech. Values range [8000,16000,22050,24000,32000,44100] with 32000 being the default sample rate.
        bitrate (int, optional): Bitrate of the generated audio. Controls the bitrate of the generated speech. Values range [32000,64000,128000,256000] with 128000 being the default bitrate.
        channel (int, optional): Channel of the generated audio. Controls the channel of the generated speech. Values range [1, 2] with 1 being the default channel.
        format (str, optional): Format of the generated audio. Controls the format of the generated speech. Values range ["pcm", "mp3","flac"] with "mp3" being the default format.
        language_boost (str, optional): Language boost of the generated audio. Controls the language boost of the generated speech. Values range ['Chinese', 'Chinese,Yue', 'English', 'Arabic', 'Russian', 'Spanish', 'French', 'Portuguese', 'German', 'Turkish', 'Dutch', 'Ukrainian', 'Vietnamese', 'Indonesian', 'Japanese', 'Italian', 'Korean', 'Thai', 'Polish', 'Romanian', 'Greek', 'Czech', 'Finnish', 'Hindi', 'auto'] with "Chinese" being the default language boost.
        pronunciation_dict_tone (list, optional): List of pronunciation dictionary entries for tone. Each entry should be in format "word /(pronunciation)".
        timber_weight (int, optional): Weight for timber control. Values range from 1 to 100, with 100 being the default.
        stream (bool, optional): Whether to enable streaming. Default is False.
        subtitle_enable (bool, optional): Whether to enable subtitle generation. Default is True.
        output_directory (str): The directory to save the audio to.

    Returns:
        Text content with the path to the output file and name of the voice used.
    """
)
def minimax_text_to_audio(
    text: str,
    output_directory: str = None,
    voice_id: str = DEFAULT_VOICE_ID,
    model: str = DEFAULT_SPEECH_MODEL,
    speed: float = DEFAULT_SPEED,
    vol: float = DEFAULT_VOLUME,
    pitch: float = DEFAULT_PITCH,
    emotion: str = DEFAULT_EMOTION,
    english_normalization: bool = False,
    sample_rate: int = DEFAULT_SAMPLE_RATE,
    bitrate: int = DEFAULT_BITRATE,
    channel: int = DEFAULT_CHANNEL,
    format: str = DEFAULT_FORMAT,
    language_boost: str = "Chinese",
    pronunciation_dict_tone: list = None,
    timber_weight: int = 100,
    stream: bool = False,
    subtitle_enable: bool = True,
):
    if not text:
        raise SynclubRequestError("Text is required.")

    payload = {
        "model": model,
        "text": text,
        "voice_setting": {
            "voice_id": voice_id,
            "speed": speed,
            "vol": vol,
            "pitch": pitch,
            "emotion": emotion,
            "english_normalization": english_normalization
        },
        "audio_setting": {
            "sample_rate": sample_rate,
            "bitrate": bitrate,
            "format": format,
            "channel": channel
        },
        "language_boost": language_boost,
        "stream": stream,
        "subtitle_enable": subtitle_enable
    }
    
    # Add pronunciation dictionary if provided
    if pronunciation_dict_tone:
        payload["pronunciation_dict"] = {
            "tone": pronunciation_dict_tone
        }
    
    # Add timber weights
    payload["timber_weights"] = [{
        "voice_id": voice_id,
        "weight": timber_weight
    }]
    
    if resource_mode == RESOURCE_MODE_URL:
        payload["output_format"] = "url"
    else:
        payload["output_format"] = "hex"
        
    try:
        response_data = api_client.post("/pulsar/mcp/minimax/tts", json=payload)
        audio_data = response_data.get('data', {}).get('audio', '')
        
        if not audio_data:
            raise SynclubRequestError(f"Failed to get audio data from response")
        if resource_mode == RESOURCE_MODE_URL:
            return TextContent(
                type="text",
                text=f"Success. Audio URL: {audio_data}"
            )
        # hex->bytes
        audio_bytes = bytes.fromhex(audio_data)

        # save audio to file
        output_path = build_output_path(output_directory, base_path)
        output_file_name = build_output_file("t2a", text, output_path, format)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path / output_file_name, "wb") as f:
            f.write(audio_bytes)

        return TextContent(
            type="text",
            text=f"Success. File saved as: {output_path / output_file_name}. Voice used: {voice_id}",
        )
        
    except SynclubAPIError as e:
        return TextContent(
            type="text",
            text=f"Failed to generate audio: {str(e)}"
        )


# @mcp.tool(
#     description="""List all voices available.

#     Args:
#         voice_type (str, optional): The type of voices to list. Values range ["all", "system", "voice_cloning"], with "all" being the default.
#     Returns:
#         Text content with the list of voices.
#     """
# )
# def minimax_list_voices(
#     voice_type: str = "all"
# ):
#     try:
#         response_data = api_client.post("/pulsar/mcp/miniMax/voice_list", json={'voice_type': voice_type})
        
#         system_voices = response_data.get('system_voice', []) or []
#         voice_cloning_voices = response_data.get('voice_cloning', []) or []
#         system_voice_list = []
#         voice_cloning_voice_list = []
        
#         for voice in system_voices:
#             system_voice_list.append(f"Name: {voice.get('voice_name')}, ID: {voice.get('voice_id')}")
#         for voice in voice_cloning_voices:
#             voice_cloning_voice_list.append(f"Name: {voice.get('voice_name')}, ID: {voice.get('voice_id')}")

#         return TextContent(
#             type="text",
#             text=f"Success. System Voices: {system_voice_list}, Voice Cloning Voices: {voice_cloning_voice_list}"
#         )
        
#     except SynclubAPIError as e:
#         return TextContent(
#             type="text",
#             text=f"Failed to list voices: {str(e)}"
#         )


@mcp.tool(
    description="""Clone a voice using provided audio files. The new voice will be charged upon first use.

    COST WARNING: This tool makes an API call to Minimax which may incur costs. Only use when explicitly requested by the user.

     Args:
        voice_id (str): The id of the voice to use.
        file (str): The path to the audio file to clone or a URL to the audio file.
        text (str, optional): The text to use for the demo audio.
        is_url (bool, optional): Whether the file is a URL. Defaults to False.
        output_directory (str): The directory to save the demo audio to.
    Returns:
        Text content with the voice id of the cloned voice.
    """
)
def minimax_voice_clone(
    voice_id: str, 
    file: str,
    text: str,
    output_directory: str = None,
    is_url: bool = False
) -> TextContent:
    try:
        # step1: upload file
        if is_url:
            # download file from url
            response = requests.get(file, stream=True)
            response.raise_for_status()
            files = {'file': ('audio_file.mp3', response.raw, 'audio/mpeg')}
            data = {'purpose': 'voice_clone'}
            response_data = api_client.post("/pulsar/mcp/minimax/upload", files=files, data=data)
        else:
            # open and upload file
            if not os.path.exists(file):
                raise SynclubRequestError(f"Local file does not exist: {file}")
            with open(file, 'rb') as f:
                files = {'file': f}
                data = {'purpose': 'voice_clone'}
                response_data = api_client.post("/pulsar/mcp/minimax/upload", files=files, data=data)
            
        file_id = response_data.get("file",{}).get("file_id")
        if not file_id:
            raise SynclubRequestError(f"Failed to get file_id from upload response")

        # step2: clone voice
        payload = {
            "file_id": file_id,
            "voice_id": voice_id,
        }
        if text:
            payload["text"] = text
            payload["model"] = DEFAULT_SPEECH_MODEL

        response_data = api_client.post("/pulsar/mcp/minimax/vc", json=payload)
        
        if not response_data.get("demo_audio"):
            return TextContent(
                type="text",
                text=f"Voice cloned successfully: Voice ID: {voice_id}"
            )
        if resource_mode == RESOURCE_MODE_URL:
            return TextContent(
                type="text",
                text=f"Success. Demo audio URL: {response_data.get('demo_audio')}"
            )
        # step3: download demo audio
        output_path = build_output_path(output_directory, base_path)
        output_file_name = build_output_file("voice_clone", text, output_path, "wav")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path / output_file_name, "wb") as f:
            f.write(requests.get(response_data.get("demo_audio")).content)

        return TextContent(
            type="text",
            text=f"Voice cloned successfully: Voice ID: {voice_id}, demo audio saved as: {output_path / output_file_name}"
        )
        
    except SynclubAPIError as e:
        return TextContent(
            type="text",
            text=f"Failed to clone voice: {str(e)}"
        )
    except (IOError, requests.RequestException) as e:
        return TextContent(
            type="text",
            text=f"Failed to handle files: {str(e)}"
        )


# @mcp.tool(
#     description="""Upload a file to Minimax service.

#     COST WARNING: This tool makes an API call to Minimax which may incur costs. Only use when explicitly requested by the user.

#     Args:
#         file_path (str): The path to the file to upload or a URL to the file.
#         purpose (str): The purpose of the file upload. Values range ["voice_clone", "video_generation"], with "voice_clone" being the default.
#         is_url (bool, optional): Whether the file is a URL. Defaults to False.
#     Returns:
#         Text content with the file ID of the uploaded file.
#     """
# )
# def minimax_upload_file(
#     file_path: str,
#     purpose: str = "voice_clone",
#     is_url: bool = False
# ) -> TextContent:
#     try:
#         if is_url:
#             # download file from url
#             response = requests.get(file_path, stream=True)
#             response.raise_for_status()
#             files = {'file': ('uploaded_file', response.raw, 'application/octet-stream')}
#             data = {'purpose': purpose}
#             response_data = api_client.post("/pulsar/mcp/minimax/upload", files=files, data=data)
#         else:
#             # open and upload file
#             if not os.path.exists(file_path):
#                 raise SynclubRequestError(f"Local file does not exist: {file_path}")
#             with open(file_path, 'rb') as f:
#                 files = {'file': f}
#                 data = {'purpose': purpose}
#                 response_data = api_client.post("/pulsar/mcp/minimax/upload", files=files, data=data)
            
#         file_id = response_data.get("file",{}).get("file_id")
#         if not file_id:
#             raise SynclubRequestError(f"Failed to get file_id from upload response")

#         return TextContent(
#             type="text",
#             text=f"File uploaded successfully: File ID: {file_id}"
#         )
        
#     except SynclubAPIError as e:
#         return TextContent(
#             type="text",
#             text=f"Failed to upload file: {str(e)}"
#         )
#     except (IOError, requests.RequestException) as e:
#         return TextContent(
#             type="text",
#             text=f"Failed to handle file: {str(e)}"
#         )


# @mcp.tool(
#     description="""Query file information by file ID.

#     Args:
#         file_id (str): The file ID to query.
#     Returns:
#         Text content with the file information.
#     """
# )
# def minimax_query_file(file_id: str) -> TextContent:
#     try:
#         response_data = api_client.get(f"/pulsar/mcp/minimax/query/ttv_file?file_id={file_id}")
        
#         file_info = response_data.get("file", {})
#         if not file_info:
#             return TextContent(
#                 type="text",
#                 text=f"No file information found for file_id: {file_id}"
#             )
        
#         download_url = file_info.get("download_url", "")
#         file_name = file_info.get("filename", "")
#         file_size = file_info.get("bytes", 0)
#         created_at = file_info.get("created_at", "")
        
#         return TextContent(
#             type="text",
#             text=f"File Information - ID: {file_id}, Name: {file_name}, Size: {file_size} bytes, Created: {created_at}, Download URL: {download_url}"
#         )
        
#     except SynclubAPIError as e:
#         return TextContent(
#             type="text",
#             text=f"Failed to query file information: {str(e)}"
#         )


@mcp.tool(
    description="""Generate a image from a prompt.

    COST WARNING: This tool makes an API call to Minimax which may incur costs. Only use when explicitly requested by the user.

     Args:
        model (str, optional): The model to use. Values range ["image-01"], with "image-01" being the default.
        prompt (str): The prompt to generate the image from.
        aspect_ratio (str, optional): The aspect ratio of the image. Values range ["1:1", "16:9","4:3", "3:2", "2:3", "3:4", "9:16", "21:9"], with "1:1" being the default.
        n (int, optional): The number of images to generate. Values range [1, 9], with 1 being the default.
        prompt_optimizer (bool, optional): Whether to optimize the prompt. Values range [True, False], with True being the default.
        output_directory (str): The directory to save the image to.
    Returns:
        Text content with the path to the output image file.
    """
)
def minimax_text_to_image(
    model: str = DEFAULT_T2I_MODEL,
    prompt: str = "",
    aspect_ratio: str = "1:1",
    n: int = 1,
    prompt_optimizer: bool = True,
    output_directory: str = None,
):
    try:
        if not prompt:
            raise SynclubRequestError("Prompt is required")

        payload = {
            "model": model, 
            "prompt": prompt,
            "aspect_ratio": aspect_ratio,
            "n": n,
            "prompt_optimizer": prompt_optimizer
        }

        response_data = api_client.post("/pulsar/mcp/minimax/tti", json=payload)
        image_urls = response_data.get("data",{}).get("image_urls",[])
        
        if not image_urls:
            raise SynclubRequestError("No images generated")
        if resource_mode == RESOURCE_MODE_URL:
            return TextContent(
                type="text",
                text=f"Success. Image URLs: {image_urls}"
            )
        output_path = build_output_path(output_directory, base_path)
        output_file_names = []
        
        for i, image_url in enumerate(image_urls):
            output_file_name = build_output_file("image", f"{i}_{prompt}", output_path, "jpg")
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            image_response = requests.get(image_url)
            image_response.raise_for_status()
            
            with open(output_file_name, 'wb') as f:
                f.write(image_response.content)
            output_file_names.append(output_file_name)
            
        return TextContent(
            type="text",
            text=f"Success. Images saved as: {output_file_names}"
        )
        
    except SynclubAPIError as e:
        return TextContent(
            type="text",
            text=f"Failed to generate images: {str(e)}"
        )
    except (IOError, requests.RequestException) as e:
        return TextContent(
            type="text",
            text=f"Failed to save images: {str(e)}"
        )



@mcp.tool(
    description="""Generate a video from a prompt.

    COST WARNING: This tool makes an API call to Minimax which may incur costs. Only use when explicitly requested by the user.

     Args:
        model (str, optional): The model to use. Values range ["T2V-01", "T2V-01-Director", "I2V-01", "I2V-01-Director", "I2V-01-live"]. "Director" supports inserting instructions for camera movement control. "I2V" for image to video. "T2V" for text to video.
        prompt (str): The prompt to generate the video from. When use Director model, the prompt supports 15 Camera Movement Instructions (Enumerated Values)
            -Truck: [Truck left], [Truck right]
            -Pan: [Pan left], [Pan right]
            -Push: [Push in], [Pull out]
            -Pedestal: [Pedestal up], [Pedestal down]
            -Tilt: [Tilt up], [Tilt down]
            -Zoom: [Zoom in], [Zoom out]
            -Shake: [Shake]
            -Follow: [Tracking shot]
            -Static: [Static shot]
        first_frame_image (str): The first frame image. The model must be "I2V" Series.
        output_directory (str): The directory to save the video to.
        async_mode (bool, optional): Whether to use async mode. Defaults to False. If True, the video generation task will be submitted asynchronously and the response will return a task_id. Should use `query_video_generation` tool to check the status of the task and get the result.
    Returns:
        Text content with the path to the output video file.
    """
)
def minimax_generate_video(
    model: str = DEFAULT_T2V_MODEL,
    prompt: str = "",
    first_frame_image  = None,
    output_directory: str = None,
    async_mode: bool = False
):
    try:
        if not prompt:
            raise SynclubRequestError("Prompt is required")

        # check first_frame_image
        if first_frame_image:
            if not isinstance(first_frame_image, str):
                raise SynclubRequestError(f"First frame image must be a string, got {type(first_frame_image)}")
            if not first_frame_image.startswith(("http://", "https://", "data:")):
                # if local image, convert to dataurl
                if not os.path.exists(first_frame_image):
                    raise SynclubRequestError(f"First frame image does not exist: {first_frame_image}")
                with open(first_frame_image, "rb") as f:
                    image_data = f.read()
                    first_frame_image = f"data:image/jpeg;base64,{base64.b64encode(image_data).decode('utf-8')}"

        # step1: submit video generation task
        payload = {
            "model": model,
            "prompt": prompt
        }
        if first_frame_image:
            payload["first_frame_image"] = first_frame_image
        
        response_data = api_client.post("/pulsar/mcp/minimax/ttv/create", json=payload)
        task_id = response_data.get("task_id")
        if not task_id:
            raise SynclubRequestError("Failed to get task_id from response")

        if async_mode:
            return TextContent(
                type="text",
                text=f"Success. Video generation task submitted: Task ID: {task_id}. Please use `query_video_generation` tool to check the status of the task and get the result."
            )

        # step2: wait for video generation task to complete
        file_id = None
        max_retries = 30  # 10 minutes total (30 * 20 seconds)
        retry_interval = 20  # seconds
        
        for attempt in range(max_retries):
            status_response = api_client.get(f"/pulsar/mcp/minimax/ttv/task?task_id={task_id}")
            status = status_response.get("status")
            
            if status == "Fail":
                raise SynclubRequestError(f"Video generation failed for task_id: {task_id}")
            elif status == "Success":
                file_id = status_response.get("file_id")
                if file_id:
                    break
                raise SynclubRequestError(f"Missing file_id in success response for task_id: {task_id}")
            
            # Still processing, wait and retry
            time.sleep(retry_interval)

        if not file_id:
            raise SynclubRequestError(f"Failed to get file_id for task_id: {task_id}")

        # step3: fetch video result
        file_response = api_client.get(f"/pulsar/mcp/minimax/ttv/file?file_id={file_id}")
        download_url = file_response.get("file", {}).get("download_url")
        
        if not download_url:
            raise SynclubRequestError(f"Failed to get download URL for file_id: {file_id}")
        if resource_mode == RESOURCE_MODE_URL:
            return TextContent(
                type="text",
                text=f"Success. Video URL: {download_url}"
            )
        # step4: download and save video
        output_path = build_output_path(output_directory, base_path)
        output_file_name = build_output_file("video", task_id, output_path, "mp4", True)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        video_response = requests.get(download_url)
        video_response.raise_for_status()
        
        with open(output_path / output_file_name, "wb") as f:
            f.write(video_response.content)

        return TextContent(
            type="text",
            text=f"Success. Video saved as: {output_path / output_file_name}"
        )

    except SynclubAPIError as e:
        return TextContent(
            type="text",
            text=f"Failed to generate video: {str(e)}"
        )
    except (IOError, requests.RequestException) as e:
        return TextContent(
            type="text",
            text=f"Failed to handle video file: {str(e)}"
        )
    except Exception as e:
        return TextContent(
            type="text",
            text=f"Unexpected error while generating video: {str(e)}"
        )



@mcp.tool(description="""
Function: Automatically extract objects from input image and remove background

Args:
    image_url (str): URL of the input image

Returns:
    TextContent: Contains the result image URL or file path
""")
async def remove_bg(
    image_url: str,
) -> TextContent:
    try:
        if not image_url:
            raise Exception("Image URL is required")

        payload = {
            "image_url": image_url
        }

        # 使用统一的请求函数调用背景去除API
        response_data = await make_unified_request(
            method="POST",
            path="/pulsar/mcp/self/image/remove_bg",
            data=payload,

        )
        
        return TextContent(
            type="text",
            text=f"Success. response_data: {response_data}"
        )
        
    except Exception as e:
        return TextContent(
            type="text",
            text=f"Failed to remove background: {str(e)}"
        )

@mcp.tool(description="""
Function: High-definition image restoration based on input image

Args:
    image_url (str): URL of the input image
Returns:
    TextContent: Contains the result image URL or file path
""")
async def hd_restore(
    image_url: str,
) -> TextContent:
    try:
        if not image_url:
            raise Exception("Image URL is required")

        payload = {
            "image_url": image_url
        }

        # 使用统一的请求函数调用图像高清修复API
        response_data = await make_unified_request(
            method="POST",
            path="/pulsar/mcp/self/image/quality",
            data=payload
        )
        

        return TextContent(
            type="text",
            text=f"Success. response_data: {response_data}"
        )
        
    except Exception as e:
        return TextContent(
            type="text",
            text=f"Failed to restore image: {str(e)}"
        )


@mcp.tool(description="""
Function: Generate an image based on a prompt

Args:
    prompt (str): The prompt to generate the image from.
    model (str, optional): The model to use. Values range ["deploy_gpt_image_1"], with "deploy_gpt_image_1" being the default.
    number (int, optional): The number of images to generate. Values range [1, 9], with 1 being the default.
    output_directory (str, optional): The directory to save the image to.

Returns:
    TextContent: Contains the result image URLs or file paths
""")
async def openai_generate_image(
    prompt: str,
    model: str = "deploy_gpt_image_1",
    number: int = 1,
) -> TextContent:
    try:
        if not prompt:
            raise Exception("Prompt is required")

        payload = {
            "model_name": model,
            "prompt": prompt,
            "height": 1024,
            "width": 1024,
            "quality": "medium",
            "output_compression": 100,
            "output_format": "png",
            "number": number
        }

        response_data = await make_unified_request(
            method="POST",
            path="/pulsar/mcp/openai/tti",
            data=payload,
        )
        
        return TextContent(
            type="text",
            text=f"Success. response_data: {response_data}"
        )
        
    except Exception as e:
        return TextContent(
            type="text",
            text=f"Failed to generate images: {str(e)}"
        )

@mcp.tool(description="""
Function: GPT image recognition and analysis

Args:
    image_url (str): The URL of the image to analyze.
    prompt (str): The prompt for image analysis.
    model (str, optional): The model to use. Values range ["deploy_gpt4o"], with "deploy_gpt4o" being the default.

Returns:
    TextContent: Contains the analysis result
""")
async def openai_image_recognition(
    image_url: str,
    prompt: str,
    model: str = "deploy_gpt4o"
) -> TextContent:
    try:
        if not image_url:
            raise Exception("Image URL is required")
        if not prompt:
            raise Exception("Prompt is required")

        data = {
            "prompt": prompt,
            "image_url": image_url
        }

        # 使用统一的请求函数调用GPT图像识别API
        response_data = await make_unified_request(
            method="POST",
            path="/pulsar/mcp/openai/ir",
            data=data
        )

        # 提取分析结果
        analysis_result = response_data.get('result', response_data.get('data', 'No analysis result'))
        
        return TextContent(
            type="text",
            text=f"Image Analysis Result:\n{analysis_result}"
        )
        
    except Exception as e:
        return TextContent(
            type="text",
            text=f"Failed to analyze image: {str(e)}"
        )


@mcp.tool(description="""
    Function: Edit an image based on a text prompt

    Args:
        image_url (str): The URL of the image to edit.
        prompt (str): The prompt to edit the image.

    Returns:
        TextContent: Contains the result image URLs or file paths
""")
async def openai_edit_image(
    image_url: str,
    prompt: str,
) -> TextContent:
    try:
        if not image_url or not prompt:
            raise Exception("Image URL and prompt are required")
        
        #  # 将图像url转成文件格式再上传
        response = requests.get(image_url)
        if response.status_code != 200:
            raise Exception(f"图片下载失败: {response.status_code}")

        files = {
            "image": ("image.png", response.content, "image/png"),
        }
            
        data = {
            "model_name": "deploy_gpt_image_1",
            "prompt": prompt,
        }
        
        response_data = await make_unified_request(
            method="POST",
            path="/pulsar/mcp/openai/edit",
            data=data,
            files=files,      
        )
        
        return TextContent(
            type="text",
            text=f"Success. Image edited: {response_data}"
        )   
        
    except Exception as e:
        return TextContent(
            type="text",
            text=f"Failed to edit image: {str(e)}"
        )





@mcp.tool()
async def japanese_tts(
    text: str,
    format: str = "mp3",
    sample_rate: int = 16000,
    gender: str = "male",
) -> TextContent:
    """
    文本转语音工具
    
    Args:
        text: 要转换为语音的文本 (仅支持日语) eg: こんにちは、今日はいい天気ですね。
        format: 音频格式 (默认: mp3)
        sample_rate: 采样率 (默认: 16000)
        gender: 性别 (默认: male)
        
    Returns:
        TextContent: 包含成功信息或错误信息
    """
    try:
        if not text:
            raise Exception("Text is required")

        payload = {
            "text": text,
            "format": format,
            "sample_rate": sample_rate,
            "gender": gender
        }

        # 使用统一的请求函数调用语音agent API
        response_data = await make_unified_request(
            method="POST",
            path="/pulsar/mcp/self/tts",
            data=payload
        )

        return TextContent(
            type="text",
            text=f"Success. response_data: {response_data}"
        )
        
    except Exception as e:
        return TextContent(
            type="text",
            text=f"Failed to generate audio: {str(e)}"
        )

@mcp.tool()
async def ai_search(
    query: str,
    search_engine: str = "Google",
    llm_name: str = "gpt4o", 
    language: str = "English",
    bee: str = "6C44A6E0-63D4-1F9E-2EA2-3FCEA2615972",
    device: str = "android",
    app_version: str = "833",
    system_version: str = "30",
    pkg: str = "com.google.android.googlequicksearchbox",
    session_id: str = "3783f0ca-2d83-4fe2-b1b9-d8f8ee41b2b41331",
    logid: str = "456e60e7-8e36-41ac-8a09-1e7566013",
) -> TextContent:
    """
    AI搜索工具
    
    Args:
        query: 搜索查询 (必需)
        search_engine: 搜索引擎 (默认: Google)
        llm_name: LLM模型名称 (默认: gpt4o)
        language: 语言 (默认: English)
        bee: 蜜蜂标识符 (可选)
        device: 设备类型 (默认: android)
        app_version: 应用版本 (默认: 833)
        system_version: 系统版本 (默认: 30)
        pkg: 包名 (默认: com.google.android.googlequicksearchbox)
        session_id: 会话ID (可选)
        logid: 日志ID (可选)
        
    Returns:
        TextContent: 包含搜索结果或错误信息
    """
    try:
        if not query:
            raise Exception("Query is required")

        payload = {
            "query": query,
            "search_engine": search_engine,
            "llm_name": llm_name,
            "language": language,
            "bee": bee,
            "device": device,
            "app_version": app_version,
            "system_version": system_version,
            "pkg": pkg,
            "session_id": session_id,
            "logid": logid,
        }

        # 使用统一的请求函数调用AI搜索API，添加URL查询参数
        response_data = await make_unified_request(
            method="POST",
            path="/pulsar/mcp/openai/search?enc=false&st=1",
            data=payload
        )
        
        return TextContent(
            type="text",
            text=f"Success. response_data: {response_data}"
        )
        
    except Exception as e:
        return TextContent(
            type="text",
            text=f"Failed to perform search: {str(e)}"
        )



@mcp.tool(description="""
    Function: Generate a video based on a text prompt

    Args:
        prompt (str): The text prompt to generate the video from.
        model_name (str): The model name to use. Default is "kling-v1".
        negative_prompt (str, optional): The negative prompt to use. Default is "low quality, blurry, distorted, watermark, noise".
        cfg_scale (float): The CFG scale to use. Default is 0.75.
        mode (str): The mode to use. Default is "std".
        aspect_ratio (str): The aspect ratio to use. Default is "16:9".
        duration (str): The duration of the video in seconds. Default is "5".
        horizontal (int): The horizontal movement parameter. Default is 0.
        vertical (int): The vertical movement parameter. Default is 0.
        pan (int): The pan movement parameter. Default is 0.
        tilt (int): The tilt movement parameter. Default is 0.
        roll (int): The roll movement parameter. Default is 0.
        zoom (int): The zoom movement parameter. Default is 0.
        callback_url (str, optional): The callback URL. Default is "".
        external_task_id (str, optional): The external task ID. Default is "".
        api_base_url (str): The API base URL. Default is "http://gbu.gw-apisix.baidu-int.com/gbu/rest/data03".

    Returns:
        dict: A dictionary containing the result of the video generation, including the video URL or task ID.
""")
async def kling_generate_text_to_video(
    prompt: str,
    model_name: str = "kling-v1",
    negative_prompt: Optional[str] = "低质量，模糊，变形，水印，噪点",
    cfg_scale: float = 0.75,
    mode: str = "std",
    aspect_ratio: str = "16:9",
    duration: str = "5",
    horizontal: int = 1,
    vertical: int = 0,
    pan: int = 0,
    tilt: int = 0,
    roll: int = 0,
    zoom: int = 0,
    callback_url: Optional[str] = "",
    external_task_id: Optional[str] = ""
) -> Dict[str, Any]:
    
    # 构建请求数据
    request_data = {
        "model_name": model_name,
        "prompt": prompt,
        "negative_prompt": negative_prompt,
        "cfg_scale": cfg_scale,
        "mode": mode,
        "aspect_ratio": aspect_ratio,
        "duration": duration,
        "callback_url": callback_url,
        "external_task_id": external_task_id
    }
    
    # 只有当镜头控制参数不全为0时才添加camera_control
    camera_params = {
        "horizontal": horizontal,
        "vertical": vertical,
        "pan": pan,
        "tilt": tilt,
        "roll": roll,
        "zoom": zoom
    }

    # 检查是否有非零的镜头控制参数
    has_non_zero_camera_params = any(value != 0 for value in camera_params.values())
    if has_non_zero_camera_params:
        # 只包含非零参数，避免发送全零配置
        non_zero_params = {k: v for k, v in camera_params.items() if v != 0}
        request_data["camera_control"] = {
            "type": "simple",
            "config": non_zero_params
        }
    
    try:
        # 使用统一的请求函数调用Kcling文生视频API
        response_data = await make_unified_request(
            method="POST",
            path="/pulsar/mcp/openai/kcling/ttv",
            data=request_data,

        )
        
        return TextContent(
            type="text",
            text=f"Success. response_data: {response_data}"
        )
        
    except Exception as e:
        return TextContent(
            type="text",
            text=f"Failed to generate video: {str(e)}"
        )

@mcp.tool(description="""
    Function: Generate a video based on an image and a text prompt

    Args:
        image (str): The source image URL, e.g. "https://example.com/image.jpg"
        prompt (str): The text prompt to generate the video from.
        model_name (str): The model name to use. Default is "kling-v1".
        mode (str): The mode to use. Default is "pro".
        duration (str): The duration of the video in seconds. Default is "5".
        cfg_scale (float): The CFG scale to use. Default is 0.5.
        negative_prompt (str): The negative prompt to use. Default is "低质量，模糊，变形，水印，噪点".
        aspect_ratio (str): The aspect ratio to use. Default is "16:9".
        static_mask (str): The static mask image URL. Default uses a sample mask.
        dynamic_masks (List[Dict], optional): The dynamic masks list, each element contains mask and trajectories. If not provided, uses default (0,0) coordinates.
        movement_strength (float): Camera movement strength. Default is 1.0.
        rotation_strength (float): Camera rotation strength. Default is 1.0.
        elevation_strength (float): Camera elevation strength. Default is 1.0.
        translation_x (int): Translation X. Default is 0.
        translation_y (int): Translation Y. Default is 0.
        translation_z (int): Translation Z. Default is 0.
        rotation_x (int): Rotation X. Default is 0.
        rotation_y (int): Rotation Y. Default is 0.
        rotation_z (int): Rotation Z. Default is 0.
        use_camera_control (bool): Whether to use camera control. Default is False.
        camera_type (str): Camera control type. Default is "simple".
        horizontal (int): The horizontal movement parameter. Default is 0.
        vertical (int): The vertical movement parameter. Default is 0.
        pan (int): The pan movement parameter. Default is 0.
        tilt (int): The tilt movement parameter. Default is 0.
        roll (int): The roll movement parameter. Default is 0.
        zoom (int): The zoom movement parameter. Default is 0.
        notify_hook (str): The notify hook URL. Default is "".
        callback_url (str): The callback URL. Default is "".
        external_task_id (str): The external task ID. Default is "".

    Returns:
        dict: A dictionary containing the result of the video generation, including the video URL or task ID.
""")
async def kling_generate_image_to_video(
    image: str,
    prompt: str,
    static_mask: str = "",
    dynamic_masks: Optional[List[Dict[str, Any]]] = None,
    model_name: str = "kling-v1",
    mode: str = "std",
    duration: str = "5",
    cfg_scale: float = 0.5,
    negative_prompt: str = "低质量，模糊，变形，水印，噪点",
    aspect_ratio: str = "16:9",
    movement_strength: float = 1.0,
    rotation_strength: float = 1.0,
    elevation_strength: float = 1.0,
    translation_x: int = 0,
    translation_y: int = 0,
    translation_z: int = 0,
    rotation_x: int = 0,
    rotation_y: int = 0,
    rotation_z: int = 0,
    use_camera_control: bool = False,
    camera_type: str = "simple",
    horizontal: int = 0,
    vertical: int = 0,
    pan: int = 0,
    tilt: int = 0,
    roll: int = 0,
    zoom: int = 0,
    notify_hook: str = "",
    callback_url: str = "",
    external_task_id: str = ""
) -> Dict[str, Any]:

    # 构建基础请求数据（根据成功案例）
    request_data = {
        "model_name": model_name,
        "mode": mode,
        "duration": duration,
        "image": image,
        "prompt": prompt,
        "cfg_scale": cfg_scale,
        "negative_prompt": negative_prompt,
        "aspect_ratio": aspect_ratio,
        "notify_hook": notify_hook,
        "callback_url": callback_url,
        "external_task_id": external_task_id
    }
    
    if static_mask:
        request_data["static_mask"] = static_mask
    
    if dynamic_masks:
        request_data["dynamic_masks"] = dynamic_masks

    # 只有当explicitly要求使用camera_control时才添加（避免与其他控制方式冲突）
    if use_camera_control:
        camera_control = {
            "movement_strength": movement_strength,
            "rotation_strength": rotation_strength,
            "elevation_strength": elevation_strength,
            "translation_x": translation_x,
            "translation_y": translation_y,
            "translation_z": translation_z,
            "rotation_x": rotation_x,
            "rotation_y": rotation_y,
            "rotation_z": rotation_z,
            "type": camera_type,
            "config": {
                "horizontal": horizontal,
                "vertical": vertical,
                "pan": pan,
                "tilt": tilt,
                "roll": roll,
                "zoom": zoom
            }
        }
        request_data["camera_control"] = camera_control
    
    try:
        # 使用统一的请求函数调用Kcling图生视频API
        response_data = await make_unified_request(
            method="POST",
            path="/pulsar/mcp/openai/kcling/itv",
            data=request_data,
        )
        
        return TextContent(
            type="text",
            text=f"Success. response_data: {response_data}"
        )
        
    except Exception as e:
        return TextContent(
            type="text",
            text=f"Failed to generate video: {str(e)}"
        )

@mcp.tool(description="""
    Function: Query the status of a Kling image-to-video generation task

    Args:
        task_id (str): The task ID to query the status for.

    Returns:
        TextContent: Contains the task status information including progress, result URL, or error details.
""")
async def kling_query_itv_task(
    task_id: str
) -> TextContent:
    try:
        print("task_id", task_id)
        if not task_id:
            raise Exception("Task ID is required")

        # 准备表单数据
        data = {
            "task_id": task_id
        }
        print(data)
        # 使用统一的请求函数调用Kcling任务查询API
        response_data = await make_unified_request(
            method="POST",
            path="/pulsar/mcp/openai/kcling/itv_task",
            data=data,
        )
        
        return TextContent(
            type="text",
            text=f"Success. Task status: {response_data}"
        )
        
    except Exception as e:
        return TextContent(
            type="text",
            text=f"Failed to query task status: {str(e)}"
        )

@mcp.tool(description="""
    Function: Query the status of a Kling text-to-video generation task

    Args:
        task_id (str): The task ID to query the status for.

    Returns:
        TextContent: Contains the task status information including progress, result URL, or error details.
""")
async def kling_query_ttv_task(
    task_id: str
) -> TextContent:
    try:
        if not task_id:
            raise Exception("Task ID is required")

        # 准备表单数据
        data = {
            "task_id": task_id
        }

        # 使用统一的请求函数调用Kcling任务查询API
        response_data = await make_unified_request(
            method="POST",
            path="/pulsar/mcp/openai/kcling/ttv_task",
            data=data,
        )
        
        return TextContent(
            type="text",
            text=f"Success. Task status: {response_data}"
        )
        
    except Exception as e:
        return TextContent(
            type="text",
            text=f"Failed to query task status: {str(e)}"
        )


# @mcp.tool(description="""
# Function: Edit an image based on a prompt and mask

# Args:
#     image_path (str): The path to the image file to edit (local file path).
#     mask_path (str): The path to the mask file (local file path). Must be PNG format.
#     prompt (str): The prompt describing how to edit the image.
#     model_name (str, optional): The model name to use. Default is "deploy_gpt_image_1".

# Returns:
#     TextContent: Contains the result of the image editing operation, including the edited image URL or error details.
# """)
# async def edit_image(
#     image_path: str,
#     mask_path: str,
#     prompt: str,
#     model_name: str = "deploy_gpt_image_1"
# ) -> TextContent:
#     try:
#         if not image_path:
#             raise Exception("Image path is required")
#         if not mask_path:
#             raise Exception("Mask path is required")
#         if not prompt:
#             raise Exception("Prompt is required")

#         # Check if files exist
#         if not os.path.exists(image_path):
#             raise Exception(f"Image file not found: {image_path}")
#         if not os.path.exists(mask_path):
#             raise Exception(f"Mask file not found: {mask_path}")

#         # Prepare form data
#         data = {
#             "model_name": model_name,
#             "prompt": prompt
#         }

#         # Prepare files for upload
#         files = {}
        
#         # Add image file
#         with open(image_path, 'rb') as img_file:
#             image_content = img_file.read()
#             files["image"] = ("image.png", image_content, "image/png")
        
#         # Add mask file
#         with open(mask_path, 'rb') as mask_file:
#             mask_content = mask_file.read()
#             files["mask"] = ("mask.png", mask_content, "image/png")

#         # 使用统一的请求函数调用图片编辑API
#         response_data = await make_unified_request(
#             method="POST",
#             path="/pulsar/mcp/openai/edit",
#             data=data,
#             files=files
#         )
        
#         return TextContent(
#             type="text",
#             text=f"Success. Image editing completed: {response_data}"
#         )
        
#     except Exception as e:
#         return TextContent(
#             type="text",
#             text=f"Failed to edit image: {str(e)}"
#         )


# @mcp.tool(description="""
# Function: Edit an image based on a prompt and mask using URLs

# Args:
#     image_url (str): The URL of the image to edit.
#     mask_url (str): The URL of the mask image. Must be PNG format.
#     prompt (str): The prompt describing how to edit the image.
#     model_name (str, optional): The model name to use. Default is "deploy_gpt_image_1".

# Returns:
#     TextContent: Contains the result of the image editing operation, including the edited image URL or error details.
# """)
# async def edit_image_from_urls(
#     image_url: str,
#     mask_url: str,
#     prompt: str,
#     model_name: str = "deploy_gpt_image_1"
# ) -> TextContent:
#     try:
#         if not image_url:
#             raise Exception("Image URL is required")
#         if not mask_url:
#             raise Exception("Mask URL is required")
#         if not prompt:
#             raise Exception("Prompt is required")

#         import requests
        
#         # Download images from URLs
#         image_response = requests.get(image_url)
#         if image_response.status_code != 200:
#             raise Exception(f"Failed to download image: {image_response.status_code}")
            
#         mask_response = requests.get(mask_url)
#         if mask_response.status_code != 200:
#             raise Exception(f"Failed to download mask: {mask_response.status_code}")

#         # Prepare form data
#         data = {
#             "model_name": model_name,
#             "prompt": prompt
#         }

#         # Prepare files for upload
#         files = {
#             "image": ("image.png", image_response.content, "image/png"),
#             "mask": ("mask.png", mask_response.content, "image/png")
#         }

#         # 使用统一的请求函数调用图片编辑API
#         response_data = await make_unified_request(
#             method="POST",
#             path="/pulsar/mcp/openai/edit",
#             data=data,
#             files=files
#         )
        
#         return TextContent(
#             type="text",
#             text=f"Success. Image editing completed: {response_data}"
#         )
        
#     except Exception as e:
#         return TextContent(
#             type="text",
#             text=f"Failed to edit image: {str(e)}"
#         )


@mcp.tool(description="""
    Function: Generate a anime character based on a text prompt

    Args:
        prompt (str): The prompt describing the anime character to generate,only support English.
        gender (str): The gender of the anime character to generate. 0-male, 1-female, 2-other
        model_style (str): The style of the comic image. value range: ["Games", "Series", "Manhwa", "Comic", "Illustration"],
            notes: The following shows each model_style's corresponding Chinese and Japanese expressions:
            Games(游戏 / ゲーム), Series(番剧 / TVアニメ), Manhwa(韩漫 / 韓国漫画), Comic(漫画专用 / カラフル), Illustration(插画 / イラスト)
        index (int, optional): Sequential index for tracking generation order when LLM calls this tool multiple times. Starts from 1. Useful for batch processing and result ordering.
        max_retries (int, optional): Maximum number of retries for task polling. Default is 50.
        retry_interval (int, optional): Interval in seconds between task polling attempts. Default is 2.

    Returns:
        TextContent: Contains the generated image content and metadata
""")
async def ugc_tti(
    prompt: str,
    gender: int,
    model_style: str,
    index: int = 1,
    max_retries: int = 50,
    retry_interval: int = 2
) -> TextContent:
    try:
        model_style_mapping = {
            "Games": "ugc_image_animagine", 
            "Series": "ugc_image_animeseries",
            "Manhwa": "ugc_image_koreanComics",
            "Comic": "ugc_image_illlustrious",
            "Illustration": "ugc_image_awpainting",
        }
        model_tag = model_style_mapping.get(model_style, "comic_image_waiNSFWv1")

        data = {
            "prompt": prompt,
            "gender": gender,
            "template_tag": model_tag
        }

        response_data = await make_unified_request(
            method="POST",
            path="/pulsar/mcp/inner/comic/generate_role",
            data=data,
        )
        
        # get task_id, and start polling task status
        task_id = response_data.get("data", {}).get("task_id")
        cost_points = response_data.get("data", {}).get("cost_points")
        if not task_id:
            raise Exception("Task ID is not found")
        
        # polling task status
        for attempt in range(max_retries):
            task_response = await make_unified_request(
                method="POST",
                path=f"/pulsar/mcp/inner/comic/query_task",
                data={"task_id": task_id},
            )

            errno = task_response.get('errno')
            if errno == 0: 
                img_data = task_response.get("data", {}).get("img_data", [])
                images = []
                for item in img_data:
                    item_images = item.get('images', [])
                    for img in item_images:
                        if img.get('webp'):
                            images.append({
                                'url': img['webp'],
                                'format': 'webp'
                            })

                final_result = {
                    "task_id": task_id,
                    "status": "generation success",
                    "msg": task_response.get('msg', ''),
                    "cost_points": cost_points,
                    "input_parameters": data,
                    "generated_images": images,
                    "index": index,
                }
                return TextContent(
                    type="text",
                    text=f"{final_result}"
                )
            elif errno not in [0, 2200]: #2200，task is running
                final_result = {
                    "task_id": task_id,
                    "status": "generation failed",
                    "msg": task_response.get('msg', ''),
                    "cost_points": cost_points,
                    "input_parameters": data,
                    "index": index,
                }
                return TextContent(
                    type="text",
                    text=f"{final_result}"
                )
            
            # Wait before retrying
            await asyncio.sleep(retry_interval)

        final_result = {
            "task_id": task_id,
            "status": "generation failed",
            "msg": "Anime character generation task did not complete in time",
            "cost_points": cost_points,
            "input_parameters": data,
            "index": index,
        }
        return TextContent(
            type="text",
            text=f"{final_result}"
        )

    except Exception as e:
        final_result = {
            "task_id": task_id,
            "status": "generation failed",
            "msg": f"Failed to generate and query anime character: {str(e)}",
            "cost_points": cost_points,
            "input_parameters": data,
            "index": index,
        }
        return TextContent(
            type="text",
            text=f"{final_result}"
        )




@mcp.tool(description="""
    Function: Generate a pose align image based on an anime character image

    Args:
        image_url (str): The URL of the character image.
        index (int, optional): Sequential index for tracking generation order when LLM calls this tool multiple times. Starts from 1. Useful for batch processing and result ordering.
        max_retries (int, optional): Maximum number of retries for task polling. Default is 20.
        retry_interval (int, optional): Interval in seconds between task polling attempts. Default is 3.
        
        

    Returns:
        TextContent: Contains the generated image content and metadata
""")
async def anime_pose_align(
    image_url: str,
    index: int = 1,
    max_retries: int = 20,
    retry_interval: int = 3
) -> TextContent:
    try:
        if not image_url:
            raise Exception("Image URL are required")
        
        data = {
            "image_url": image_url,
        }

        response_data = await make_unified_request(
            method="POST",
            path="/pulsar/mcp/inner/comic/pose_straighten",
            data=data,
        )
        
        # get task_id, and start polling task status
        task_id = response_data.get("data", {}).get("task_id")
        cost_points = response_data.get("data", {}).get("cost_points")
        if not task_id:
            raise Exception("Task ID is not found")
        
        # polling task status
        for attempt in range(max_retries):
            task_response = await make_unified_request(
                method="POST",
                path=f"/pulsar/mcp/inner/comic/query_task",
                data={"task_id": task_id},
            )
            
            errno = task_response.get('errno')
            if errno == 0: 
                img_data = task_response.get("data", {}).get("img_data", [])
                images = []
                for item in img_data:
                    item_images = item.get('images', [])
                    for img in item_images:
                        if img.get('webp'):
                            images.append({
                                'url': img['webp'],
                                'format': 'webp'
                            })

                final_result = {
                    "task_id": task_id,
                    "status": "generation success",
                    "msg": task_response.get('msg', ''),
                    "cost_points": cost_points,
                    "input_parameters": data,
                    "generated_images": images,
                    "index": index,
                }
                return TextContent(
                    type="text",
                    text=f"{final_result}"
                )
            elif errno not in [0, 2200]: #task failed(2200-task is running)
                final_result = {
                    "task_id": task_id,
                    "status": "generation failed",
                    "msg": task_response.get('msg', ''),
                    "cost_points": cost_points,
                    "input_parameters": data,
                    "index": index,
                }
                return TextContent(
                    type="text",
                    text=f"{final_result}"
                )

            # Wait before retrying
            await asyncio.sleep(retry_interval)

        final_result = {
            "task_id": task_id,
            "status": "generation failed",
            "msg": "Pose align task did not complete in time",
            "cost_points": cost_points,
            "input_parameters": data,
            "index": index,
        }
        return TextContent(
            type="text",
            text=f"{final_result}"
        )

    except Exception as e:
        final_result = {
            "task_id": task_id,
            "status": "generation failed",
            "msg": f"Failed to generate and query pose align: {str(e)}",
            "cost_points": cost_points,
            "input_parameters": data,
            "index": index,
            }
        return TextContent(
            type="text",
            text=f"{final_result}"
        )



@mcp.tool(description="""
    Function: Generate a comic image based on prompt, scene_type,char_image and char_gender

    Args:
        prompt (str): The prompt for the comic image.Only support English.
        scene_type (str): The scene type for the comic image. value range: ["nc", "single", "double"],nc-no character,single-single character,double-double character
        char1_image (str): The URL of the character1 image pose align. if scene_type="nc", value should be the first character pose align image url, not empty.
        char2_image (str): The URL of the character2 image pose align. value = "" if scene_type in ["nc", "single"]
        char1_gender (str): The gender of the character1. value range: ["0", "1"], 0-male,1-female
        char2_gender (str): The gender of the character2. value range: ["0", "1"], 0-male,1-female, value = "" if scene_type in ["nc", "single"]
        model_style (str): The style of the comic image. value range: ["Games", "Series", "Manhwa", "Comic", "Illustration"],
            notes: The following shows each model_style's corresponding Chinese and Japanese expressions:
            Games(游戏 / ゲーム), Series(番剧 / TVアニメ), Manhwa(韩漫 / 韓国漫画), Comic(漫画专用 / カラフル), Illustration(插画 / イラスト)
        index (int, optional): Sequential index for tracking generation order when LLM calls this tool multiple times. Starts from 1. Useful for batch processing and result ordering.
        max_retries (int, optional): Maximum number of retries for task polling. Default is 50.
        retry_interval (int, optional): Interval in seconds between task polling attempts. Default is 2.

    Returns:
        TextContent: Contains the generated image content and metadata
""")
async def anime_comic_image(
    prompt: str,
    scene_type: str,
    char1_image: str,
    char2_image: str,
    char1_gender: str,
    char2_gender: str,
    model_style: str,
    index: int = 1,
    max_retries: int = 50,
    retry_interval: int = 2       
) -> TextContent:
    try:
        char2_image = "" if scene_type in ["nc", "single"] else char2_image
        char2_gender = "" if scene_type in ["nc", "single"] else char2_gender

        model_style_mapping = {
            "Games": "comic_image_animagine", 
            "Series": "comic_image_animeseries",
            "Manhwa": "comic_image_koreanComics",
            "Comic": "comic_image_waiNSFWv1",
            "Illustration": "comic_image_awpainting",
            
        }
        model_tag = model_style_mapping.get(model_style, "comic_image_waiNSFWv1")

        data = {
            "prompt": prompt,
            "scene_type": scene_type,
            "char1_image": char1_image,
            "char2_image": char2_image,
            "char1_gender": char1_gender,
            "char2_gender": char2_gender,
            "template_tag": model_tag,
        }

        response_data = await make_unified_request(
            method="POST",
            path="/pulsar/mcp/inner/comic/generate_comic",
            data=data,
        )
        
        # get task_id, and start polling task status
        task_id = response_data.get("data", {}).get("task_id")
        cost_points = response_data.get("data", {}).get("cost_points")
        if not task_id:
            raise Exception("Task ID is not found")
        
        # polling task status
        for attempt in range(max_retries):
            task_response = await make_unified_request(
                method="POST",
                path=f"/pulsar/mcp/inner/comic/query_task",
                data={"task_id": task_id},
            )

            errno = task_response.get('errno')
            if errno == 0:  # generation success      
                img_data = task_response.get("data", {}).get("img_data", [])
                images = []
                for item in img_data:
                    item_images = item.get('images', [])
                    for img in item_images:
                        if img.get('webp'):
                            images.append({
                                'url': img['webp'],
                                'format': 'webp'
                            })
                
                final_result = {
                    "task_id": task_id,
                    "status": "generation success",
                    "msg": task_response.get('msg', ''),
                    "cost_points": cost_points,
                    "input_parameters": data,
                    "generated_images": images,
                    "index": index,
                }
                    
                return TextContent(
                type="text",
                text=f"{final_result}"
            )
            elif errno not in [0, 2200]: #task failed(2200-task is running)
                final_result = {
                    "task_id": task_id,
                    "status": "generation failed",
                    "msg": task_response.get('msg', ''),
                    "cost_points": cost_points,
                    "input_parameters": data,
                    "index": index,
                }
                return TextContent(
                    type="text",
                    text=f"{final_result}"
                )

            # Wait before retrying
            await asyncio.sleep(retry_interval)
        
        final_result = {
            "task_id": task_id,
            "status": "generation failed",
            "msg": "Comic image generation task did not complete in time",
            "cost_points": cost_points,
            "input_parameters": data,
            "index": index,
        }
        return TextContent(
            type="text",
            text=f"{final_result}"
        )
    
    except Exception as e:
        final_result = {
            "task_id": task_id,
            "status": "generation failed",
            "msg": f"Failed to create comic image generation task: {str(e)}",
            "cost_points": cost_points,
            "input_parameters": data,
            "index": index,
        }
        return TextContent( 
            type="text",
            text=f"{final_result}"
        )


@mcp.tool(description="""
    Function: Generate comic script story based on topic input using streaming response

    Args:
        topic_input (str): The topic or theme for the comic script to generate (supports Japanese).
                          Example: "海をテーマにしたシナリオをください" (Please provide a scenario themed around the ocean)

    Returns:
        TextContent: Contains the generated comic script content
""")
async def generate_comic_story(
    topic_input: str
) -> TextContent:
    try:
        if not topic_input:
            raise Exception("Topic input is required")

        payload = {
            "topic_input": topic_input
        }

        # 使用流式请求调用漫画脚本生成API
        response_data = await make_unified_request(
            method="POST",
            path="/pulsar/mcp/inner/comic/generate_script",
            data=payload,
            stream=True  # 启用流式响应
        )
        
        # 返回生成的脚本内容
        return TextContent(
            type="text",
            text=response_data
        )
        
    except Exception as e:
        return TextContent(
            type="text",
            text=f"failed to generate comic script story: {str(e)}"
        )

@mcp.tool(description="""
    Function: Generate comic story chapters based on novel input, character info and chapter number.

    Args:
        input_novel (str): The novel input, required.
        chars_info (str or dict): The characters info. Supports both dictionary objects and JSON strings.
            Example: {"char1": {"name": "Jack", "gender": "male"}, "char2": {"name": "Mary", "gender": "female"}}
        chapters_num (int): The number of chapters to generate, default is 4, max is 15.

    Returns:
        TextContent: Contains the generated comic story chapters content
""")
async def generate_comic_chapters(
    input_novel: str,
    chars_info: Union[str, dict],
    chapters_num: int = 10
) -> TextContent:
    try:
        if not input_novel:
            raise Exception("input_novel is required")
        if not chars_info:
            raise Exception("chars_info is required")
       
        
        if isinstance(chars_info, str):
            chars_info = json.loads(chars_info)
        elif isinstance(chars_info, dict):
            chars_info = chars_info
        else:
            raise Exception("chars_info must be a dictionary or JSON string")
        
        # 将字典转换为JSON字符串发送给API
        chars_info_json = json.dumps(chars_info, ensure_ascii=False)
        
        payload = {
            "input_novel": input_novel,
            "chars_info": chars_info_json,
            "chapter_num": chapters_num
        }
                
        response_data = await make_unified_request(
            method="POST",
            path="/pulsar/mcp/inner/comic/generate_storyboards",
            data=payload,
            stream=True
        )
        
      
        
        return TextContent(
            type="text",
            text=response_data
        )
        
    except Exception as e:
        return TextContent(
            type="text",
            text=f"failed to generate comic story chapters: {str(e)}"
        )       


@mcp.tool(description="""
    Function: Generate image prompts based on comic story chapter and character info.
    Args:
        input_chapters (str or dict): The comic story chapter input, required.
        chars_info (str or dict): The characters info. Supports both dictionary objects and JSON strings.
                          Example: {"char1": {"name": "Jack", "gender": "male"}, "char2": {"name": "Mary", "gender": "female"}}
    Returns:
        TextContent: Contains the  image prompts content for comic image generation
""")
async def generate_comic_image_prompts(
    input_chapters: Union[str, dict],
    chars_info: Union[str, dict],
) -> TextContent:
    try:
        if not input_chapters:
            raise Exception("input_chapters is required")
        if not chars_info:
            raise Exception("chars_info is required")
        
        if isinstance(chars_info, str):
            chars_info = json.loads(chars_info)
        elif isinstance(chars_info, dict):
            chars_info = chars_info
        else:
            raise Exception("chars_info must be a dictionary or JSON string")
        
        if isinstance(input_chapters, str):
            input_chapters = json.loads(input_chapters)
        elif isinstance(input_chapters, dict):
            input_chapters = input_chapters
        else:
            raise Exception("input_chapters must be a dictionary or JSON string")
        
        chars_info_json = json.dumps(chars_info, ensure_ascii=False)
        input_chapters_json = json.dumps(input_chapters, ensure_ascii=False)

        payload = {
            "input_chapter": input_chapters_json,
            "chars_info": chars_info_json
        }
        
        response_data = await make_unified_request(
            method="POST",
            path="/pulsar/mcp/inner/comic/prompt_format",
            data=payload,
            stream=True
        )
        
        
        return TextContent(
            type="text",
            text=response_data
        )
        
    except Exception as e:
        return TextContent(
            type="text",
            text=f"failed to generate comic image prompts: {str(e)}"
        )

@mcp.tool(description="""
    Function: edit image based on image url and image prompts.
    Args:
        image_url (str): The URL of the image to edit.
        image_prompt (str): The prompt for the image to edit.Only support English.
        max_retries (int): The maximum number of retries.
        retry_interval (int): The interval between retries.
    Returns:
        TextContent: Contains the generated image content
""")
async def flux_edit_image(
    image_url: str,
    image_prompt: str,
    max_retries: int = 20,
    retry_interval: int = 5
) -> TextContent:
    try:
        if not image_url:
            raise Exception("image_url is required")
        if not image_prompt:
            raise Exception("image_prompts is required")
        
        payload = {
            "image_url": image_url,
            "edit_prompt": image_prompt
        }
        
        response_data = await make_unified_request(
            method="POST",
            path="/pulsar/mcp/inner/comic/edit",
            data=payload,
        )

        task_id = response_data.get("data", {}).get("task_id")
        if not task_id:
            raise Exception(f"task_id is required,response_data: {response_data}")
        
        # polling task status
        for attempt in range(max_retries):
            task_response = await make_unified_request(
                method="POST",
                path=f"/pulsar/mcp/inner/comic/query_task",
                data={"task_id": task_id},
            )
            
            errno = task_response.get('errno')
            if errno == 0: 
                return TextContent(
                    type="text",
                    text=f"Success. Pose align task completed: {task_response}"
                )
            elif errno not in [0, 2200]: #2200，task is running
                raise Exception(f"Pose align task failed for task_id: {task_id}")       

            # Wait before retrying
            await asyncio.sleep(retry_interval)

        raise Exception(f"flux edit image task did not complete in time for task_id: {task_id}")
    
    except Exception as e:
        return TextContent(
            type="text",
            text=f"failed to edit image: {str(e)}"
        )


@mcp.tool(description="""
    Function: edit comic story based on edit prompt and input story.
    Args:
        edit_prompt (str): The edit prompt for the comic story, required.
        input_story (str or dict): The input story, required.including story content and story title.format example:{"story_title": "xxx", "story": "xxx"}
                          
    Returns:
        TextContent: Contains the generated comic story content
""")
async def edit_comic_story(
    edit_prompt: str,
    input_story: Union[str, dict],
) -> TextContent:
    try:
        if not edit_prompt:
            raise Exception("edit_prompt is required")
        if not input_story:
            raise Exception("input_story is required")
        
        if isinstance(input_story, str):
            input_story = json.loads(input_story)
        elif isinstance(input_story, dict):
            input_story = input_story
        else:
            raise Exception("input_story must be a dictionary or JSON string") 
        
        input_story_json = json.dumps(input_story, ensure_ascii=False)

        payload = {
            "story_input": input_story_json,
            "edit_prompt": edit_prompt
        }
        
        response_data = await make_unified_request(
            method="POST",
            path="/pulsar/mcp/inner/comic/edit_script",
            data=payload,
            stream=True
        )
        
        
        return TextContent(
            type="text",
            text=response_data
        )
        
    except Exception as e:
        return TextContent(
            type="text",
            text=f"failed to edit comic story: {str(e)}"
        )


@mcp.tool(description="""
    Function: edit comic chapters based on edit prompt and input chapters.
    Args:
        edit_prompt (str): The edit prompt for the comic chapters, required.
        input_chapters (str or dict): The input chapters, required.Format example:
        {"title": "chapter_title", "chapter_image": {"1": {"description": "scene_desc", "dialogue": [{"name": "char_name", "text": "dialogue_text"}], "aside": "aside_text"}}}
                          
                          
    Returns:
        TextContent: Contains the generated comic chapters content
""")
async def edit_comic_chapters(
    edit_prompt: str,
    input_chapters: Union[str, dict],
) -> TextContent:
    try:
        if not edit_prompt:
            raise Exception("edit_prompt is required")
        if not input_chapters:
            raise Exception("input_chapters is required")
        
        if isinstance(input_chapters, str):
            input_chapters = json.loads(input_chapters)
        elif isinstance(input_chapters, dict):
            input_chapters = input_chapters
        else:
            raise Exception("input_chapters must be a dictionary or JSON string") 
        
        input_chapters_json = json.dumps(input_chapters, ensure_ascii=False)

        payload = {
            "chapters_description_input": input_chapters_json,
            "edit_prompt": edit_prompt
        }
        
        response_data = await make_unified_request(
            method="POST",
            path="/pulsar/mcp/inner/comic/edit_storyboards",
            data=payload,
            stream=True
        )
        
        
        return TextContent(
            type="text",
            text=response_data
        )
        
    except Exception as e:
        return TextContent(
            type="text",
            text=f"failed to edit comic chapters: {str(e)}"
        )


def main():
    """Main entry point for the MCP server."""
    mcp.run(transport="stdio")

if __name__ == "__main__":
    main()
