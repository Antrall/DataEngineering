# Порядок запуска HW5

Команды для PowerShell, выполняются из корня `HW5`, если не сказано иное. Данные и S3 берутся из HW3.

## Подготовка

```
pip install -r requirements.txt
$env:PYTHONPATH = (Resolve-Path ..\..).Path
python src\make_kind_config.py
kind create cluster --config kind-config.yaml
kubectl get nodes -o custom-columns=NAME:.metadata.name,CPU_CAP:.status.capacity.cpu,CPU_ALLOC:.status.allocatable.cpu
docker build -f docker\Dockerfile -t hw5-pairs:1 .
python src\kind_load.py hw5-pairs:1 rustfs/rustfs:latest busybox:1.36
```

## Этапы

```
python src\stage1_memory.py
python src\stage2_parallel.py
python src\stage3_cpu_wait.py
python src\stage4_preemption.py
python src\stage5_quota.py
python src\verify_top10.py k8s/result-h4 http://localhost:19000
python src\make_charts.py
```

Манифесты Kubernetes лежат в `manifests\` (в них есть подстановки `${...}`, сценарии этапов подставляют значения сами).

## Структура

```
HW5/
├── README.md, RUN.md, requirements.txt, kind-config.yaml
├── docker\       Dockerfile образа с программой расчёта
├── manifests\    манифесты Kubernetes
├── src\          программа расчёта, сценарии этапов, вспомогательные модули
├── logs\         журналы запусков по этапам
├── results\      итоговый топ-10 и все пары, эталон из HW3
└── report\       отчёт и скриншоты
```
