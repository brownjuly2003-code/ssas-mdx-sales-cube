# Протокол 21.11.2026: куб в SSAS Multidimensional на раннере GitHub windows-2022

Уровень доказательства — **целевой софт**: SQL Server 2022 Developer и Analysis Services в режиме Multidimensional. Куб создан из `cube/create.xmla`, обработан `cube/process.xmla` (ProcessFull), 10 запросов MDX исполнены службой SSAS, ответы совпали с ожидаемыми. Запуск один, с первой попытки. Сводная Excel на кубе не подключалась.

## Где и что исполнено

| Что | Значение |
|---|---|
| Репозиторий | публичный https://github.com/brownjuly2003-code/ssas-mdx-sales-cube, один снимок `ed9510d` без истории; его дерево `c8b956f` — то же, что у локального коммита `fb8fd01` |
| Запуск | workflow `SSAS on Windows` ([ssas-windows.yml](../../.github/workflows/ssas-windows.yml)), `workflow_dispatch`, https://github.com/brownjuly2003-code/ssas-mdx-sales-cube/actions/runs/44905240710 — success |
| Время | 12:42:30–12:49:10 UTC, 6 мин 40 с на весь запуск |
| Раннер | GitHub-hosted, образ `windows-2022` версии 20261116.370.1; Windows Server 2022 Datacenter (сборка 20348), Python 3.11.9, pytest 8.4.2 |
| Database Engine | Microsoft SQL Server 2022 (RTM) 16.0.1000.6 (X64), Developer Edition (64-bit), без накопительных обновлений |
| Analysis Services | Microsoft SQL Server Analysis Services 16.0.42.209, редакция Developer64, ServerMode Multidimensional (AMO), `DeploymentMode` 0 в msmdsrv.ini |
| Клиенты | модуль PowerShell SqlServer 22.4.5.1 (предустановлен в образе), AMO 19.96.1.0 из этого модуля, sqlcmd 16.0.1000.6 (ODBC 170) |
| Дистрибутив | `SQLServer2022-x64-ENU-Dev.iso` с download.microsoft.com, 1 163 053 056 байт, SHA-256 `80D2CD75DD2B28098C0182F50AD86BD44F9B3A9F357C30FF617480A1497DAFFD` (совпал с закреплённым) |

Тексты запросов `mdx/*.mdx` исполнены в SSAS **без правок**: `Compare-Cube.ps1` берёт файл целиком, экранирует его для XML и отправляет в `<Statement>` запроса XMLA Execute. Две правки для Mondrian (снятый `;`, флаг `TYPED` в запросе 09) здесь не делались. SSAS принял и завершающий `;`, и `Properties("KEY0", TYPED)`.

## Шаги и длительности

По меткам времени журнала задачи ([job-windows.log](2026-11-21-ssas-windows/job-windows.log)).

| Шаг | Время | Итог |
|---|---|---|
| 1. Seed и эталон | 61 с (из них pip) | `reports/expected.json` равен `docs/runs/expected-seed64.json` |
| 2a. Скачивание ISO и SHA-256 | 15 с | хеш совпал |
| 2b. Установка SQLENGINE и AS | 4 мин 26 с (setup.exe — 4,3 мин) | код выхода 0; маркеров ожидающей перезагрузки нет |
| 3a. Модуль SqlServer | 2 с | 22.4.5.1, устанавливать не понадобилось |
| 3b. Службы, версии, режим | 14 с | обе службы Running; режим Multidimensional |
| 4. Загрузка звезды `sql/load.sql` | 1 с | числа ниже |
| 5. Право чтения для службы SSAS | 1 с | `NT Service\MSSQLServerOLAPService` — db_datareader в P64SalesDW |
| 6. AMO: Deserialize и Validate (Developer) | 1 с | `P64SalesCube: 3 dimensions, 1 measure group, 2 measures` |
| 7. Create и ProcessFull через `Invoke-ASCmd -InputFile` | 11 с (ProcessFull — 3,2 с) | в обоих ответах нет Exception и Error, предупреждений нет |
| 8. Состояние куба | 1 с | всё Processed, секция MOLAP, члены совпали |
| 9. 10 запросов MDX (`Compare-Cube.ps1`) | 2 с | 10/10 |
| 10. Негативные проверки | 1 с | 23 passed за 0,35 с |
| 11–12. Сводка и выгрузка артефакта | 2 с | артефакт `ssas-windows-evidence` |

## Звезда в SQL Server

| DimDate | DimProduct | DimCustomer | FactSales | SUM(Units) | SUM(Revenue) |
|---:|---:|---:|---:|---:|---:|
| 731 | 6 | 4 | 1 838 | 8 422 | 870 055 |

Все шесть чисел совпали с записью seed 64 ([протокол SQL Server](2026-11-18-mssql.md), [эталон](expected-seed64.json)).

## Create, ProcessFull и состояние куба

Ответы сервера на Create и ProcessFull — пустой `<root>` без ошибок ([create](2026-11-21-ssas-windows/create-response.xml), [process](2026-11-21-ssas-windows/process-response.xml)). Источник куба подключился к SQL Server от имени службы SSAS (ImpersonateServiceAccount); право ему дал `sql/grant_ssas.sql`.

Проверки AMO после обработки ([cube-state.txt](2026-11-21-ssas-windows/cube-state.txt)):

