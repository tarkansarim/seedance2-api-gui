import os
import tempfile
import requests
import time
from PIL import Image
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

    def omni_reference(self, prompt, images=None, video_urls=None, audio_urls=None,
                       aspect_ratio="16:9", duration=5, upscale_4k=False):
        """
        Submits a Seedance 2.0 Omni Reference generation task.
        Combines text, images, videos, and audio as multi-modal references.

        Use @image1-@image9, @video1-@video3, @audio1-@audio3 in the prompt
        to reference each asset.

        :param prompt: Text prompt with @imageN/@videoN/@audioN references.
        :param images: List of up to 9 image URLs or local paths.
        :param video_urls: List of up to 3 video URLs or local paths.
        :param audio_urls: List of up to 3 audio URLs or local paths.
        :param aspect_ratio: Video aspect ratio.
        :param duration: Video duration in seconds (4-15).
        :param upscale_4k: Upscale output to 4K resolution.
        :return: JSON response from the Seedance 2.0 API.
        """
        endpoint = f"{self.base_url}/seedance-2.0-omni-reference"
        payload = {
            "prompt": prompt,
            "aspect_ratio": aspect_ratio,
            "duration": duration,
        }
        if upscale_4k:
            payload["upscale_resolution"] = "4k"
        # Resolve and add numbered image fields (image_1 .. image_9)
        if images:
            resolved_imgs = self._resolve_images(images)
            for i, url in enumerate(resolved_imgs[:9], 1):
                payload[f"image_{i}"] = url
        # Resolve and add numbered video fields (video_url_1 .. video_url_3)
        if video_urls:
            resolved_vids = self._resolve_images(video_urls)
            for i, url in enumerate(resolved_vids[:3], 1):
                payload[f"video_url_{i}"] = url
        # Resolve and add numbered audio fields (audio_url_1 .. audio_url_3)
        if audio_urls:
            resolved_auds = self._resolve_images(audio_urls)
            for i, url in enumerate(resolved_auds[:3], 1):
                payload[f"audio_url_{i}"] = url

        response = requests.post(endpoint, json=payload, headers=self.headers)
        response.raise_for_status()
        return response.json()

    @staticmethod
    def _compress_image(file_path, max_bytes=9_500_000):
        """
        If an image file exceeds max_bytes, convert to JPEG starting at
        max quality and step down until it fits. No resolution change.
        Returns the original path if already small enough, or a temp path.
        """
        IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}
        ext = os.path.splitext(file_path)[1].lower()
        if ext not in IMAGE_EXTS:
            return file_path

        if os.path.getsize(file_path) <= max_bytes:
            return file_path

        img = Image.open(file_path)
        if img.mode == "RGBA":
            img = img.convert("RGB")

        name = os.path.basename(file_path)
        tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
        tmp.close()

        for quality in range(98, 10, -5):
            img.save(tmp.name, format="JPEG", quality=quality)
            size = os.path.getsize(tmp.name)
            if size <= max_bytes:
                print(f"Compressed {name}: {os.path.getsize(file_path)/1e6:.1f}MB → {size/1e6:.1f}MB (q={quality})")
                return tmp.name

        # Last resort: quality 10 still too big, shouldn't happen
        print(f"Warning: {name} still {size/1e6:.1f}MB after max compression")
        return tmp.name

    def upload_file(self, file_path):
        """
        Uploads a local file to MuAPI and returns a hosted URL.
        Auto-downscales images over 10MB using Lanczos resampling.
        """
        upload_path = self._compress_image(file_path)
        try:
            endpoint = f"{self.base_url}/upload_file"
            headers = {"x-api-key": self.api_key}
            last_err = None
            for attempt in range(3):
                with open(upload_path, "rb") as f:
                    # Keep original filename for the API
                    fname = os.path.basename(file_path)
                    if upload_path != file_path:
                        fname = os.path.splitext(fname)[0] + ".jpg"
                    files = {"file": (fname, f)}
                    response = requests.post(endpoint, files=files, headers=headers)
                if response.ok:
                    return response.json().get("url") or response.json().get("file_url")
                last_err = f"{response.status_code}: {response.text}"
                print(f"upload_file attempt {attempt+1} FAILED for {file_path} — {last_err}", flush=True)
                if response.status_code < 500 and response.status_code != 429:
                    break
                time.sleep(2)
            raise Exception(f"upload_file failed for {os.path.basename(file_path)}: {last_err}")
        finally:
            if upload_path != file_path:
                os.unlink(upload_path)  # clean up temp file

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
