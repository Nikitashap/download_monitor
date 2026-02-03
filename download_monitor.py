import os
import re
import sys
import time
import subprocess
from datetime import datetime
from pathlib import Path
import plistlib
import json

def get_steam_path():
    # Поиск пути к Steam
    possible_paths = [
        "~/Library/Application Support/Steam",
        "/Applications/Steam.app/Contents/MacOS",
        "~/Library/Application Support/Steam/Steam.AppBundle/Steam/Contents/MacOS",
    ]
    
    try:
        result = subprocess.run(
            ["mdfind", "kMDItemCFBundleIdentifier == 'com.valvesoftware.steam'"],
            capture_output=True,
            text=True
        )
        if result.stdout:
            for line in result.stdout.strip().split('\n'):
                if line.endswith('.app'):
                    data_path = os.path.expanduser("~/Library/Application Support/Steam")
                    if os.path.isdir(data_path):
                        return data_path
    except:
        pass
    
    # Проверяем стандартные пути
    for path in possible_paths:
        expanded_path = os.path.expanduser(path)
        if os.path.isdir(expanded_path):
            if expanded_path.endswith('.app') or 'Contents/MacOS' in expanded_path:
                data_path = os.path.expanduser("~/Library/Application Support/Steam")
                if os.path.isdir(data_path):
                    return data_path
            return expanded_path
    
    # Ищем через plist LaunchAgents/LaunchDaemons
    plist_paths = [
        "~/Library/LaunchAgents/com.valvesoftware.steam.plist",
        "/Library/LaunchDaemons/com.valvesoftware.steam.plist",
    ]
    
    for plist in plist_paths:
        expanded = os.path.expanduser(plist)
        if os.path.exists(expanded):
            try:
                with open(expanded, 'rb') as f:
                    plist_data = plistlib.load(f)
                    if 'ProgramArguments' in plist_data:
                        for arg in plist_data['ProgramArguments']:
                            if 'steam' in arg.lower() and os.path.isdir(arg):
                                data_path = os.path.expanduser("~/Library/Application Support/Steam")
                                if os.path.isdir(data_path):
                                    return data_path
            except:
                pass
    
    return None

