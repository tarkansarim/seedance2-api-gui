import os
import sys
import json
import time
import uuid
import subprocess
import logging
import flet as ft
import platform
import flet_video as ftv

sys.path.insert(0, os.path.dirname(__file__))
from seedance_api import SeedanceAPI


def open_file(path):
    """Open a file with the system default application (cross-platform)."""
    if platform.system() == "Windows":
        os.startfile(path)
    elif platform.system() == "Darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])

_log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "seedance_debug.log")
_logger = logging.getLogger("seedance_ui")
_logger.setLevel(logging.DEBUG)
_handler = logging.FileHandler(_log_path, mode="w")
_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S"))
_logger.addHandler(_handler)
_logger.propagate = False
log_debug = _logger.debug
log_info = _logger.info
log_error = _logger.error


def main(page: ft.Page):
    log_info("main() started")
    page.title = "Seedance 2.0"
    page.window.width = page.width * 0.85 if page.width else 1700
    page.window.height = page.height * 0.85 if page.height else 1050
    page.window.min_width = 900
    page.window.min_height = 1050
    page.padding = 20
    page.theme_mode = ft.ThemeMode.DARK

    # State
    api = None
    jobs = []  # list of job dicts
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")

    def mask_key(key):
        """Show first 4 and last 4 chars, mask the rest."""
        if not key or len(key) <= 10:
            return key or ""
        return key[:4] + "*" * (len(key) - 8) + key[-4:]

    def load_api_key():
        """Load API key from .env file."""
        if os.path.exists(env_path):
            with open(env_path) as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("MUAPI_API_KEY="):
                        return line.split("=", 1)[1].strip().strip('"').strip("'")
        return ""

    def save_api_key(key):
        """Save API key to .env file."""
        lines = []
        found = False
        if os.path.exists(env_path):
            with open(env_path) as f:
                for line in f:
                    if line.strip().startswith("MUAPI_API_KEY="):
                        lines.append(f"MUAPI_API_KEY={key}\n")
                        found = True
                    else:
                        lines.append(line)
        if not found:
            lines.append(f"MUAPI_API_KEY={key}\n")
        with open(env_path, "w") as f:
            f.writelines(lines)

    current_key = load_api_key()
    api_key_display = ft.Text(mask_key(current_key) if current_key else "No API key set", size=12,
                               color=ft.Colors.ON_SURFACE if current_key else ft.Colors.ERROR)
    api_key_input = ft.TextField(label="Paste API key", password=True, can_reveal_password=True,
                                  width=400, text_size=13, visible=False)
    api_key_edit_btn = ft.TextButton("Edit")
    api_key_save_btn = ft.TextButton("Save", visible=False)
    api_key_cancel_btn = ft.TextButton("Cancel", visible=False)

    def toggle_key_edit(e):
        api_key_input.visible = True
        api_key_save_btn.visible = True
        api_key_cancel_btn.visible = True
        api_key_edit_btn.visible = False
        api_key_input.value = ""
        page.update()

    def save_key_click(e):
        nonlocal api, current_key
        new_key = (api_key_input.value or "").strip()
        if new_key:
            save_api_key(new_key)
            current_key = new_key
            os.environ["MUAPI_API_KEY"] = new_key
            api_key_display.value = mask_key(new_key)
            api_key_display.color = ft.Colors.ON_SURFACE
            try:
                api = SeedanceAPI()
                log("API re-initialized with new key")
            except Exception as ex:
                log(f"API init failed with new key: {ex}")
        api_key_input.visible = False
        api_key_save_btn.visible = False
        api_key_cancel_btn.visible = False
        api_key_edit_btn.visible = True
        page.update()

    def cancel_key_edit(e):
        api_key_input.visible = False
        api_key_save_btn.visible = False
        api_key_cancel_btn.visible = False
        api_key_edit_btn.visible = True
        page.update()

    api_key_edit_btn.on_click = toggle_key_edit
    api_key_save_btn.on_click = save_key_click
    api_key_cancel_btn.on_click = cancel_key_edit

    api_key_section = ft.Column([
        ft.Row([
            ft.Icon(ft.Icons.KEY, size=16),
            ft.Text("MuAPI Key:", size=12, weight=ft.FontWeight.BOLD),
            api_key_display,
            api_key_edit_btn,
        ]),
        ft.Row([api_key_input, api_key_save_btn, api_key_cancel_btn]),
    ], spacing=8)

    def open_settings(e):
        settings_dialog.open = True
        page.update()

    def close_settings(e):
        settings_dialog.open = False
        page.update()

    settings_dialog = ft.AlertDialog(
        title=ft.Text("Settings"),
        content=api_key_section,
        actions=[ft.TextButton("Close", on_click=close_settings)],
    )

    settings_btn = ft.IconButton(ft.Icons.SETTINGS, tooltip="Settings", on_click=open_settings)

    # Shared controls
    log_field = ft.TextField(
        multiline=True, read_only=True, min_lines=3, max_lines=3,
        expand=True, text_size=11, border_color=ft.Colors.OUTLINE,
    )
    active_jobs_list = ft.ListView(spacing=5, height=200)
    history_list = ft.ListView(expand=True, spacing=5)

    # Video preview
    preview_player_container = ft.Container(expand=True)
    preview_container = ft.Container(
        content=ft.Column([
            ft.Text("Preview", size=16, weight=ft.FontWeight.BOLD),
            ft.Text("No video yet", size=14, italic=True, color=ft.Colors.ON_SURFACE),
        ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, alignment=ft.MainAxisAlignment.CENTER),
        bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
        border_radius=10,
        padding=10,
        expand=True,
    )

    current_preview_path = [None]

    def load_preview(video_path_or_url):
        current_preview_path[0] = video_path_or_url
        player = ftv.Video(
            playlist=[ftv.VideoMedia(video_path_or_url)],
            autoplay=True,
            show_controls=True,
            aspect_ratio=16 / 9,
            expand=True,
        )
        preview_container.content = ft.Column([
            ft.Text("Preview", size=16, weight=ft.FontWeight.BOLD),
            ft.Container(content=player, expand=True),
            ft.Button(
                content="Fullscreen",
                icon=ft.Icons.FULLSCREEN,
                on_click=lambda e: open_file(current_preview_path[0]),
            ),
        ], expand=True, horizontal_alignment=ft.CrossAxisAlignment.CENTER)
        page.update()

    def log(msg):
        log_field.value = (log_field.value or "") + msg + "\n"
        page.update()

    # --- Persistent history ---
    history_file = os.path.join(os.path.dirname(__file__), "history.json")

    def save_history(entries):
        with open(history_file, "w") as f:
            json.dump(entries, f, indent=2)

    def load_history():
        if os.path.exists(history_file):
            try:
                with open(history_file, "r") as f:
                    return json.load(f)
            except Exception:
                return []
        return []

    history_data = load_history()  # list of {mode, prompt, path, url, timestamp}

    def build_history_row(entry):
        m, p, path, url = entry["mode"], entry["prompt"], entry.get("path"), entry.get("url")

        def play_in_preview(e, u=url, lp=path):
            src = lp if lp and os.path.exists(lp) else u
            if src:
                load_preview(src)

        return ft.Container(
            content=ft.Column([
                ft.Text(f"[{m}] {p[:50]}...", size=11, weight=ft.FontWeight.BOLD),
                ft.Row([
                    ft.TextButton("Play", icon=ft.Icons.PLAY_CIRCLE, on_click=play_in_preview),
                    ft.TextButton("Open", on_click=lambda e, lp=path: open_file(lp) if lp else None) if path else ft.Container(),
                    ft.TextButton("Copy URL", on_click=lambda e, u=url: page.set_clipboard(u)) if url else ft.Container(),
                ], spacing=0),
            ], spacing=2),
            bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST, border_radius=8, padding=8,
        )

    def add_to_history(mode, prompt, path, url):
        entry = {"mode": mode, "prompt": prompt, "path": path, "url": url, "timestamp": time.time()}
        history_data.insert(0, entry)
        save_history(history_data)
        history_list.controls.insert(0, build_history_row(entry))
        page.update()

    # --- Job queue UI ---
    def build_job_row(job):
        """Build a UI row for a job in the active jobs list."""
        ring = ft.ProgressRing(width=16, height=16, visible=job["status"] in ("pending", "processing", "submitting"))
        status_icon = ft.Icon(ft.Icons.CHECK_CIRCLE, color=ft.Colors.GREEN, size=16, visible=job["status"] == "completed")
        fail_icon = ft.Icon(ft.Icons.ERROR, color=ft.Colors.RED, size=16, visible=job["status"] == "failed")

        return ft.Container(
            key=job["id"],
            content=ft.Row([
                ring,
                status_icon,
                fail_icon,
                ft.Text(f"[{job['mode']}]", size=11, weight=ft.FontWeight.BOLD),
                ft.Text(job["prompt"][:40] + "..." if len(job["prompt"]) > 40 else job["prompt"], size=11, expand=True),
                ft.Text(job["status"], size=11, italic=True),
                ft.Text(f"{job['elapsed']}s" if job["elapsed"] > 0 else "", size=11),
            ], spacing=5),
            bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
            border_radius=6,
            padding=ft.Padding.symmetric(horizontal=8, vertical=4),
        )

    def refresh_jobs_ui():
        """Rebuild the active jobs list from the jobs array."""
        active_jobs_list.controls = [build_job_row(j) for j in jobs]
        page.update()

    # --- Shared parameter builders ---
    def make_aspect_ratio():
        return ft.Dropdown(
            label="Aspect Ratio", width=140, value="16:9", filled=True,
            options=[ft.dropdown.Option(r) for r in ["16:9", "9:16", "1:1", "4:3", "3:4"]],
        )

    def make_duration():
        return ft.Dropdown(
            label="Duration (s)", width=120, value="5", filled=True,
            options=[ft.dropdown.Option(str(d)) for d in range(4, 16)],
        )

    def make_quality():
        return ft.Dropdown(
            label="Quality", width=120, value="basic", filled=True,
            options=[ft.dropdown.Option(q) for q in ["basic", "high"]],
        )

    def make_prompt(hint="Describe the video..."):
        return ft.TextField(
            label="Prompt", multiline=True, min_lines=3, max_lines=4,
            expand=True, hint_text=hint,
        )

    # --- Custom file picker with thumbnail previews ---
    _IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}
    _VIDEO_EXTS = {".mp4", ".mkv", ".avi", ".mov", ".webm"}
    _AUDIO_EXTS = {".mp3", ".wav", ".ogg", ".flac", ".aac"}

    def _open_media_picker(title, extensions, on_done, multi=True):
        """Open a custom file picker dialog with thumbnail grid previews."""
        log_debug(f"_open_media_picker: title={title}, extensions={extensions}, multi={multi}")
        current_dir = [os.path.expanduser("~")]
        selected = []

        grid = ft.GridView(max_extent=180, spacing=8, run_spacing=8, expand=True, padding=10)
        dir_field = ft.TextField(value=current_dir[0], expand=True, text_size=13, dense=True,
                                 on_submit=lambda e: _nav(dir_field.value))
        sel_label = ft.Text("0 selected", size=13, italic=True)

        def _is_match(name):
            return os.path.splitext(name)[1].lower() in extensions

        # --- Large preview panel (right side of dialog) ---
        preview_img = ft.Image(src="", width=320, height=320, fit=ft.BoxFit.CONTAIN, border_radius=8)
        preview_panel = ft.Container(
            content=ft.Column([
                ft.Icon(ft.Icons.TOUCH_APP, size=48, color=ft.Colors.ON_SURFACE_VARIANT),
                ft.Text("Click a file to preview", size=13, italic=True, color=ft.Colors.ON_SURFACE_VARIANT),
            ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, alignment=ft.MainAxisAlignment.CENTER, expand=True),
            width=340, bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
            border_radius=10, padding=10,
            alignment=ft.Alignment(0, 0),
        )

        def _show_preview(path):
            log_debug(f"_show_preview: {path}")
            ext = os.path.splitext(path)[1].lower()
            name = os.path.basename(path)
            try:
                size_mb = os.path.getsize(path) / (1024 * 1024)
            except OSError:
                size_mb = 0

            if ext in _IMAGE_EXTS:
                preview_img.src = path
                preview_panel.content = ft.Column([
                    preview_img,
                    ft.Text(name, size=13, weight=ft.FontWeight.BOLD, text_align=ft.TextAlign.CENTER, width=320,
                            max_lines=2, overflow=ft.TextOverflow.ELLIPSIS),
                    ft.Text(f"{size_mb:.1f} MB", size=11, italic=True, color=ft.Colors.ON_SURFACE_VARIANT),
                ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, alignment=ft.MainAxisAlignment.CENTER, spacing=6)
            elif ext in _VIDEO_EXTS:
                preview_panel.content = ft.Column([
                    ft.Icon(ft.Icons.MOVIE, size=80, color=ft.Colors.LIGHT_BLUE),
                    ft.Text(name, size=13, weight=ft.FontWeight.BOLD, text_align=ft.TextAlign.CENTER, width=320,
                            max_lines=2, overflow=ft.TextOverflow.ELLIPSIS),
                    ft.Text(f"{size_mb:.1f} MB", size=11, italic=True, color=ft.Colors.ON_SURFACE_VARIANT),
                ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, alignment=ft.MainAxisAlignment.CENTER, spacing=6, expand=True)
            elif ext in _AUDIO_EXTS:
                preview_panel.content = ft.Column([
                    ft.Icon(ft.Icons.GRAPHIC_EQ, size=80, color=ft.Colors.PURPLE),
                    ft.Text(name, size=13, weight=ft.FontWeight.BOLD, text_align=ft.TextAlign.CENTER, width=320,
                            max_lines=2, overflow=ft.TextOverflow.ELLIPSIS),
                    ft.Text(f"{size_mb:.1f} MB", size=11, italic=True, color=ft.Colors.ON_SURFACE_VARIANT),
                ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, alignment=ft.MainAxisAlignment.CENTER, spacing=6, expand=True)

        def _toggle(path):
            log_debug(f"_toggle: {path}, currently selected: {len(selected)}")
            if multi:
                if path in selected:
                    selected.remove(path)
                else:
                    selected.append(path)
            else:
                selected.clear()
                selected.append(path)
            sel_label.value = f"{len(selected)} selected"
            _show_preview(path)
            _refresh()

        def _nav(path):
            log_debug(f"_nav: {path}")
            path = os.path.expanduser(path)
            if os.path.isdir(path):
                current_dir[0] = path
                dir_field.value = path
                selected.clear()
                sel_label.value = "0 selected"
                _refresh()

        def _make_tile(content_col, is_sel, on_click_fn):
            return ft.Container(
                content=ft.Stack([
                    content_col,
                    ft.Container(
                        content=ft.Icon(ft.Icons.CHECK_CIRCLE, color=ft.Colors.PRIMARY, size=22),
                        alignment=ft.Alignment(1, -1),
                        visible=is_sel,
                        ignore_interactions=True,
                    ),
                ]),
                width=170, height=170,
                bgcolor=ft.Colors.SURFACE_CONTAINER,
                border=ft.Border.all(3, ft.Colors.PRIMARY) if is_sel else ft.Border.all(1, ft.Colors.with_opacity(0.2, ft.Colors.OUTLINE)),
                border_radius=10,
                padding=6,
                on_click=on_click_fn,
            )

        def _refresh():
            log_debug(f"_refresh: dir={current_dir[0]}")
            grid.controls.clear()
            d = current_dir[0]

            # Parent directory tile
            parent = os.path.dirname(d)
            if parent != d:
                grid.controls.append(
                    _make_tile(
                        ft.Column([
                            ft.Icon(ft.Icons.DRIVE_FOLDER_UPLOAD, size=48, color=ft.Colors.ON_SURFACE_VARIANT),
                            ft.Text("..", size=12, text_align=ft.TextAlign.CENTER, weight=ft.FontWeight.BOLD),
                        ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, alignment=ft.MainAxisAlignment.CENTER),
                        False,
                        lambda e, p=parent: _nav(p),
                    )
                )

            try:
                entries = sorted(os.listdir(d), key=lambda x: (not os.path.isdir(os.path.join(d, x)), x.lower()))
            except PermissionError:
                page.update()
                return

            for name in entries:
                if name.startswith("."):
                    continue
                full = os.path.join(d, name)

                if os.path.isdir(full):
                    grid.controls.append(
                        _make_tile(
                            ft.Column([
                                ft.Icon(ft.Icons.FOLDER, size=48, color=ft.Colors.AMBER),
                                ft.Text(name, size=11, text_align=ft.TextAlign.CENTER, max_lines=2,
                                        overflow=ft.TextOverflow.ELLIPSIS, width=150),
                            ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, alignment=ft.MainAxisAlignment.CENTER),
                            False,
                            lambda e, p=full: _nav(p),
                        )
                    )
                elif _is_match(name):
                    is_sel = full in selected
                    ext = os.path.splitext(name)[1].lower()

                    # Build the thumbnail based on file type
                    if ext in _IMAGE_EXTS:
                        thumb = ft.Image(src=full, width=150, height=115, fit=ft.BoxFit.COVER, border_radius=6)
                    elif ext in _VIDEO_EXTS:
                        thumb = ft.Container(
                            content=ft.Column([
                                ft.Icon(ft.Icons.MOVIE, size=44, color=ft.Colors.LIGHT_BLUE),
                                ft.Text("VIDEO", size=9, color=ft.Colors.ON_SURFACE_VARIANT, weight=ft.FontWeight.BOLD),
                            ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, alignment=ft.MainAxisAlignment.CENTER, spacing=2),
                            width=150, height=115, alignment=ft.Alignment(0, 0),
                            bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST, border_radius=6,
                        )
                    elif ext in _AUDIO_EXTS:
                        thumb = ft.Container(
                            content=ft.Column([
                                ft.Icon(ft.Icons.GRAPHIC_EQ, size=44, color=ft.Colors.PURPLE),
                                ft.Text("AUDIO", size=9, color=ft.Colors.ON_SURFACE_VARIANT, weight=ft.FontWeight.BOLD),
                            ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, alignment=ft.MainAxisAlignment.CENTER, spacing=2),
                            width=150, height=115, alignment=ft.Alignment(0, 0),
                            bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST, border_radius=6,
                        )
                    else:
                        thumb = ft.Container(
                            content=ft.Icon(ft.Icons.INSERT_DRIVE_FILE, size=44),
                            width=150, height=115, alignment=ft.Alignment(0, 0),
                        )

                    grid.controls.append(
                        _make_tile(
                            ft.Column([
                                thumb,
                                ft.Text(name, size=10, text_align=ft.TextAlign.CENTER, max_lines=1,
                                        overflow=ft.TextOverflow.ELLIPSIS, width=150),
                            ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=4),
                            is_sel,
                            lambda e, p=full: _toggle(p),
                        )
                    )
            page.update()

        def _on_confirm(e):
            log_debug(f"_on_confirm: {len(selected)} files selected: {selected}")
            page.pop_dialog()
            if selected:
                on_done(list(selected))

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Row([
                ft.Icon(ft.Icons.PERM_MEDIA, size=24),
                ft.Text(title, size=18, weight=ft.FontWeight.BOLD),
            ], spacing=8),
            content=ft.Container(
                content=ft.Column([
                    ft.Row([
                        ft.IconButton(ft.Icons.HOME, on_click=lambda e: _nav(os.path.expanduser("~")),
                                      tooltip="Home"),
                        ft.IconButton(ft.Icons.DESKTOP_WINDOWS,
                                      on_click=lambda e: _nav(os.path.expanduser("~/Desktop")),
                                      tooltip="Desktop"),
                        ft.IconButton(ft.Icons.DOWNLOAD,
                                      on_click=lambda e: _nav(os.path.expanduser("~/Downloads")),
                                      tooltip="Downloads"),
                        dir_field,
                    ], spacing=2),
                    ft.Divider(height=1),
                    ft.Row([
                        ft.Container(content=grid, expand=True),
                        ft.VerticalDivider(width=1),
                        preview_panel,
                    ], expand=True, spacing=0),
                    ft.Divider(height=1),
                    ft.Row([
                        sel_label,
                        ft.Container(expand=True),
                        ft.TextButton("Cancel", on_click=lambda e: page.pop_dialog()),
                        ft.FilledButton("Select", icon=ft.Icons.CHECK, on_click=_on_confirm),
                    ]),
                ], spacing=8, expand=True),
                width=1100,
                height=650,
            ),
        )

        _refresh()
        page.show_dialog(dlg)

    # --- Generation logic ---
    def run_generation(mode, api_call, prompt_text):
        log_info(f"run_generation: mode={mode}, prompt={prompt_text[:80]!r}")
        if not api:
            log("ERROR: API key not set. Put your key in .env")
            return

        job = {
            "id": uuid.uuid4().hex[:8],
            "mode": mode,
            "prompt": prompt_text,
            "status": "submitting",
            "elapsed": 0,
            "request_id": None,
        }
        jobs.append(job)
        refresh_jobs_ui()
        log(f"[{mode}] Job {job['id']}: {prompt_text[:60]}...")

        start = time.time()

        def worker():
            import traceback
            try:
                log_debug(f"[{job['id']}] Submitting API call...")
                result = api_call()
                log_debug(f"[{job['id']}] API response: {result}")
                job["request_id"] = result.get("request_id")
                job["status"] = "pending"
                log(f"[{job['id']}] Request ID: {job['request_id']}")
                log_info(f"[{job['id']}] Got request_id: {job['request_id']}")
                refresh_jobs_ui()

                while True:
                    log_debug(f"[{job['id']}] Polling...")
                    poll = api.get_result(job["request_id"])
                    s = poll.get("status", "unknown")
                    log_debug(f"[{job['id']}] Poll status: {s}")
                    job["status"] = s
                    job["elapsed"] = int(time.time() - start)
                    refresh_jobs_ui()

                    if s == "completed":
                        log_info(f"[{job['id']}] COMPLETED! Full response: {poll}")
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
                            filename = f"seedance_{job['request_id']}.mp4"
                            local_path = os.path.join(save_dir, filename)
                            log_debug(f"[{job['id']}] Downloading to {local_path}...")
                            log(f"[{job['id']}] Downloading...")
                            r = requests.get(video_url, stream=True)
                            with open(local_path, "wb") as f:
                                for chunk in r.iter_content(chunk_size=8192):
                                    f.write(chunk)
                            log_debug(f"[{job['id']}] Download done")

                        job["elapsed"] = int(time.time() - start)
                        job["status"] = "completed"
                        log(f"[{job['id']}] Done in {job['elapsed']}s")
                        add_to_history(mode, prompt_text, local_path, video_url)
                        refresh_jobs_ui()

                        preview_src = local_path if local_path and os.path.exists(local_path) else video_url
                        if preview_src:
                            load_preview(preview_src)
                        break

                    elif s == "failed":
                        log_error(f"[{job['id']}] FAILED! Full response: {poll}")
                        job["status"] = "failed"
                        error_msg = poll.get('error') or poll.get('message') or str(poll)
                        log(f"[{job['id']}] FAILED: {error_msg}")
                        refresh_jobs_ui()
                        break

                    time.sleep(5)

            except Exception as ex:
                tb = traceback.format_exc()
                log_error(f"[{job['id']}] EXCEPTION:\n{tb}")
                job["status"] = "failed"
                job["elapsed"] = int(time.time() - start)
                log(f"[{job['id']}] ERROR: {ex}\n{tb}")
                refresh_jobs_ui()

        page.run_thread(worker)

    # ==================== TAB 1: Text to Video ====================
    t2v_prompt = make_prompt("A cinematic shot of a futuristic city...")
    t2v_aspect = make_aspect_ratio()
    t2v_duration = make_duration()
    t2v_quality = make_quality()

    def t2v_generate(e):
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
        ], spacing=8),
        padding=15, data="t2v", alignment=ft.Alignment(0, -1),
    )

    # ==================== TAB 2: Image to Video ====================
    i2v_prompt = make_prompt("Animate this image with gentle motion...")
    i2v_aspect = make_aspect_ratio()
    i2v_duration = make_duration()
    i2v_quality = make_quality()
    i2v_images = ft.TextField(label="Image URLs or paths (one per line)", multiline=True, min_lines=2, max_lines=3, expand=True)
    i2v_picked = ft.Text("", size=11)

    def pick_images(e):
        def on_done(paths):
            existing = i2v_images.value.strip()
            i2v_images.value = (existing + "\n" if existing else "") + "\n".join(paths)
            i2v_picked.value = f"{len(paths)} file(s) added"
            page.update()
        _open_media_picker("Select Images", _IMAGE_EXTS, on_done)

    def i2v_generate(e):
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
        ], spacing=8),
        padding=15, data="i2v", alignment=ft.Alignment(0, -1),
    )

    # ==================== TAB 3: Omni Reference ====================
    omni_prompt = make_prompt("Use @image1, @video1, @audio1 to reference assets...")
    omni_aspect = make_aspect_ratio()
    omni_duration = make_duration()
    omni_4k = ft.Checkbox(label="Upscale to 4K", value=False)
    omni_images = ft.TextField(label="Image URLs or paths (up to 9, one per line)", multiline=True, min_lines=2, max_lines=3, expand=True)
    omni_videos = ft.TextField(label="Video URLs or paths (up to 3, one per line)", multiline=True, min_lines=1, max_lines=2, expand=True)
    omni_audios = ft.TextField(label="Audio URLs or paths (up to 3, one per line)", multiline=True, min_lines=1, max_lines=2, expand=True)
    omni_img_picked = ft.Text("", size=11)
    omni_vid_picked = ft.Text("", size=11)
    omni_aud_picked = ft.Text("", size=11)

    # --- Autocomplete for @references in prompt ---
    _ac_visible = [False]
    _ac_options = []       # list of (token, display_label)
    _ac_sel = [0]
    _ac_enter = [False]

    _ac_listview = ft.ListView(spacing=0)
    _ac_popup = ft.Container(
        content=_ac_listview,
        bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
        border=ft.Border.all(1, ft.Colors.OUTLINE),
        border_radius=8,
        padding=4,
        visible=False,
    )

    def _ac_get_refs():
        """Build available @references from loaded assets."""
        refs = []
        for i, line in enumerate([l.strip() for l in (omni_images.value or "").split("\n") if l.strip()][:9], 1):
            name = os.path.basename(line) if "/" in line or os.sep in line else (line[:35] + "\u2026" if len(line) > 35 else line)
            refs.append((f"@image{i}", f"@image{i}  \u2014  {name}"))
        for i, line in enumerate([l.strip() for l in (omni_videos.value or "").split("\n") if l.strip()][:3], 1):
            name = os.path.basename(line) if "/" in line or os.sep in line else (line[:35] + "\u2026" if len(line) > 35 else line)
            refs.append((f"@video{i}", f"@video{i}  \u2014  {name}"))
        for i, line in enumerate([l.strip() for l in (omni_audios.value or "").split("\n") if l.strip()][:3], 1):
            name = os.path.basename(line) if "/" in line or os.sep in line else (line[:35] + "\u2026" if len(line) > 35 else line)
            refs.append((f"@audio{i}", f"@audio{i}  \u2014  {name}"))
        return refs

    def _ac_find_token(text):
        """Find the @token being typed at the end of text."""
        if not text:
            return None, -1
        i = len(text) - 1
        while i >= 0 and text[i] not in (" ", "\n", "\t"):
            i -= 1
        word = text[i + 1:]
        if word.startswith("@"):
            return word, i + 1
        return None, -1

    def _ac_rebuild():
        """Rebuild the autocomplete popup list."""
        _ac_listview.controls.clear()
        for i, (token, label) in enumerate(_ac_options):
            selected = i == _ac_sel[0]
            _ac_listview.controls.append(ft.Container(
                content=ft.Text(label, size=13),
                bgcolor=ft.Colors.PRIMARY_CONTAINER if selected else ft.Colors.SURFACE_CONTAINER_HIGHEST,
                padding=ft.Padding.symmetric(horizontal=10, vertical=6),
                border_radius=4,
                on_click=lambda e, t=token: _ac_select(t),
                ink=True,
            ))

    def _ac_select(token):
        """Insert the selected autocomplete token into the prompt."""
        text = omni_prompt.value or ""
        partial, pos = _ac_find_token(text)
        if partial is not None and pos >= 0:
            omni_prompt.value = text[:pos] + token + " "
        _ac_visible[0] = False
        _ac_popup.visible = False
        page.update()
        omni_prompt.focus()

    def _ac_on_prompt_change(e):
        log_debug(f"_ac_on_prompt_change: visible={_ac_visible[0]}, enter_flag={_ac_enter[0]}")
        # Handle enter-to-select: the Enter key added a newline, undo it and insert token
        if _ac_enter[0]:
            _ac_enter[0] = False
            if _ac_options:
                token = _ac_options[_ac_sel[0]][0]
                text = omni_prompt.value or ""
                if text.endswith("\n"):
                    text = text[:-1]
                partial, pos = _ac_find_token(text)
                if partial is not None and pos >= 0:
                    omni_prompt.value = text[:pos] + token + " "
                else:
                    omni_prompt.value = text
                _ac_visible[0] = False
                _ac_popup.visible = False
                page.update()
                return

        text = omni_prompt.value or ""
        partial, pos = _ac_find_token(text)
        if partial is not None:
            all_refs = _ac_get_refs()
            filtered = [(t, l) for t, l in all_refs if t.lower().startswith(partial.lower())]
            if filtered:
                _ac_options.clear()
                _ac_options.extend(filtered)
                _ac_sel[0] = 0
                _ac_rebuild()
                _ac_visible[0] = True
                _ac_popup.visible = True
                page.update()
                return
        if _ac_visible[0]:
            _ac_visible[0] = False
            _ac_popup.visible = False
            page.update()

    omni_prompt.on_change = _ac_on_prompt_change

    def _ac_on_keyboard(e: ft.KeyboardEvent):
        if not _ac_visible[0]:
            return
        if e.key == "Arrow Down":
            _ac_sel[0] = min(_ac_sel[0] + 1, len(_ac_options) - 1)
            _ac_rebuild()
            page.update()
        elif e.key == "Arrow Up":
            _ac_sel[0] = max(_ac_sel[0] - 1, 0)
            _ac_rebuild()
            page.update()
        elif e.key == "Enter":
            _ac_enter[0] = True
        elif e.key == "Escape":
            _ac_visible[0] = False
            _ac_popup.visible = False
            page.update()

    page.on_keyboard_event = _ac_on_keyboard

    # --- File pickers ---
    def pick_omni_images(e):
        def on_done(paths):
            existing = omni_images.value.strip()
            omni_images.value = (existing + "\n" if existing else "") + "\n".join(paths)
            omni_img_picked.value = f"{len(paths)} image(s) added"
            page.update()
        _open_media_picker("Select Images", _IMAGE_EXTS, on_done)

    def pick_omni_videos(e):
        def on_done(paths):
            existing = omni_videos.value.strip()
            omni_videos.value = (existing + "\n" if existing else "") + "\n".join(paths)
            omni_vid_picked.value = f"{len(paths)} video(s) added"
            page.update()
        _open_media_picker("Select Videos", _VIDEO_EXTS, on_done)

    def pick_omni_audios(e):
        def on_done(paths):
            existing = omni_audios.value.strip()
            omni_audios.value = (existing + "\n" if existing else "") + "\n".join(paths)
            omni_aud_picked.value = f"{len(paths)} audio file(s) added"
            page.update()
        _open_media_picker("Select Audio Files", _AUDIO_EXTS, on_done)

    def omni_generate(e):
        imgs = [line.strip() for line in (omni_images.value or "").split("\n") if line.strip()]
        vids = [line.strip() for line in (omni_videos.value or "").split("\n") if line.strip()]
        auds = [line.strip() for line in (omni_audios.value or "").split("\n") if line.strip()]
        if not imgs and not vids and not auds:
            log("ERROR: Add at least one image, video, or audio reference")
            return
        run_generation("Omni", lambda: api.omni_reference(
            prompt=omni_prompt.value or "",
            images=imgs if imgs else None,
            video_urls=vids if vids else None,
            audio_urls=auds if auds else None,
            aspect_ratio=omni_aspect.value,
            duration=int(omni_duration.value),
            upscale_4k=omni_4k.value,
        ), omni_prompt.value or "")

    omni_tab = ft.Container(
        content=ft.Column([
            omni_prompt,
            ft.Row([
                omni_images,
                ft.Column([
                    ft.Button(content="Browse images...", icon=ft.Icons.IMAGE, on_click=pick_omni_images),
                    omni_img_picked,
                ]),
            ], spacing=10),
            ft.Row([
                omni_videos,
                ft.Column([
                    ft.Button(content="Browse videos...", icon=ft.Icons.VIDEO_FILE, on_click=pick_omni_videos),
                    omni_vid_picked,
                ]),
            ], spacing=10),
            ft.Row([
                omni_audios,
                ft.Column([
                    ft.Button(content="Browse audio...", icon=ft.Icons.AUDIO_FILE, on_click=pick_omni_audios),
                    omni_aud_picked,
                ]),
            ], spacing=10),
            ft.Row([omni_aspect, omni_duration, omni_4k]),
            ft.Button(content="Generate Video", icon=ft.Icons.PLAY_ARROW, on_click=omni_generate),
        ], spacing=8),
        padding=15, data="omni", alignment=ft.Alignment(0, -1),
    )

    # ==================== TAB 4: Video Edit ====================
    ve_prompt = make_prompt("Edit this video to add slow motion...")
    ve_aspect = make_aspect_ratio()
    ve_quality = make_quality()
    ve_videos = ft.TextField(label="Video URLs or paths (one per line)", multiline=True, min_lines=2, max_lines=3, expand=True)
    ve_images = ft.TextField(label="Optional image URLs/paths (one per line)", multiline=True, min_lines=1, max_lines=2, expand=True)
    ve_watermark = ft.Checkbox(label="Remove watermark", value=False)
    ve_picked = ft.Text("", size=11)

    def pick_videos(e):
        def on_done(paths):
            existing = ve_videos.value.strip()
            ve_videos.value = (existing + "\n" if existing else "") + "\n".join(paths)
            ve_picked.value = f"{len(paths)} video(s) added"
            page.update()
        _open_media_picker("Select Videos", _VIDEO_EXTS, on_done)

    def ve_generate(e):
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
        ], spacing=8),
        padding=15, data="ve", alignment=ft.Alignment(0, -1),
    )

    # ==================== TAB 4: Extend Video ====================
    ext_request_id = ft.TextField(label="Request ID (from previous generation)", expand=True)
    ext_prompt = make_prompt("Continue the scene with...")
    ext_duration = make_duration()
    ext_quality = make_quality()

    def ext_generate(e):
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
        ], spacing=8),
        padding=15, data="ext", alignment=ft.Alignment(0, -1),
    )

    # Minimum heights per tab to show all controls without scrolling
    _tab_min_heights = {
        0: 700,    # T2V: prompt + options + button
        1: 780,    # I2V: prompt + images + options + button
        2: 1050,   # Omni: prompt + images + videos + audio + options + button
        3: 830,    # Video Edit: prompt + videos + images + options + button
        4: 700,    # Extend: request id + prompt + options + button
    }

    def on_tab_change(e):
        idx = int(e.data) if e.data is not None else 0
        needed = _tab_min_heights.get(idx, 700)
        page.window.min_height = needed
        if page.window.height < needed:
            page.window.height = needed
        page.update()

    # ==================== Main Layout ====================
    tabs = ft.Tabs(
        selected_index=0,
        length=5,
        expand=True,
        on_change=on_tab_change,
        content=ft.Column(
            expand=True,
            controls=[
                ft.TabBar(
                    tabs=[
                        ft.Tab(label="Text to Video", icon=ft.Icons.TEXT_FIELDS),
                        ft.Tab(label="Image to Video", icon=ft.Icons.IMAGE),
                        ft.Tab(label="Omni Reference", icon=ft.Icons.AUTO_AWESOME),
                        ft.Tab(label="Video Edit", icon=ft.Icons.EDIT),
                        ft.Tab(label="Extend Video", icon=ft.Icons.FAST_FORWARD),
                    ],
                ),
                ft.TabBarView(
                    expand=True,
                    controls=[t2v_tab, i2v_tab, omni_tab, ve_tab, ext_tab],
                ),
            ],
        ),
    )

    # Left side: tabs only
    left_panel = ft.Column([
        tabs,
    ], expand=2)

    # Right side: preview + active jobs + history
    right_panel = ft.Column([
        preview_container,
        ft.Divider(),
        ft.Text("Active Jobs", size=14, weight=ft.FontWeight.BOLD),
        active_jobs_list,
        ft.Divider(),
        ft.Text("History", size=14, weight=ft.FontWeight.BOLD),
        history_list,
    ], expand=1, width=400)

    page.overlay.append(settings_dialog)
    page.add(
        ft.Stack([
            ft.Container(
                content=ft.Image(src=os.path.join(os.path.dirname(os.path.abspath(__file__)), "logo.png"), height=60),
                alignment=ft.Alignment(0, 0),
                expand=True,
                padding=ft.Padding(top=15, bottom=15, left=0, right=0),
            ),
            ft.Container(
                content=settings_btn,
                alignment=ft.Alignment(1, 0),
                expand=True,
            ),
        ], height=90),
        ft.Divider(),
        ft.Row([left_panel, ft.VerticalDivider(), right_panel], expand=True),
        ft.Divider(),
        ft.Container(
            content=ft.Row([
                ft.Text("Log", size=11, weight=ft.FontWeight.BOLD),
                ft.Container(content=log_field, expand=True),
            ], vertical_alignment=ft.CrossAxisAlignment.START, spacing=10),
            height=80,
        ),
    )

    # Init API
    try:
        api = SeedanceAPI()
        log("API initialized successfully")
        log_info("API initialized OK")
    except Exception as ex:
        log(f"API init failed: {ex}")
        log("Make sure .env contains MUAPI_API_KEY=your_key")
        log_error(f"API init failed: {ex}")

    # Load persistent history
    for entry in history_data:
        history_list.controls.append(build_history_row(entry))
    if history_data:
        log(f"Loaded {len(history_data)} items from history")
    log_info(f"UI ready. {len(history_data)} history items loaded.")
    page.update()


ft.run(main)
