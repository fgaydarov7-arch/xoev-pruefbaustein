import os
import xml.etree.ElementTree as ET
import json
import re

# Настройки путей к твоим папкам
XSD_DIR = r"..\shemas\xauslaender\schemata"
XML_DIR = r"..\shemas\xauslaender\codeliste"
OUTPUT_JSON = r"..\rules\xauslaender_core1.json" # или куда тебе удобнее в проекте

# Пространства имен для парсинга XML / XSD
XSD_NS = {'xs': 'http://www.w3.org/2001/XMLSchema'}
GC_NS = {'gc': 'http://docs.oasis-open.org/codelist/ns/genericode/1.0/'}

def parse_codelists(xml_dir):
    """
    Сканирует все .xml коделисты и собирает словарь:
    { 'имя_справочника_или_код': [список_валидных_значений] }
    """
    codelists_db = {}
    if not os.path.exists(xml_dir):
        print(f"⚠️ Папка с коделистами не найдена: {xml_dir}")
        return codelists_db

    print("📦 Парсинг коделист (Genericode XML)...")
    for file_name in os.listdir(xml_dir):
        if not file_name.endswith('.xml'):
            continue
            
        file_path = os.path.join(xml_dir, file_name)
        try:
            tree = ET.parse(file_path)
            root = tree.getroot()
            
            # Пытаемся определить уникальное техническое имя коделиста (из ShortName или Identification)
            short_name_elem = root.find('.//ShortName')
            if short_name_elem is not None and short_name_elem.text:
                codelist_key = short_name_elem.text.strip()
            else:
                codelist_key = os.path.splitext(file_name)[0]

            codes = []
            # Ищем все строки данных <Row>
            for row in root.findall('.//Row', GC_NS) or root.findall('.//Row'):
                # В немецких коделистах XÖV целевой код обычно лежит в колонке 'code' или 'Schluessel'
                for value in row.findall('Value'):
                    col_ref = value.attrib.get('ColumnRef')
                    if col_ref in ['code', 'Schluessel', 'Wert']:
                        val_elem = value.find('SimpleValue')
                        if val_elem is not None and val_elem.text:
                            codes.append(val_elem.text.strip())
            
            # Если по техническому ключу ничего не нашли, берем первую попавшуюся текстовую колонку
            if not codes:
                for row in root.findall('.//Row'):
                    val_elem = row.find('.//SimpleValue')
                    if val_elem is not None and val_elem.text:
                        codes.append(val_elem.text.strip())

            if codes:
                codelists_db[codelist_key.lower()] = sorted(list(set(codes)))
                # Также сохраняем по имени файла для гибкости связывания
                file_key = os.path.splitext(file_name)[0].lower()
                codelists_db[file_key] = sorted(list(set(codes)))

        except Exception as e:
            print(f"❌ Ошибка при чтении коделиста {file_name}: {e}")
            
    print(f"✅ Успешно загружено справочников: {len(codelists_db)}")
    return codelists_db

def parse_schemata(xsd_dir, codelists_db):
    """
    Сканирует XSD файлы, находит элементы (поля), их типы,
    обязательность и пытается связать их со справочниками.
    """
    fields = []
    if not os.path.exists(xsd_dir):
        print(f"⚠️ Папка со схемами не найдена: {xsd_dir}")
        return fields

    print("📐 Анализ XSD схем (Структура полей)...")
    
    # Для отслеживания дубликатов полей в рамках одного итогового JSON
    seen_fields = set()

    for file_name in os.listdir(xsd_dir):
        if not file_name.endswith('.xsd'):
            continue
            
        file_path = os.path.join(xsd_dir, file_name)
        try:
            tree = ET.parse(file_path)
            root = tree.getroot()
            
            # Ищем все объявления элементов <xs:element>
            for elem in root.findall('.//xs:element', XSD_NS) or root.findall('.//element'):
                name = elem.attrib.get('name')
                if not name:
                    continue
                
                # Игнорируем технические корневые контейнеры сообщений Nachricht, оставляем только поля данных
                if name.startswith('nachricht.') or name in seen_fields:
                    continue

                # Определение обязательности поля
                min_occurs = elem.attrib.get('minOccurs', '1') # По умолчанию в XSD элемент обязателен
                required = True if min_occurs != '0' else False
                
                # Базовый тип данных
                xsd_type = elem.attrib.get('type', 'string')
                clean_type = xsd_type.split(':')[-1] if ':' in xsd_type else xsd_type
                
                field_obj = {
                    "name": name,
                    "required": required,
                    "type": "string" if "string" in clean_type.lower() else "number" if "int" in clean_type.lower() else "string"
                }

                # Умный поиск подходящего справочника (коделиста) по имени поля
                # Например, если поле называется "geschlecht" или "staatsangehoerigkeit"
                matched_list = None
                name_lower = name.lower()
                
                for key in codelists_db.keys():
                    # Если имя поля совпадает с именем справочника или содержит его в себе
                    if key in name_lower or name_lower in key:
                        matched_list = codelists_db[key]
                        break
                
                if matched_list:
                    field_obj["codelist"] = matched_list
                    field_obj["fix_suggestion"] = f"Der Wert muss einem gültigen Code aus der XÖV-Codeliste für '{name}' entsprechen."
                
                # Добавляем регулярные выражения для специфичных типов (например, даты)
                if "date" in clean_type.lower():
                    field_obj["regex"] = r"^\d{4}-\d{2}-\d{2}$"
                    field_obj["fix_suggestion"] = "Format muss JJJJ-MM-TT sein (z.B. 1990-05-25)."

                fields.append(field_obj)
                seen_fields.add(name)

        except Exception as e:
            print(f"❌ Ошибка при анализе схемы {file_name}: {e}")

    return fields

def main():
    # 1. Сначала парсим все справочники, чтобы знать разрешенные значения
    codelists_db = parse_codelists(XML_DIR)
    
    # 2. Затем парсим схемы, формируя список полей, и встраиваем туда справочники
    fields = parse_schemata(XSD_DIR, codelists_db)
    
    if not fields:
        print("🔴 Не удалось извлечь ни одного поля. Проверьте правильность путей и структуру файлов.")
        return

    # 3. Собираем финальный каркас JSON-конфига
    config_json = {
        "schema_id": "xauslaender_full",
        "schema_name": "XAusländer Vollprüfung (Automatisch generiert)",
        "version": "26.11.0",
        "xoev_standard": "XAusländer",
        "description": "Vollständiges Validierungsprofil generiert aus offiziellen XSD-Schemata und XML-Codelisten.",
        "fields": fields
    }

    # Создаем целевую папку, если её нет
    os.makedirs(os.path.dirname(OUTPUT_JSON), exist_ok=True)
    
    # 4. Записываем результат
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(config_json, f, ensure_ascii=False, indent=2)
        
    print(f"\n🎉 ПРАЗДНИК! Огромный JSON правил успешно создан!")
    print(f"📍 Путь: {OUTPUT_JSON}")
    print(f"📊 Всего сгенерировано валидируемых полей: {len(fields)}")

if __name__ == "__main__":
    main()