def get_library_folders(steam_path):
    libraries = []
    
    if steam_path and os.path.isdir(steam_path):
        possible_steamapps = [
            os.path.join(steam_path, "steamapps"),
            os.path.join(steam_path, "SteamApps"),  
            steam_path, 
        ]
        
        for path in possible_steamapps:
            if os.path.isdir(path):
                libraries.append(steam_path)
                break
    
    vdf_paths = [
        os.path.join(steam_path, "steamapps", "libraryfolders.vdf"),
        os.path.join(steam_path, "SteamApps", "libraryfolders.vdf"),
        os.path.join(steam_path, "libraryfolders.vdf"),
    ]
    
    for vdf_path in vdf_paths:
        if os.path.isfile(vdf_path):
            try:
                with open(vdf_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                
                path_matches = re.findall(r'"path"\s+"([^"]+)"', content)
                for path in path_matches:
                    if os.path.isdir(path):
                        libraries.append(os.path.normpath(path))
                
                alt_matches = re.findall(r'"\d+"\s+"([^"]+)"', content)
                for path in alt_matches:
                    if os.path.isdir(path) and path not in libraries:
                        libraries.append(os.path.normpath(path))
                        
            except Exception as e:
                print(f"Ошибка чтения libraryfolders.vdf: {e}")
    
    unique_libs = []
    seen = set()
    for lib in libraries:
        if lib not in seen:
            unique_libs.append(lib)
            seen.add(lib)
    
    return unique_libs

def get_game_name(appid, libraries):
    manifest_name = f"appmanifest_{appid}.acf"
    
    for lib in libraries:
        possible_paths = [
            os.path.join(lib, "steamapps", manifest_name),
            os.path.join(lib, "SteamApps", manifest_name),
            os.path.join(lib, manifest_name),
        ]
        
        for manifest_path in possible_paths:
            if os.path.isfile(manifest_path):
                try:
                    with open(manifest_path, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read()
                    
                    name_match = re.search(r'"name"\s+"([^"]+)"', content)
                    if name_match:
                        return name_match.group(1)
                except Exception as e:
                    print(f"Ошибка чтения манифеста {manifest_path}: {e}")
    
    return f"AppID {appid}"

def find_content_log(steam_path):
    possible_paths = [
        os.path.join(steam_path, "logs", "content_log.txt"),
        os.path.join(steam_path, "Logs", "content_log.txt"),
        os.path.join(os.path.dirname(steam_path), "logs", "content_log.txt"),
        os.path.expanduser("~/Library/Application Support/Steam/logs/content_log.txt"),
    ]
    
    for path in possible_paths:
        if os.path.isfile(path):
            return path

    try:
        result = subprocess.run(
            ["find", os.path.expanduser("~"), "-name", "content_log.txt", "-type", "f", 
             "-path", "*Steam*", "2>/dev/null", "|", "head", "-1"],
            shell=True,
            capture_output=True,
            text=True
        )
        if result.stdout.strip():
            return result.stdout.strip()
    except:
        pass
    
    return None

def tail_log_file(filepath, lines=500):
    try:
        with open(filepath, 'rb') as f:
            f.seek(0, 2)
            file_size = f.tell()
            
            buffer_size = 1024 * 64
            data = []
            lines_found = 0
            
            position = file_size
            while position > 0 and lines_found < lines:
                to_read = min(buffer_size, position)
                position -= to_read
                f.seek(position)
                
                chunk = f.read(to_read)
                lines_in_chunk = chunk.count(b'\n')
                lines_found += lines_in_chunk
                
                data.insert(0, chunk.decode('utf-8', errors='ignore'))
            
            full_text = ''.join(data)
            all_lines = full_text.splitlines()
            return all_lines[-lines:]
            
    except Exception as e:
        print(f"Ошибка чтения файла логов: {e}")
        return []

RE_APP_UPDATE = re.compile(
    r'^\[(?P<ts>[\d-]+\s+[\d:]+)\]\s+AppID\s+(?P<appid>\d+)\s+App update changed\s*:\s*(?P<flags>.*)$'
)
RE_STATE = re.compile(
    r'^\[(?P<ts>[\d-]+\s+[\d:]+)\]\s+AppID\s+(?P<appid>\d+)\s+state changed\s*:\s*(?P<flags>.*)$'
)
RE_PROGRESS = re.compile(
    r'^\[(?P<ts>[\d-]+\s+[\d:]+)\]\s+AppID\s+(?P<appid>\d+)\s+update started\s*:\s*download\s+(?P<done>\d+)/(?P<total>\d+)'
)
RE_RATE = re.compile(
    r'^\[(?P<ts>[\d-]+\s+[\d:]+)\]\s+Current download rate:\s+(?P<mbps>[0-9.]+)\s+Mbps'
)
RE_FINISHED = re.compile(
    r'^\[(?P<ts>[\d-]+\s+[\d:]+)\]\s+AppID\s+(?P<appid>\d+)\s+finished update\b'
)
RE_CANCELED = re.compile(
    r'^\[(?P<ts>[\d-]+\s+[\d:]+)\]\s+AppID\s+(?P<appid>\d+)\s+update canceled\s*:\s*(?P<reason>.*)$'
)

def analyze_logs(lines):
    current_appid = None
    latest_timestamp = None
    
    for line in lines:
        match = RE_APP_UPDATE.match(line)
        if match:
            flags = match.group('flags')
            if 'Downloading' in flags or 'Running Update' in flags:
                timestamp = match.group('ts')
                appid = int(match.group('appid'))
                
                if latest_timestamp is None or timestamp > latest_timestamp:
                    latest_timestamp = timestamp
                    current_appid = appid
    
    if not current_appid:
        return None
    
    info = {
        'appid': current_appid,
        'downloaded': None,
        'total': None,
        'rate_mbps': None,
        'status': 'IDLE',
        'timestamp': latest_timestamp
    }
    
    for line in lines:
        match = RE_RATE.match(line)
        if match:
            info['rate_mbps'] = float(match.group('mbps'))
    
        match = RE_PROGRESS.match(line)
        if match and int(match.group('appid')) == current_appid:
            info['downloaded'] = int(match.group('done'))
            info['total'] = int(match.group('total'))
        
        match = RE_APP_UPDATE.match(line)
        if match and int(match.group('appid')) == current_appid:
            flags = match.group('flags').lower()
            if 'downloading' in flags:
                info['status'] = 'DOWNLOADING'
            elif 'running update' in flags:
                info['status'] = 'RUNNING_UPDATE'
            elif any(x in flags for x in ['suspended', 'paused', 'stopping']):
                info['status'] = 'PAUSED'
        
        match = RE_STATE.match(line)
        if match and int(match.group('appid')) == current_appid:
            state = match.group('flags').lower()
            if 'fully installed' in state:
                info['status'] = 'COMPLETED'
            elif 'suspended' in state:
                info['status'] = 'PAUSED'
    
    if info['rate_mbps'] is not None:
        if info['rate_mbps'] > 0 and info['status'] in ['DOWNLOADING', 'RUNNING_UPDATE']:
            info['status'] = 'DOWNLOADING'
        elif info['rate_mbps'] == 0 and info['status'] == 'DOWNLOADING':
            info['status'] = 'PAUSED'
    
    return info

def format_speed(mbps):
    if mbps is None:
        return "unknown"
    
    mb_per_s = mbps / 8.0
    return f"{mb_per_s:.2f} MB/s ({mbps:.2f} Mbps)"

def format_progress(downloaded, total):
    if downloaded is None or total is None or total == 0:
        return "progress: unknown"
    
    percentage = (downloaded / total) * 100
    def format_bytes(bytes_num):
        for unit in ['B', 'KB', 'MB', 'GB']:
            if bytes_num < 1024.0:
                return f"{bytes_num:.1f} {unit}"
            bytes_num /= 1024.0
        return f"{bytes_num:.1f} TB"
    
    return f"{percentage:.1f}% ({format_bytes(downloaded)}/{format_bytes(total)})"

def main():
    print("Steam Download Monitor for macOS")
    print("=" * 50)
    
    # 1. Находим Steam
    print("Поиск Steam ...")
    steam_path = get_steam_path()
    
    if not steam_path:
        print("Ошибка: Не удалось найти Steam на вашем Mac.")
        print("Убедитесь, что Steam установлен и запущен.")
        sys.exit(1)
    
    print(f"Найден Steam: {steam_path}")
    
    # 2. Находим логи
    content_log = find_content_log(steam_path)
    if not content_log:
        print("Ошибка: Не удалось найти файл логов content_log.txt")
        print("Убедитесь, что Steam запущен и начата загрузка.")
        sys.exit(1)
    
    print(f"Файл логов: {content_log}")
    
    # 3. Получаем библиотеки
    libraries = get_library_folders(steam_path)
    if not libraries:
        libraries = [steam_path]
    
    print(f"Найдено библиотек Steam: {len(libraries)}")
    
    # 4. Мониторим 5 минут
    print("\nНачинаем мониторинг загрузок (5 минут)...")
    print("=" * 50)
    
    idle_counter = 0
    last_game_name = None
    
    for minute in range(1, 6):
        current_time = datetime.now().strftime("%H:%M:%S")
        
        # Читаем логи
        lines = tail_log_file(content_log, 1000)
        
        if not lines:
            print(f"[{current_time}] {minute}/5  Не удалось прочитать логи")
            time.sleep(60)
            continue
        
        # Анализируем логи
        download_info = analyze_logs(lines)
        
        if not download_info:
            idle_counter += 1
            print(f"[{current_time}] {minute}/5  Активных загрузок не обнаружено")
            
            if idle_counter >= 2:
                # Если 2 минуты нет активности, выводим сообщение о завершении
                if last_game_name:
                    print(f"[{current_time}] {minute}/5  {last_game_name} | ЗАВЕРШЕНО")
                else:
                    print(f"[{current_time}] {minute}/5  Steam | БЕЗ ДЕЙСТВИЯ")
        else:
            idle_counter = 0
            
            # Получаем имя игры
            game_name = get_game_name(download_info['appid'], libraries)
            last_game_name = game_name
            
            # Форматируем вывод
            speed_str = format_speed(download_info['rate_mbps'])
            
            # Выводим информацию
            print(f"[{current_time}] {minute}/5  {game_name} | {download_info['status']} | {speed_str}")
        
        # Ждем 60 секунд до следующей проверки
        if minute < 5:
            time.sleep(60)
    
    print("\n" + "=" * 50)
    print("Мониторинг завершен. Спасибо за использование!")

if __name__ == "__main__":
    if sys.platform != "darwin":
        print("Ошибка: Этот скрипт предназначен только для macOS!")
        print(f"Текущая система: {sys.platform}")
        sys.exit(1)
    
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nМониторинг прерван пользователем.")
    except Exception as e:
        print(f"\nПроизошла ошибка: {e}")
        print("Попробуйте запустить Steam и начать загрузку игры.")