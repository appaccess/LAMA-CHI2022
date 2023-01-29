import configparser
import json
import os
import re
import subprocess
import time
import uuid
from typing import Dict, List, Optional, Union


def send_keycode_event(device: str, keycode: Union[int, str]) -> None:
    subprocess.call([f"adb -s {device} shell input keyevent {keycode}"], shell=True)


def send_touch_event(device: str, x: int, y: int) -> None:
    subprocess.call([f"adb -s {device} shell input tap {x} {y}"], shell=True)


def send_text_event(device: str, text: str) -> None:
    text = text.replace(" ", "%s")
    subprocess.call([f'adb -s {device} shell input text "{text}"'], shell=True)
    send_keycode_event(device, "KEYCODE_ENTER")


def clear_text_field(device: str) -> None:
    send_keycode_event(device, "KEYCODE_MOVE_END")
    subprocess.call(
        [
            f'adb -s {device} shell input keyevent --longpress \
                        $(printf "KEYCODE_DEL %.0s" {{1..250}});'
        ],
        shell=True,
    )


def press_accessibility_button(device: str) -> None:
    dir_path = os.path.dirname(os.path.realpath(__file__))
    with open(os.path.join(dir_path, "access_button.json"), "r") as f:
        data = json.load(f)
    x, y = data[device]["x"], data[device]["y"]
    send_touch_event(device, x, y)


def sync_accesspull_service(config: configparser.ConfigParser, device: str) -> None:
    required_accesspull_version = config["crawl"]["accesspull_version"]
    try:
        version = get_app_version_name(device, "com.android.accesspull")
    except Exception:
        version = "NOT INSTALLED"
    if required_accesspull_version not in version:
        subprocess.call(
            [f"adb -s {device} install accesspull_v{required_accesspull_version}.apk"], shell=True,
        )


def enable_accesspull_service(device: str) -> None:
    subprocess.call(
        [
            f"adb -s {device} shell settings put secure enabled_accessibility_services \
                    com.android.accesspull/com.android.accesspull.AccessPullService"
        ],
        shell=True,
    )


def get_app_version_name(device: str, app: str) -> str:
    proc = subprocess.Popen(
        [f"adb -s {device} shell dumpsys package {app} | grep versionName"],
        stdout=subprocess.PIPE,
        stderr=None,
        shell=True,
    )
    stdout, _ = proc.communicate()
    versions = stdout.decode("utf-8").split("\n")
    version = versions[0].strip().split("=")[1]
    version = version.replace(" ", "")
    version = version.replace("version", "")
    version = version.replace("/", ".")
    version = re.sub(r"\([^)]*\)", "", version)
    return version


def get_app_version_code(device: str, app: str) -> str:
    proc = subprocess.Popen(
        [f"adb -s {device} shell dumpsys package {app} | grep versionCode"],
        stdout=subprocess.PIPE,
        stderr=None,
        shell=True,
    )
    stdout, _ = proc.communicate()
    vers = stdout.decode("utf-8").split("\n")
    vers = [ver for ver in vers if "=" in ver]
    vcodes = [ver.strip().split(" ")[0].split("=")[1] for ver in vers]
    latest_vcode = sorted(vcodes, reverse=True)[0]
    return latest_vcode


def get_requested_perms_of_installed_app(device: str, app: str) -> List[str]:
    proc = subprocess.Popen(
        [f"adb -s {device} shell dumpsys package {app} | grep permission"],
        stdout=subprocess.PIPE,
        stderr=None,
        shell=True,
    )
    stdout, _ = proc.communicate()
    lines = stdout.decode("ascii").split("\n")
    lines = [p.strip() for p in lines]
    try:
        start = lines.index("requested permissions:")
        end = lines.index("install permissions:")
        permissions = lines[start + 1 : end]
        permissions = [p.split(":")[0] for p in permissions]
    except ValueError:
        permissions = []
    return permissions


def get_requested_perms_from_apk(apk_path: str) -> List[str]:
    proc = subprocess.Popen(
        [f"aapt d permissions {apk_path}"], stdout=subprocess.PIPE, stderr=None, shell=True
    )
    stdout, _ = proc.communicate()
    perm_list = stdout.decode("ascii").split("\n")
    req_perms = [p for p in perm_list if "uses-permission" in p]
    perm_names = [re.search(r"name=\'(\S*)\'", p) for p in req_perms]
    permissions = [p.group(1) for p in perm_names if p]
    return permissions


