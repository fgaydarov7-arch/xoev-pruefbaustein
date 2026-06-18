import pandas as pd
import os

# Путь, куда сохранить тестовый файл
output_path = r".\auslaender_liste.xlsx"

# Создаем папку, если её нет
os.makedirs(os.path.dirname(output_path), exist_ok=True)

# Формируем структуру данных точно по нашему сценарию
data = {
    "Geschlecht": ["männlich", "Frau", "weiblich", ""],
    "Staatsangehoerigkeit": ["DEU", "TUR", "RUSSIA", "SYR"],
    "Geburtsdatum": ["1995-08-12", "1990-11-23", "25.05.1988", "2000-01-01"],
    "AZR_Nummer": ["123456789012", "12345", "987654321098", "111122223333"]
}

# Переводим в DataFrame Pandas
df = pd.DataFrame(data)

# Сохраняем в формат Excel
df.to_excel(output_path, index=False)

print(f"🎉 Тестовый файл успешно создан по пути: {output_path}")
print("Вы можете загружать его в движок для проверки вашего 32k-строчного JSON!")