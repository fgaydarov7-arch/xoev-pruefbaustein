import os
import json
import zipfile
import xml.etree.ElementTree as ET

# 🛠️ АВТООПРЕДЕЛЕНИЕ ПУТЕЙ (базируется на расположении скрипта)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")
IMPORT_ZONE = os.path.join(BASE_DIR, "..", "xrepository", "import_zone")
XOEV_REGISTRY = os.path.join(BASE_DIR, "..", "xrepository", "xoev-registry")

def init_catalog(catalog_path):
    """Инициализирует валидный XML-каталог по стандарту OASIS, если его нет"""
    if not os.path.exists(catalog_path):
        os.makedirs(os.path.dirname(catalog_path), exist_ok=True)
        # Стандартный корневой элемент каталога OASIS
        root = ET.Element("catalog", xmlns="urn:oasis:names:tc:entity:xmlns:xml:catalog")
        tree = ET.ElementTree(root)
        tree.write(catalog_path, encoding="utf-8", xml_declaration=True)
        print(f"  ✓ Создан новый глобальный catalog.xml")

def update_catalog(catalog_path, target_ns, rewrite_prefix):
    """Безопасно добавляет или обновляет правило rewriteSystem в catalog.xml"""
    ET.register_namespace('', "urn:oasis:names:tc:entity:xmlns:xml:catalog")
    tree = ET.parse(catalog_path)
    root = tree.getroot()
    
    ns = {"cat": "urn:oasis:names:tc:entity:xmlns:xml:catalog"}
    exists = False
    
    # Проверяем, нет ли уже правила для этого namespace
    for item in root.findall("cat:rewriteSystem", ns):
        if item.get("systemIdStartString") == target_ns:
            item.set("rewritePrefix", rewrite_prefix)
            exists = True
            break
            
    if not exists:
        new_entry = ET.SubElement(root, "rewriteSystem")
        new_entry.set("systemIdStartString", target_ns)
        new_entry.set("rewritePrefix", rewrite_prefix)
        
    tree.write(catalog_path, encoding="utf-8", xml_declaration=True)
    print(f"  ✓ OASIS Catalog: {target_ns} ➔ {rewrite_prefix}")

def extract_zip(zip_path, target_dir):
    """Безопасно распаковывает ZIP-архив в целевую папку"""
    if not os.path.exists(zip_path):
        return False
    
    os.makedirs(target_dir, exist_ok=True)
    print(f"  --> Распаковка {os.path.basename(zip_path)} в {target_dir}")
    
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        zip_ref.extractall(target_dir)
    return True

def main():
    if not os.path.exists(CONFIG_FILE):
        print(f"[ОШИБКА] Конфигурационный файл {CONFIG_FILE} не найден!")
        return

    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
        config = json.load(f)

    catalog_path = os.path.join(XOEV_REGISTRY, "catalog.xml")
    init_catalog(catalog_path)

    has_changes = False

    for pkg in config["packages"]:
        # Обрабатываем ТОЛЬКО те пакеты, которые успешно скачались (status: downloaded)
        if pkg.get("status") != "downloaded":
            if pkg.get("status") == "deployed":
                print(f"⏩ [ПРОПУСК] {pkg['standard']} v{pkg['version']} уже развернут.")
            continue
            
        print(f"\n[DEPLOY] Развертывание пакета {pkg['standard']} версии {pkg['version']}")
        
        # 1. Пути к сырью в import_zone
        package_import_dir = os.path.join(IMPORT_ZONE, pkg["domain_path"], pkg["version"])
        xsd_zip = os.path.join(package_import_dir, "schemata.zip")
        cl_zip = os.path.join(package_import_dir, "codelisten.zip")
        
        # 2. Пути к чистовой зоне в xoev-registry
        package_registry_dir = os.path.join(XOEV_REGISTRY, pkg["domain_path"], pkg["version"])
        xsd_target_dir = os.path.join(package_registry_dir, "xsd")
        cl_target_dir = os.path.join(package_registry_dir, "codelisten")
        
        try:
            # Распаковываем схемы
            extracted_xsd = extract_zip(xsd_zip, xsd_target_dir)
            
            # Распаковываем коделисты (если архив существует)
            extracted_cl = extract_zip(cl_zip, cl_target_dir)
            
            if extracted_xsd:
                # 3. Привязываем относительный путь для catalog.xml
                # Важно: пути в каталоге всегда идут через прямой слэш (/) независимо от OS
                relative_prefix = f"{pkg['domain_path']}/{pkg['version']}/xsd/"
                update_catalog(catalog_path, pkg["target_namespace"], relative_prefix)
                
                # Обновляем статус на финальный
                pkg["status"] = "deployed"
                has_changes = True
                print(f"✓ {pkg['standard']} успешно развернут в реестр!")
            else:
                print(f"  ❌ Ошибка: Не найден корневой архив схем для {pkg['standard']}")
                pkg["status"] = "failed_deploy"
                has_changes = True
                
        except Exception as e:
            print(f"  ❌ КРИТИЧЕСКАЯ ОШИБКА деплоя для {pkg['standard']}: {e}")
            pkg["status"] = "failed_deploy"
            has_changes = True

    # Сохраняем обновленные статусы ("deployed") в config.json
    if has_changes:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        print("\n💾 Финальные статусы развертывания сохранены в config.json!")

    print("\n[FINISH] Фаза Deploy завершена.")

if __name__ == "__main__":
    main()