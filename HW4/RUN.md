# Порядок запуска HW4

Команды для PowerShell, выполняются из корня `HW4`, если не сказано иное. RustFS и данные в бакете `hh-lake` берутся из HW3 (`docker compose up -d` и `python src\upload.py` в папке HW3).

## Установка

```
pip install -r requirements.txt
```

1. Java 17: распаковать JDK 17 в `jdk\`.
2. ZooKeeper 3.9.6 (apache-zookeeper-3.9.6-bin.tar.gz): распаковать в три папки `zk\server1`, `zk\server2`, `zk\server3`.
3. Настройка серверов: `python src\setup_zookeeper.py` кладёт конфигурации из `zookeeper\` в `conf\zoo.cfg`
   каждой копии и создаёт `data\myid`.
4. В каждом окне PowerShell, где запускается ZooKeeper, нужен `JAVA_HOME`: `$env:JAVA_HOME = "<путь к HW4>\jdk"`.

## Этапы 1-2: ансамбль

Каждый сервер запускается в **своём окне** PowerShell из **своей папки** (путь `dataDir=./data` относительный, и при запуске
из другой папки серверы пересекутся по данным). Сервер работает в этом окне и пишет в него журнал, остановка: закрыть окно.

```
cd zk\server1
.\bin\zkServer.cmd                         # то же в двух других окнах для server2 и server3
```

В отдельном окне, из корня `HW4`:

```
python src\zk_status.py                    # роль каждого сервера (leader / follower), нужна команда srvr из конфигурации
.\zk\server1\bin\zkCli.cmd -server localhost:2181,localhost:2182,localhost:2183 create /alive-check ok
.\zk\server1\bin\zkCli.cmd -server localhost:2181,localhost:2182,localhost:2183 ls /
```

Эфемерный узел: в двух окнах `zkCli.cmd`. В первом `create -e /ephemeral-demo hello` и держать окно открытым;
во втором `ls /` (узел есть). В первом `quit`, во втором снова `ls /` (узла нет).

## Этапы 3-4: координаторы

```
python src\run_failover.py --scenario without-fencing         # пауза лидера без защиты, logs\without-fencing\
$env:FENCING = "1"; python src\run_failover.py --scenario with-fencing   # то же с защитой по эпохе, logs\with-fencing\
python src\check_results.py                                   # указатель на результат и сравнение с HW3
```

Координатор можно запустить и вручную в двух окнах: `python src\coordinator.py --name A` и `--name B`.
Паузу лидера вручную можно сделать так же, как это делает сценарий: `psutil.Process(pid).suspend()` и `.resume()`.

## Структура

```
HW4/
├── README.md, RUN.md, requirements.txt
├── zookeeper\    конфигурации трёх серверов (server1-3.cfg)
├── src\          настройка серверов, координатор, расчёт пар, сценарий с паузой лидера, проверка результатов
├── logs\         журналы: ensemble\ (выводы команд), without-fencing\, with-fencing\
├── report\       отчёт (report.pdf) и картинки к отчёту
├── zk\           три копии ZooKeeper (не в git)
└── jdk\          JDK 17 (не в git)
```
