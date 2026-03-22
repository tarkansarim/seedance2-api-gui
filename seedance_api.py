import os
import requests
import time
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class SeedanceAPI:
    def __init__(self, api_key=None):
        """
        Initialize the Seedance 2.0 API client.
        :param api_key: Your MuAPI.ai API key. Defaults to MUAPI_API_KEY environment variable.
        """
        self.api_key = api_key or os.getenv("MUAPI_API_KEY")
        if not self.api_key:
            raise ValueError("API Key is required. Set MUAPI_API_KEY in .env or pass it to the constructor.")
        
        self.base_url = "https://api.muapi.ai/api/v1"
        self.headers = {
            "x-api-key": self.api_key,
            "Content-Type": "application/json"
        }

    def text_to_video(self, prompt, aspect_ratio="16:9", duration=5, quality="basic"):
        """
        Submits a Seedance 2.0 Text-to-Video (T2V) generation task.
        
        :param prompt: The text prompt describing the video.
        :param aspect_ratio: Video aspect ratio (e.g., '16:9', '9:16').
        :param duration: Video duration in seconds.
        :param quality: Output quality ('basic' or 'high').
        :return: JSON response from the Seedance 2.0 API.
        """
        endpoint = f"{self.base_url}/seedance-v2.0-t2v"
        payload = {
            "prompt": prompt,
            "aspect_ratio": aspect_ratio,
            "duration": duration,
            "quality": quality
        }
        return self._post_request(endpoint, payload)

    def image_to_video(self, prompt, images_list, aspect_ratio="16:9", duration=5, quality="basic"):
        """
        Submits a Seedance 2.0 Image-to-Video (I2V) generation task.
        
        :param prompt: Optional text prompt to guide the animation.
        :param images_list: A list of image URLs to animate.
        :param aspect_ratio: Video aspect ratio.
        :param duration: Video duration.
        :param quality: Output quality.
        :return: JSON response from the Seedance 2.0 API.
        """
        endpoint = f"{self.base_url}/seedance-v2.0-i2v"
        payload = {
            "prompt": prompt,
            "images_list": images_list,
            "aspect_ratio": aspect_ratio,
            "duration": duration,
            "quality": quality
        }
        return self._post_request(endpoint, payload)

    def extend_video(self, request_id, prompt="", duration=5, quality="basic"):
        """
        Extends a previously generated Seedance 2.0 video.
        
        :param request_id: The ID of the video segment to extend.
        :param prompt: Optional text prompt for the extension.
        :return: JSON response from the Seedance 2.0 API.
        """
        endpoint = f"{self.base_url}/seedance-v2.0-extend"
        payload = {
            "request_id": request_id,
            "prompt": prompt,
            "duration": duration,
            "quality": quality
        }
        return self._post_request(endpoint, payload)

    def video_edit(self, prompt, video_urls, images_list=None, aspect_ratio="16:9", quality="basic", remove_watermark=False):
        """
        Submits a Seedance 2.0 Video-Edit generation task.
        
        :param prompt: The text prompt describing the edit.
        :param video_urls: A list of video URLs to edit.
        :param images_list: Optional list of image URLs.
        :param aspect_ratio: Video aspect ratio.
        :param quality: Output quality.
        :param remove_watermark: Whether to remove watermark.
        :return: JSON response from the Seedance 2.0 API.
        """
        endpoint = f"{self.base_url}/seedance-v2.0-video-edit"
        payload = {
            "prompt": prompt,
            "video_urls": video_urls,
            "images_list": images_list or [],
            "aspect_ratio": aspect_ratio,
            "quality": quality,
            "remove_watermark": remove_watermark
        }
        return self._post_request(endpoint, payload)

    def upload_file(self, file_path):
        """
        Uploads a local file to MuAPI and returns a hosted URL.
        Use this to convert local images/videos to URLs for the API.
        """
        endpoint = f"{self.base_url}/upload_file"
        headers = {"x-api-key": self.api_key}
        with open(file_path, "rb") as f:
            files = {"file": (os.path.basename(file_path), f)}
            response = requests.post(endpoint, files=files, headers=headers)
        response.raise_for_status()
        return response.json().get("url") or response.json().get("file_url")

    def _resolve_images(self, images_list):
        """
        Takes a list of image paths or URLs.
        Local paths get uploaded automatically, URLs pass through.
        """
        resolved = []
        for img in images_list:
            if os.path.isfile(img):
                print(f"Uploading local file: {img}")
                url = self.upload_file(img)
                print(f"  → {url}")
                resolved.append(url)
            else:
                resolved.append(img)
        return resolved

    def _post_request(self, endpoint, payload):
        if "images_list" in payload and payload["images_list"]:
            payload["images_list"] = self._resolve_images(payload["images_list"])
        if "video_urls" in payload and payload["video_urls"]:
            payload["video_urls"] = self._resolve_images(payload["video_urls"])
        response = requests.post(endpoint, json=payload, headers=self.headers)
        response.raise_for_status()
        return response.json()

    def get_result(self, request_id):
        """
        Polls for the result of a generation task.
        """
        endpoint = f"{self.base_url}/predictions/{request_id}/result"
        response = requests.get(endpoint, headers=self.headers)
        response.raise_for_status()
        return response.json()

    def wait_for_completion(self, request_id, poll_interval=5, timeout=600, save_to=None):
        """
        Waits for the video generation to complete and returns the result.
        Optionally downloads the video to save_to directory (defaults to ./output/).
        """
        start_time = time.time()
        while time.time() - start_time < timeout:
            result = self.get_result(request_id)
            status = result.get("status")

            if status == "completed":
                # Find the video URL from whichever key the API uses
                video_url = None
                for key in ("url", "video_url", "output_url", "result_url", "output", "video"):
                    if result.get(key) and isinstance(result[key], str) and result[key].startswith("http"):
                        video_url = result[key]
                        break
                if not video_url:
                    # Check 'outputs' list (MuAPI returns URLs here)
                    outputs = result.get("outputs", [])
                    if outputs and isinstance(outputs, list) and len(outputs) > 0:
                        video_url = outputs[0]
                if video_url:
                    save_dir = save_to or os.path.join(os.path.dirname(__file__), "output")
                    os.makedirs(save_dir, exist_ok=True)
                    filename = f"seedance_{request_id}.mp4"
                    filepath = os.path.join(save_dir, filename)
                    print(f"Downloading video to {filepath}...")
                    r = requests.get(video_url, stream=True)
                    with open(filepath, "wb") as f:
                        for chunk in r.iter_content(chunk_size=8192):
                            f.write(chunk)
                    print(f"Saved: {filepath}")
                    result["local_path"] = filepath
                return result
            elif status == "failed":
                raise Exception(f"Video generation failed: {result.get('error')}")

            print(f"Status: {status}. Waiting {poll_interval} seconds...")
            time.sleep(poll_interval)

        raise TimeoutError("Timed out waiting for video generation to complete.")

if __name__ == "__main__":
    # Example usage for T2V
    try:
        api = SeedanceAPI()
        prompt = "A cinematic shot of a futuristic city with neon lights, 8k resolution"
        
        print(f"Submitting T2V task with prompt: {prompt}")
        submission = api.text_to_video(prompt=prompt, duration=5)
        request_id = submission.get("request_id")
        print(f"Task submitted. Request ID: {request_id}")
        
        print("Waiting for completion...")
        result = api.wait_for_completion(request_id)
        print(f"Generation completed! Full response: {result}")
        
    except Exception as e:
        print(f"Error: {e}")
