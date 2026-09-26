import os
import json
import requests

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Теперь конфиг всегда ищется в той же папке, где лежит скрипт
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")

# А папку import_zone поднимаем на уровень выше, в корень xoevpruefbaustein.local/backend/
IMPORT_ZONE = os.path.join(BASE_DIR, "..", "xrepository", "import_zone")

def download_file(url, target_path):
    """Скачивает файл по URL и сохраняет по указанному пути"""
    if not url:
        return False
        
    print(f"  --> Начало загрузки: {url}")
    try:
        # stream=True позволяет скачивать большие архивы чанками, не забивая оперативку
        response = requests.get(url, stream=True, timeout=30)
        if response.status_code == 200:
            with open(target_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=16384):
                    f.write(chunk)
            print(f"  ✓ Файл успешно сохранен: {target_path}")
            return True
        else:
            print(f"  ❌ Ошибка! Сервер вернул код: {response.status_code}")
            return False
    except Exception as e:
        print(f"  ❌ Сетевая ошибка при скачивании: {e}")
        return False

def main():
    if not os.path.exists(CONFIG_FILE):
        print(f"[ОШИБКА] Конфигурационный файл {CONFIG_FILE} не найден!")
        return

    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
        config = json.load(f)

    has_changes = False

    for pkg in config["packages"]:
        # Проверяем статус загрузки. Если downloaded — пропускаем пакет
        if pkg.get("status") == "downloaded":
            print(f"⏩ [ПРОПУСК] {pkg['standard']} v{pkg['version']} уже находится в import_zone.")
            continue
            
        print(f"\n[FETCH] Запуск загрузки для {pkg['standard']} версии {pkg['version']}")
        
        # Динамически собираем путь: xrepository/import_zone/de/osci/xinneres/26.11/
        package_fetch_dir = os.path.join(IMPORT_ZONE, pkg["domain_path"], pkg["version"])
        os.makedirs(package_fetch_dir, exist_ok=True)
        
        # Задаем фиксированные имена для архивов
        xsd_local_path = os.path.join(package_fetch_dir, "schemata.zip")
        cl_local_path = os.path.join(package_fetch_dir, "codelisten.zip")
        
        xsd_success = True
        cl_success = True
        
        # 1. Скачиваем XSD-схемы
        if pkg["xsd_url"]:
            xsd_success = download_file(pkg["xsd_url"], xsd_local_path)
            
        # 2. Скачиваем коделисты (если ссылка на них есть в JSON)
        if pkg["cl_url"]:
            cl_success = download_file(pkg["cl_url"], cl_local_path)
            
        # Если всё, что было задекларировано, скачалось — обновляем статус
        if xsd_success and cl_success:
            pkg["status"] = "downloaded"
            has_changes = True
            print(f"✓ Все ресурсы для {pkg['standard']} успешно доставлены в import_zone.")
        else:
            pkg["status"] = "failed"
            has_changes = True
            print(f"❌ Часть загрузок для {pkg['standard']} завершилась ошибкой.")

    # Если были изменения статусов — перезаписываем конфиг
    if has_changes:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        print("\n💾 Новые статусы загрузок зафиксированы в config.json")

    print("\n[FINISH] Фаза Fetch завершена.")

if __name__ == "__main__":
    main()