- база P64SalesCube, три измерения, куб Sales и секция SalesLines — State Processed, LastProcessed 21.11.2026 12:49:00 UTC (измерения — 12:48:59);
- куб и секция — StorageMode Molap; секция одна, EstimatedSize 7 358 байт; EstimatedSize базы — 273 602;
- `DISCOVER_PARTITION_STAT` вернул `AGGREGATION_SIZE=1774` ([XML](2026-11-21-ssas-windows/cube-state/partition-stat-SalesLines.xml)); дизайн агрегаций в модели не задан, число приведено как есть;
- запрос MDX `Count(<уровень>.Members)` к кубу: `[Date].[Calendar].[Day]` — 731, `[Product].[Catalog].[Product]` — 6, `[Customer].[Geography].[Customer]` — 4. Это ровно число строк измерений в SQL Server.

## 10 запросов MDX: ожидаемое и ответ SSAS

[compare.txt](2026-11-21-ssas-windows/compare.txt), ответы сервера — [answers/](2026-11-21-ssas-windows/answers). Сравнивал код `sales_cube.cellset` (подписи, порядок, значения) и отдельно `python -m sales_cube.mondrian report --engine SSAS`.

| Запрос | Ожидаемое = ответ SSAS |
|---|---|
| 01_total | 870 055 |
| 02_units_by_year | 2024 — 4 232, 2025 — 4 190 |
| 03_category | Office 192 840, Tech 218 900 |
| 04_region | East 201 310, West 210 430 |
| 05_months | 12 месяцев 2025: 31 130, 31 595, 28 625, 35 240, 41 575, 35 485, 43 185, 30 020, 26 565, 32 595, 36 900, 38 825 |
| 06_ytd_march | 91 350 |
| 07_prior_march | 42 395 |
| 08_march_change | −13 770 |
| 09_top_products | Screen 152 640, Desk 117 000, Chair 53 370 |
| 10_east_office | Aspen 48 335, Birch 47 650 |

Итог: «10/10 SSAS answers match the reference», «10 MDX cellsets match the reference».

## Негативные проверки на ответах SSAS

`tests/test_mondrian_answers.py` с `P64_ANSWERS`, указывающей на папку ответов SSAS ([negative.txt](2026-11-21-ssas-windows/negative.txt)): 23 passed за 0,35 с. Один тест — совпадение всех 10 ответов, 22 негативных: изменённое значение эталона (10), изменённое значение ответа (10), переставленные подписи запроса 09, пропавший ответ. Имена тестов содержат «mondrian», потому что их цитируют прежние протоколы; здесь они читали ответы SSAS.

## Linux CI на GitHub

Тот же снимок `ed9510d` запустил `ci.yml` (push) на раннерах GitHub `ubuntu-26.04`: https://github.com/brownjuly2003-code/ssas-mdx-sales-cube/actions/runs/44905232067 — success. Задачи `offline` и `mssql` впервые прошли на раннере GitHub, а не только в ci_local ([job-linux-ci.log](2026-11-21-ssas-windows/job-linux-ci.log)):

- `offline`: 59 passed, 31 deselected за 0,70 с; ruff чистый;
- `mssql`: 8 тестов загрузки за 2,49 с; 10/10 ответов Mondrian; 23 проверки ответов Mondrian за 0,04 с.

В журнале есть предупреждения GitHub: Node.js 20 устарел у `actions/checkout@v4`, `actions/setup-python@v5`, `actions/setup-java@v4`. На результат они не повлияли.

## Материалы в репозитории

Папка [2026-11-21-ssas-windows/](2026-11-21-ssas-windows):

- `summary.txt` — сводка шага 11;
- `compare.txt`, `negative.txt`, `cube-state.txt`, `analysis-server.txt`, `amo-validate.txt`;
- `create-response.xml`, `process-response.xml`;
- `cube-state/*.xml` — ответы на счёт членов и `DISCOVER_PARTITION_STAT`;
- `answers/*.xml` — 10 ответов SSAS (в артефакте — папка `actual/20261121-124902`);
- `seed-summary.txt` — сводка генератора;
- `job-windows.log` и `job-linux-ci.log` — журналы обеих задач целиком, как их отдаёт GitHub.

`expected.json` артефакта побайтово равен [expected-seed64.json](expected-seed64.json) и отдельно не сохранён.

Windows PowerShell 5.1 записал `Tee-Object` текстовые файлы в UTF-16, а `summary.txt` — в UTF-8 с BOM. Здесь они перекодированы в UTF-8 без BOM, переводы строк — LF, текст не менялся. Артефакт GitHub хранится 30 дней, поэтому копия лежит здесь. В материалах только пути раннера (`D:\a\…`, `C:\Program Files\…`) и временное имя его учётной записи.

## Чего прогон не доказывает

- Сводная Excel к кубу не подключалась: на раннере нет Excel. Шаг 4 обещания открыт ([шаги на стенде](../MANUAL_STEPS.md), шаг 4).
- Прогон один, на свежей RTM-установке 16.0.1000.6 без накопительных обновлений. Поведение на других сборках не проверялось.
- Данные учебные и синтетические (seed 64, 1 838 строк): скорость обработки и запросов на таком объёме ничего не говорит о реальных нагрузках.
- Раннер GitHub — временная машина, удаляемая после задачи, а не постоянный сервер. Резервное копирование, роли безопасности куба, инкрементальная обработка и эксплуатация не проверялись.
- Дизайн агрегаций не задан; разрешение ничьих в запросе 09 на этих данных не проверяется — ничьих нет.