def enable_permission(device: str, app: str, permission: str) -> str:
    banned_permissions = ["android.permission.MODIFY_AUDIO_SETTINGS"]
    if permission in banned_permissions:
        return "BANNED"
    proc = subprocess.Popen(
        [f"adb -s {device} shell pm grant {app} {permission}"],
        stdout=None,
        stderr=subprocess.PIPE,
        shell=True,
    )
    _, stderr = proc.communicate()
    err_msg = stderr.decode("utf-8").split("\n")[0]
    return "FAILED" if "Security exception" in err_msg else "GRANTED"


def reset_app_permissions(device: str, app: str, permission: Optional[str] = None) -> None:
    if permission:
        subprocess.run(
            [f"adb -s {device} shell pm revoke {app} {permission}"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.STDOUT,
            shell=True,
        )
    else:
        subprocess.run(
            [f"adb -s {device} shell pm reset-permissions -p {app}"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.STDOUT,
            shell=True,
        )


def get_connected_devices() -> List[str]:
    proc = subprocess.Popen(["adb devices"], stdout=subprocess.PIPE, stderr=None, shell=True)
    stdout, _ = proc.communicate()
    stdout_msg = stdout.decode("utf-8").split("\n")
    stdout_msg = stdout_msg[1:]  # Remove header text 'List of devices attached'
    devices = [s.split("\t")[0] for s in stdout_msg if "device" in s]
    return devices


def unlock_device(device: str) -> None:
    while True:
        screen_state = subprocess.check_output(
            [f'adb -s {device} shell dumpsys nfc | grep "mScreenState="'], shell=True
        ).decode("utf-8")
        if "OFF" in screen_state:
            subprocess.call([f"adb -s {device} shell input keyevent 26"], shell=True)
            subprocess.call([f"adb -s {device} shell input keyevent 82"], shell=True)
        if "ON_LOCKED" in screen_state:
            subprocess.call([f"adb -s {device} shell input keyevent 82"], shell=True)
        else:
            break


def reboot_device(device: str) -> None:
    subprocess.call([f"adb -s {device} reboot"], shell=True)


def mute_device(device: str) -> None:
    send_keycode_event(device, 164)


def is_app_installed(device: str, app: str) -> bool:
    is_installed = subprocess.check_output(
        ["adb", "-s", device, "shell", "pm", "list", "packages", app]
    ).decode("utf-8")
    return is_installed != ""


def uninstall_app(device: str, app: str) -> None:
    if is_app_installed(device, app):
        subprocess.call([f"adb -s {device} uninstall {app}"], stdout=subprocess.DEVNULL, shell=True)


def start_app(device: str, app: str) -> None:
    subprocess.call(
        [f"adb -s {device} shell monkey -p {app} 1"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
        shell=True,
    )


def stop_app(device: str, app: str) -> None:
    subprocess.call([f"adb -s {device} shell am force-stop {app}"], shell=True)


def take_screenshot(device: str, savedir: str, filename: Optional[str] = None) -> None:
    if not filename:
        filename = uuid.uuid4().hex
    saveto = os.path.join(savedir, filename) + ".png"
    subprocess.call([f"adb -s {device} exec-out screencap -p > {saveto}"], shell=True)


def pull_file_from_device(device: str, filepath: str, saveto: str) -> None:
    subprocess.run(
        [f"adb -s {device} pull {filepath} {saveto}"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
        shell=True,
    )


def remove_file_on_device(device: str, filepath: str) -> None:
    subprocess.run(
        [f"adb -s {device} shell rm -f {filepath}"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
        shell=True,
    )


def download_hierarchy(device: str, savedir: str, filename: Optional[str] = None) -> bool:
    ondevice_file_path = "/sdcard/Android/data/com.android.accesspull/files/files/view.json"
    if not filename:
        filename = uuid.uuid4().hex
    saveto = os.path.join(savedir, filename) + ".json"

    failed_count = 0
    while True:
        press_accessibility_button(device)
        time.sleep(0.5)
        try:
            pull_file_from_device(device, ondevice_file_path, saveto)
            remove_file_on_device(device, ondevice_file_path)
            if os.stat(saveto).st_size > 0:
                return True

            failed_count += 1
            if failed_count > 10:
                return False
        except FileNotFoundError:
            failed_count += 1
            if failed_count > 10:
                return False


def pull_state_info(config: configparser.ConfigParser, device: str, app: str) -> Optional[str]:
    screen_uuid = uuid.uuid4().hex
    savedir = os.path.join(config["crawl"]["views_path"], app)
    view_success = download_hierarchy(device, savedir, screen_uuid)
    if not view_success:
        return None

    savedir = os.path.join(config["crawl"]["screenshots_path"], app)
    take_screenshot(device, savedir, screen_uuid)
    return screen_uuid


def get_device_dims(device: str) -> Optional[Dict[str, int]]:
    out = (
        subprocess.run([f"adb -s {device} shell wm size"], shell=True, stdout=subprocess.PIPE)
        .stdout.decode("utf-8")
        .strip()
    )
    dims = re.search(r"(\d*)x(\d*)", out)
    if not dims:
        return None
    return {"width": int(dims.group(1)), "height": int(dims.group(2))}


def get_devstrings(apk_path: str) -> List[str]:
    proc = subprocess.Popen(
        [
            f"aapt dump --values resources {apk_path} | grep '^ *resource.*:string/' --after-context=1"
        ],
        stdout=subprocess.PIPE,
        stderr=None,
        shell=True,
    )
    stdout, _ = proc.communicate()

    strings = []
    for raw_string in stdout.decode().split("\n"):
        match = re.search(r"\"(\S*)\"", raw_string)
        if match:
            strings.append(match.group(1))
    return strings


def pull_apk_from_device(
    device: str, app: str, savedir: str, verbose: Optional[bool] = False
) -> None:
    os.makedirs(savedir, exist_ok=True)

    # get absolute path to apk on the device
    proc = subprocess.Popen(
        [f'adb -s {device} shell pm path "{app}"'],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        shell=True,
    )
    stdout, _ = proc.communicate()
    packages = []
    for pkg in stdout.decode().split("\n"):
        match = re.search(r"package:(\S*)", pkg)
        if match:
            packages.append(match.group(1))
    apk_path = ""
    for package in packages:
        if "base" in package:
            apk_path = package
    if not apk_path:
        apk_path = packages[0]

    version_code = get_app_version_code(device, app)
    apk_filename = os.path.join(savedir, f"{app}__{version_code}.apk")
    if os.path.exists(apk_filename):
        if verbose:
            print(f"{apk_filename} already exists.")
    else:
        subprocess.Popen(
            [f"adb -s {device} pull '{apk_path}' {apk_filename}"],
            shell=True,
            stdout=subprocess.PIPE,
        )
        if verbose:
            print(f"Fetched {apk_path} to {apk_filename}")


def open_playstore_install_page(device: str, app: str) -> None:
    subprocess.call(
        [
            f"adb -s {device} shell am start -a android.intent.action.VIEW -d market://details?id={app}"
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        shell=True,
    )


def rotate_to_orientation(device: str, mode: Optional[str] = "portrait") -> None:
    subprocess.call(
        [
            f"adb -s {device} shell content insert --uri content://settings/system --bind name:s:accelerometer_rotation --bind value:i:0"
        ],
        shell=True,
    )
    if mode == "portrait":
        subprocess.call(
            [
                f"adb -s {device} shell content insert --uri content://settings/system --bind name:s:user_rotation --bind value:i:0"
            ],
            shell=True,
        )
    elif mode == "landscape":
        subprocess.call(
            [
                f"adb -s {device} shell content insert --uri content://settings/system --bind name:s:user_rotation --bind value:i:1"
            ],
            shell=True,
        )
    else:
        raise Exception(f"Invalid orientation: {mode}")


def get_apps_installed(device: str) -> List[str]:
    # Returns all "user-installed" apps
    proc = subprocess.Popen(
        [f"adb -s {device} shell pm list packages -3'|cut -f 2 -d ':"],
        stdout=subprocess.PIPE,
        stderr=None,
        shell=True,
    )
    stdout, _ = proc.communicate()
    lines = stdout.decode("ascii").split("\n")
    lines = [p.strip() for p in lines]
    apps = [line for line in lines if line != ""]
    return apps
