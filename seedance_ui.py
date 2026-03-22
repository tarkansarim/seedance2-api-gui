import os
import sys
import time
import subprocess
import flet as ft

sys.path.insert(0, os.path.dirname(__file__))
from seedance_api import SeedanceAPI


def main(page: ft.Page):
    page.title = "Seedance 2.0"
    page.window.width = 1280
    page.window.height = 800
    page.padding = 20
    page.theme_mode = ft.ThemeMode.DARK

    # State
    api = None
    generating = False

    # Shared controls
    status_text = ft.Text("Ready", size=14, weight=ft.FontWeight.BOLD)
    progress_ring = ft.ProgressRing(visible=False, width=20, height=20)
    elapsed_text = ft.Text("", size=12)
    log_field = ft.TextField(
        multiline=True, read_only=True, min_lines=4, max_lines=4,
        expand=True, text_size=11, border_color=ft.Colors.OUTLINE,
    )
    history_list = ft.ListView(expand=True, spacing=5)

    # Video preview
    preview_placeholder = ft.Text("No video yet", size=14, italic=True, color=ft.Colors.ON_SURFACE)
    preview_container = ft.Container(
        content=ft.Column([
            ft.Text("Preview", size=16, weight=ft.FontWeight.BOLD),
            preview_placeholder,
        ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, alignment=ft.MainAxisAlignment.CENTER),
        bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
        border_radius=10,
        padding=10,
        expand=True,
        alignment=ft.Alignment(0, 0),
    )

    current_preview_path = [None]

    def load_preview(video_path_or_url):
        print(f"[PREVIEW] load_preview called with: {video_path_or_url}", flush=True)
        current_preview_path[0] = video_path_or_url
        local = video_path_or_url if os.path.exists(video_path_or_url) else None
        print(f"[PREVIEW] local={local}", flush=True)

        # Try to extract a thumbnail
        thumb_path = None
        if local:
            thumb_path = local + ".thumb.png"
            try:
                r = subprocess.run(
                    ["ffmpeg", "-y", "-i", local, "-ss", "00:00:01", "-vframes", "1", "-q:v", "2", thumb_path],
                    capture_output=True, text=True, timeout=10,
                )
                print(f"[PREVIEW] ffmpeg returncode={r.returncode}", flush=True)
                if r.returncode != 0:
                    print(f"[PREVIEW] ffmpeg stderr: {r.stderr[:200]}", flush=True)
                    thumb_path = None
            except Exception as ex:
                print(f"[PREVIEW] ffmpeg exception: {ex}", flush=True)
                thumb_path = None

        print(f"[PREVIEW] thumb_path={thumb_path}, exists={os.path.exists(thumb_path) if thumb_path else False}", flush=True)

        preview_controls = [ft.Text("Preview", size=16, weight=ft.FontWeight.BOLD)]

        if thumb_path and os.path.exists(thumb_path):
            print(f"[PREVIEW] Loading thumbnail image: {thumb_path}", flush=True)
            preview_controls.append(ft.Image(src=thumb_path, fit=ft.ImageFit.CONTAIN, expand=True))
        else:
            print(f"[PREVIEW] No thumbnail available", flush=True)
            preview_controls.append(ft.Text("Thumbnail unavailable", italic=True, size=12))

        preview_controls.append(
            ft.Button(
                content="Play in Player",
                icon=ft.Icons.PLAY_CIRCLE_FILLED,
                on_click=lambda e: subprocess.Popen(["xdg-open", current_preview_path[0]]),
            )
        )

        preview_container.content = ft.Column(
            preview_controls,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            expand=True,
        )
        print(f"[PREVIEW] Calling page.update()", flush=True)
        page.update()
        print(f"[PREVIEW] Done", flush=True)

    def log(msg):
        log_field.value = (log_field.value or "") + msg + "\n"
        page.update()

    def set_status(text, busy=False):
        status_text.value = text
        progress_ring.visible = busy
        page.update()

    def add_to_history(mode, prompt, path, url):
        def play_in_preview(e, u=url, p=path):
            src = p if p and os.path.exists(p) else u
            if src:
                load_preview(src)

        history_list.controls.insert(0, ft.Container(
            content=ft.Column([
                ft.Text(f"[{mode}] {prompt[:50]}...", size=11, weight=ft.FontWeight.BOLD),
                ft.Row([
                    ft.TextButton("Play", icon=ft.Icons.PLAY_CIRCLE, on_click=play_in_preview),
                    ft.TextButton("Open", on_click=lambda e, p=path: subprocess.Popen(["xdg-open", p]) if p else None) if path else ft.Container(),
                    ft.TextButton("Copy URL", on_click=lambda e, u=url: page.set_clipboard(u)) if url else ft.Container(),
                ], spacing=0),
            ], spacing=2),
            bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST, border_radius=8, padding=8,
        ))
        page.update()

    # --- Shared parameter builders ---
    def make_aspect_ratio():
        return ft.Dropdown(
            label="Aspect Ratio", width=140, value="16:9",
            options=[ft.dropdown.Option(r) for r in ["16:9", "9:16", "1:1", "4:3", "3:4"]],
        )

    def make_duration():
        return ft.Dropdown(
            label="Duration (s)", width=120, value="5",
            options=[ft.dropdown.Option(str(d)) for d in range(4, 16)],
        )

    def make_quality():
        return ft.Dropdown(
            label="Quality", width=120, value="basic",
            options=[ft.dropdown.Option(q) for q in ["basic", "high"]],
        )

    def make_prompt(hint="Describe the video..."):
        return ft.TextField(
            label="Prompt", multiline=True, min_lines=3, max_lines=4,
            expand=True, hint_text=hint,
        )

    # --- Generation logic ---
    def run_generation(mode, api_call, prompt_text):
        nonlocal generating
        print(f"run_generation called: mode={mode}, generating={generating}, api={'OK' if api else 'NONE'}", flush=True)
        if generating:
            print("BLOCKED: already generating", flush=True)
            return
        if not api:
            print("BLOCKED: no API", flush=True)
            log("ERROR: API key not set. Put your key in .env")
            return
        generating = True
        start = time.time()

        def worker():
            nonlocal generating
            try:
                set_status(f"Submitting {mode}...", busy=True)
                log(f"[{mode}] Submitting: {prompt_text[:80]}...")
                result = api_call()
                request_id = result.get("request_id")
                log(f"Request ID: {request_id}")
                set_status("Processing...", busy=True)

                while True:
                    poll = api.get_result(request_id)
                    s = poll.get("status", "unknown")
                    elapsed = int(time.time() - start)
                    elapsed_text.value = f"{elapsed}s"
                    set_status(f"Status: {s}", busy=True)

                    if s == "completed":
                        video_url = None
                        outputs = poll.get("outputs", [])
                        if outputs:
                            video_url = outputs[0]
                        for key in ("url", "video_url", "output_url"):
                            if poll.get(key) and isinstance(poll[key], str) and poll[key].startswith("http"):
                                video_url = poll[key]
                                break

                        local_path = None
                        if video_url:
                            import requests
                            save_dir = os.path.join(os.path.dirname(__file__), "output")
                            os.makedirs(save_dir, exist_ok=True)
                            filename = f"seedance_{request_id}.mp4"
                            local_path = os.path.join(save_dir, filename)
                            log(f"Downloading to {local_path}...")
                            r = requests.get(video_url, stream=True)
                            with open(local_path, "wb") as f:
                                for chunk in r.iter_content(chunk_size=8192):
                                    f.write(chunk)

                        elapsed = int(time.time() - start)
                        log(f"Completed in {elapsed}s!")
                        set_status(f"Done! ({elapsed}s)", busy=False)
                        elapsed_text.value = f"{elapsed}s total"
                        add_to_history(mode, prompt_text, local_path, video_url)

                        # Auto-load preview
                        preview_src = local_path if local_path and os.path.exists(local_path) else video_url
                        print(f"[WORKER] video_url={video_url}", flush=True)
                        print(f"[WORKER] local_path={local_path}, exists={os.path.exists(local_path) if local_path else False}", flush=True)
                        print(f"[WORKER] preview_src={preview_src}", flush=True)
                        if preview_src:
                            load_preview(preview_src)

                        page.update()
                        break

                    elif s == "failed":
                        log(f"FAILED: {poll.get('error', 'Unknown error')}")
                        set_status("Failed", busy=False)
                        break

                    time.sleep(5)

            except Exception as ex:
                log(f"ERROR: {ex}")
                set_status("Error", busy=False)
            finally:
                generating = False
                page.update()

        page.run_thread(worker)

    # ==================== TAB 1: Text to Video ====================
    t2v_prompt = make_prompt("A cinematic shot of a futuristic city...")
    t2v_aspect = make_aspect_ratio()
    t2v_duration = make_duration()
    t2v_quality = make_quality()

    def t2v_generate(e):
        print(f"T2V CLICKED! prompt={t2v_prompt.value}, api={api}", flush=True)
        log(f"Button clicked! generating={generating}, api={'OK' if api else 'NONE'}")
        run_generation("T2V", lambda: api.text_to_video(
            prompt=t2v_prompt.value,
            aspect_ratio=t2v_aspect.value,
            duration=int(t2v_duration.value),
            quality=t2v_quality.value,
        ), t2v_prompt.value or "")

    t2v_tab = ft.Container(
        content=ft.Column([
            t2v_prompt,
            ft.Row([t2v_aspect, t2v_duration, t2v_quality]),
            ft.Button(content="Generate Video", icon=ft.Icons.PLAY_ARROW, on_click=t2v_generate),
        ], spacing=12, scroll=ft.ScrollMode.AUTO),
        padding=15,
    )

    # ==================== TAB 2: Image to Video ====================
    i2v_prompt = make_prompt("Animate this image with gentle motion...")
    i2v_aspect = make_aspect_ratio()
    i2v_duration = make_duration()
    i2v_quality = make_quality()
    i2v_images = ft.TextField(label="Image URLs or paths (one per line)", multiline=True, min_lines=2, max_lines=3, expand=True)
    i2v_picked = ft.Text("", size=11)

    def pick_images(e):
        try:
            result = subprocess.run(
                ["zenity", "--file-selection", "--multiple", "--separator=\n",
                 "--title=Select images", "--file-filter=Images|*.png *.jpg *.jpeg *.webp *.bmp"],
                capture_output=True, text=True, timeout=60,
            )
            if result.returncode == 0 and result.stdout.strip():
                paths = result.stdout.strip().split("\n")
                existing = i2v_images.value.strip()
                i2v_images.value = (existing + "\n" if existing else "") + "\n".join(paths)
                i2v_picked.value = f"{len(paths)} file(s) added"
                page.update()
        except Exception as ex:
            log(f"File picker error: {ex}")

    async def i2v_generate(e):
        imgs = [line.strip() for line in (i2v_images.value or "").split("\n") if line.strip()]
        if not imgs:
            log("ERROR: Add at least one image")
            return
        run_generation("I2V", lambda: api.image_to_video(
            prompt=i2v_prompt.value or "",
            images_list=imgs,
            aspect_ratio=i2v_aspect.value,
            duration=int(i2v_duration.value),
            quality=i2v_quality.value,
        ), i2v_prompt.value or "")

    i2v_tab = ft.Container(
        content=ft.Column([
            i2v_prompt,
            ft.Row([
                i2v_images,
                ft.Column([
                    ft.Button(content="Browse...", icon=ft.Icons.FOLDER_OPEN, on_click=pick_images),
                    i2v_picked,
                ]),
            ], spacing=10),
            ft.Row([i2v_aspect, i2v_duration, i2v_quality]),
            ft.Button(content="Generate Video", icon=ft.Icons.PLAY_ARROW, on_click=i2v_generate),
        ], spacing=12, scroll=ft.ScrollMode.AUTO),
        padding=15,
    )

    # ==================== TAB 3: Video Edit ====================
    ve_prompt = make_prompt("Edit this video to add slow motion...")
    ve_aspect = make_aspect_ratio()
    ve_quality = make_quality()
    ve_videos = ft.TextField(label="Video URLs or paths (one per line)", multiline=True, min_lines=2, max_lines=3, expand=True)
    ve_images = ft.TextField(label="Optional image URLs/paths (one per line)", multiline=True, min_lines=1, max_lines=2, expand=True)
    ve_watermark = ft.Checkbox(label="Remove watermark", value=False)
    ve_picked = ft.Text("", size=11)

    def pick_videos(e):
        try:
            result = subprocess.run(
                ["zenity", "--file-selection", "--multiple", "--separator=\n",
                 "--title=Select videos", "--file-filter=Videos|*.mp4 *.mkv *.avi *.mov *.webm"],
                capture_output=True, text=True, timeout=60,
            )
            if result.returncode == 0 and result.stdout.strip():
                paths = result.stdout.strip().split("\n")
                existing = ve_videos.value.strip()
                ve_videos.value = (existing + "\n" if existing else "") + "\n".join(paths)
                ve_picked.value = f"{len(paths)} video(s) added"
                page.update()
        except Exception as ex:
            log(f"File picker error: {ex}")

    async def ve_generate(e):
        vids = [line.strip() for line in (ve_videos.value or "").split("\n") if line.strip()]
        imgs = [line.strip() for line in (ve_images.value or "").split("\n") if line.strip()]
        if not vids:
            log("ERROR: Add at least one video")
            return
        run_generation("Edit", lambda: api.video_edit(
            prompt=ve_prompt.value or "",
            video_urls=vids,
            images_list=imgs if imgs else None,
            aspect_ratio=ve_aspect.value,
            quality=ve_quality.value,
            remove_watermark=ve_watermark.value,
        ), ve_prompt.value or "")

    ve_tab = ft.Container(
        content=ft.Column([
            ve_prompt,
            ft.Row([
                ve_videos,
                ft.Column([
                    ft.Button(content="Browse videos...", icon=ft.Icons.VIDEO_FILE, on_click=pick_videos),
                    ve_picked,
                ]),
            ], spacing=10),
            ve_images,
            ft.Row([ve_aspect, ve_quality, ve_watermark]),
            ft.Button(content="Edit Video", icon=ft.Icons.EDIT, on_click=ve_generate),
        ], spacing=12, scroll=ft.ScrollMode.AUTO),
        padding=15,
    )

    # ==================== TAB 4: Extend Video ====================
    ext_request_id = ft.TextField(label="Request ID (from previous generation)", expand=True)
    ext_prompt = make_prompt("Continue the scene with...")
    ext_duration = make_duration()
    ext_quality = make_quality()

    async def ext_generate(e):
        rid = ext_request_id.value.strip()
        if not rid:
            log("ERROR: Enter a request ID")
            return
        run_generation("Extend", lambda: api.extend_video(
            request_id=rid,
            prompt=ext_prompt.value or "",
            duration=int(ext_duration.value),
            quality=ext_quality.value,
        ), ext_prompt.value or rid)

    ext_tab = ft.Container(
        content=ft.Column([
            ext_request_id,
            ext_prompt,
            ft.Row([ext_duration, ext_quality]),
            ft.Button(content="Extend Video", icon=ft.Icons.FAST_FORWARD, on_click=ext_generate),
        ], spacing=12, scroll=ft.ScrollMode.AUTO),
        padding=15,
    )

    # ==================== Main Layout ====================
    tabs = ft.Tabs(
        selected_index=0,
        length=4,
        expand=True,
        content=ft.Column(
            expand=True,
            controls=[
                ft.TabBar(
                    tabs=[
                        ft.Tab(label="Text to Video", icon=ft.Icons.TEXT_FIELDS),
                        ft.Tab(label="Image to Video", icon=ft.Icons.IMAGE),
                        ft.Tab(label="Video Edit", icon=ft.Icons.EDIT),
                        ft.Tab(label="Extend Video", icon=ft.Icons.FAST_FORWARD),
                    ],
                ),
                ft.TabBarView(
                    expand=True,
                    controls=[t2v_tab, i2v_tab, ve_tab, ext_tab],
                ),
            ],
        ),
    )

    status_bar = ft.Row([
        progress_ring,
        status_text,
        ft.Container(expand=True),
        elapsed_text,
    ], alignment=ft.MainAxisAlignment.START)

    # Left side: tabs + status + log
    left_panel = ft.Column([
        tabs,
        ft.Divider(),
        status_bar,
        ft.Text("Log", size=12, weight=ft.FontWeight.BOLD),
        log_field,
    ], expand=2)

    # Right side: preview + history
    right_panel = ft.Column([
        preview_container,
        ft.Divider(),
        ft.Text("History", size=14, weight=ft.FontWeight.BOLD),
        history_list,
    ], expand=1, width=400)

    page.add(
        ft.Text("Seedance 2.0", size=24, weight=ft.FontWeight.BOLD),
        ft.Divider(),
        ft.Row([left_panel, ft.VerticalDivider(), right_panel], expand=True),
    )

    # Init API
    try:
        api = SeedanceAPI()
        log("API initialized successfully")
    except Exception as ex:
        log(f"API init failed: {ex}")
        log("Make sure .env contains MUAPI_API_KEY=your_key")


ft.run(main)
