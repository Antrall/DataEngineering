# Порядок запуска HW3

Все команды выполняются из корня `HW3`.

```
pip install -r requirements.txt
docker compose up -d                       # RustFS: S3 API на :9000, веб-консоль на :9001
python src/gen_data.py --rows 250000       # data/it_vacancies_2024.csv и data/skills_alias.csv
python src/upload.py                       # бакет hh-lake: raw/ (данные) и ref/ (словарь синонимов)
python src/mapreduce.py --inject-fail 3    # MapReduce, маппер чанка 3 падает и перезапускается
python src/duckdb_sql.py                   # тот же расчёт SQL-запросом
python src/verify.py                       # сравнение результатов двух способов
python src/analysis.py > results/analysis_output.md   # этапы 5 и 6
python src/profile.py 3                    # время и пик памяти, 3 запуска (results/profile_results.csv)
python src/export_results.py               # выгрузка результатов из хранилища в results/
python src/make_charts.py                  # графики для отчёта
```

## Структура

```
HW3/
├── docker-compose.yml   RustFS на 4 папках-дисках
├── RUN.md               этот файл
├── requirements.txt     зависимости Python
├── src/                 код
├── report/              отчёт (report.md, report.pdf) и скриншоты
├── results/             результаты расчётов, профилирование, консольные логи (results/logs)
├── data/                сгенерированный датасет (не хранится в git)
└── disks/               «диски» RustFS (не хранятся в git)
```