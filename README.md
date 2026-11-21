# Учебный куб продаж SSAS и запросы MDX

Куб Sales описывает, сколько единиц товара купили клиенты и какова выручка в рублях. Гранулярность факта — одна строка продажи. Измерения позволяют переходить от года к месяцу и дню, от категории к товару, от региона к клиенту. Данные синтетические: продажи за 2024 и 2025 годы, генератор с seed 64.

**Что сделано и чего нет.** В SSAS куб не разворачивался и не обрабатывался. Доказано: звезда загружается в SQL Server 2022 и построчно совпадает с исходными данными; определение куба в XMLA проходит проверку структуры; ожидаемые ответы на 10 запросов посчитаны независимо (pandas и отдельные выборки SQLite) и сходятся между собой; все 10 запросов MDX исполнены движком Mondrian 3.2 поверх той же звезды в SQL Server, и ответы совпали с ожидаемыми. Уровень этого доказательства — заменяющий движок Mondrian 3.2, не SSAS: Mondrian читает тот же язык MDX, но это другой сервер, и два запроса пришлось поправить. Итог одной фразой — в [BRIEF](docs/BRIEF.md).

| Утверждение | Доказательство (исполнено, есть лог) |
|---|---|
| Схема «звезда» загружается в SQL Server 2022 Developer тем же `sqlcmd -i sql/load.sql`, все поля 2 579 строк четырёх таблиц совпадают с исходными (сравнивается текст, напечатанный `sqlcmd`, и отдельно длина пяти текстовых столбцов в байтах), повторная загрузка и загрузка в чужую базу отклоняются | [DDL](sql/star.sql), [загрузчик](sql/load.sql), [тесты](tests/test_mssql.py), [протокол SQL Server](docs/runs/2026-11-18-mssql.md), [прогон 19.11](docs/runs/2026-11-19-audit.md), журнал `logs/j2_6.log` в [архиве прогона](docs/runs/mssql-evidence.zip) |
| Определение куба в XMLA разбирается; логические и физические имена таблиц и столбцов представления источника совпадают с DDL; у трёх измерений естественные иерархии с ожидаемым порядком уровней (год → месяц → день, категория → товар, регион → клиент), каждый уровень связан с родительским; шесть намеренно испорченных копий определения проверка отвергает; гранулярность группы мер — день, товар и клиент, мер две (Units и Revenue), секция читает FactSales | [модель XMLA](cube/create.xmla), тесты `test_model_bindings_and_grain` и `test_damaged_model_is_rejected` в [tests/test_offline.py](tests/test_offline.py), [прогон 19.11](docs/runs/2026-11-19-audit.md) |
| Ожидаемые ответы на 10 запросов (27 строк) посчитаны на pandas и совпадают с отдельными выборками SQLite по экспорту SQL, включая подписи и порядок строк | [эталон pandas](src/sales_cube/reference.py), [выборки SQLite](tests/test_offline.py), [снимок ответов](docs/runs/expected-seed64.json), журналы `logs/j1_4.log` и `logs/j1_7.log` в [архиве прогона](docs/runs/mssql-evidence.zip) |
| Уровень — заменяющий движок Mondrian 3.2, не SSAS. Все 10 запросов MDX исполнены Mondrian 3.2 поверх той же звезды в SQL Server 2022 в CI; ответы — 27 строк, подписи, порядок и значения — совпали с ожидаемыми тем же кодом сравнения, что написан для ответов SSAS (`sales_cube.cellset`); изменённое значение эталона или ответа, переставленные подписи и пропавший ответ сравнение отвергает (22 негативные проверки); схема Mondrian описывает тот же куб, что XMLA, — офлайн-тест сравнивает их и отвергает 10 испорченных копий; все 14 скачанных jar сверены по SHA-256 | [схема Mondrian](cube/mondrian.xml), [исполнитель](mondrian/RunMdx.java), [список jar с SHA-256](mondrian/artifacts.txt), [тесты ответов](tests/test_mondrian_answers.py), [офлайн-тесты](tests/test_mondrian.py), [протокол Mondrian](docs/runs/2026-11-21-mondrian.md) (прогон `ssas-mdx-sales-cube_20261121-063735`) |

Запросы MDX лежат в [mdx/](mdx) в тексте для SSAS. Для Mondrian они не переписаны вручную: две правки делает [sales_cube/mondrian.py](src/sales_cube/mondrian.py) по точному списку, тест проверяет, что остальной текст не меняется.

| Запрос | Что изменено для Mondrian | Почему |
|---|---|---|
| все 10 | снят завершающий `;` | сканер Mondrian 3.2 его не принимает: «Unexpected character ';'» (прогон `ssas-mdx-sales-cube_20261121-062419`); `;` — разделитель команд клиента вроде SSMS, а не часть запроса |
| 09 | `.Properties("KEY0", TYPED)` → `.Properties("KEY0")`; в схеме Mondrian у уровня Product объявлено свойство `KEY0` — столбец `ProductKey`, тип Numeric | в Mondrian 3.2 нет флага `TYPED`: парсер принимает его за имя члена — «MDX object '[TYPED]' not found in cube 'Sales'» (прогон `ssas-mdx-sales-cube_20261121-062821`); встроенного свойства `KEY0` тоже нет. Числовой тип оставляет выражение `Revenue * 1000 - ключ` арифметикой, как в SSAS |

### Без сохранённого вывода

Проверка структуры библиотекой Microsoft AMO (`Microsoft.AnalysisServices` 19.114.8, `Deserialize` и `Database.Validate` для Developer Edition) выполнялась на Windows, но её вывод не сохранён, поэтому доказательством с логом она не служит. Повторить — `.\scripts\Confirm-Model.ps1` в Windows PowerShell с модулем SqlServer или `.\scripts\Confirm-Model.ps1 -AmoDirectory <каталог сборок AMO>`, вывод положить в `docs/runs/`. [Скрипт](scripts/Confirm-Model.ps1) · [офлайн-протокол](docs/runs/2026-11-18-offline.md)

### Предстоит

| Шаг | Состояние |
|---|---|
| Create базы и ProcessFull в SSAS Multidimensional | Скрипты готовы, не запускались: [create.xmla](cube/create.xmla), [process.xmla](cube/process.xmla) |
| Исполнение 10 запросов MDX в SSAS и сравнение ответов сервера с ожидаемыми | Скрипт готов, не запускался: [Compare-Cube.ps1](scripts/Compare-Cube.ps1). Код сравнения проверен на ответах Mondrian (выше), но ответ XMLA от SSAS он ещё не читал |
| Сводная таблица Excel на кубе | Не выполнено, порядок — [шаги на стенде](docs/MANUAL_STEPS.md) |

Первые два шага готов выполнить ручной workflow [ssas-windows.yml](.github/workflows/ssas-windows.yml) на раннере GitHub `windows-2022`. Он ставит SQL Server 2022 Developer с Analysis Services в режиме Multidimensional и загружает звезду. Затем выполняет Create и ProcessFull, проверяет состояние куба, хранение MOLAP и число членов ключевых уровней, исполняет 10 запросов через `Compare-Cube.ps1` и прогоняет негативные проверки на ответах SSAS. Журналы и ответы сервера выгружаются артефактом. Workflow ещё не запускался, результатов у него нет. Запуск:

```bash
gh workflow run ssas-windows.yml
```

Офлайн-тест [test_windows_workflow.py](tests/test_windows_workflow.py) проверяет только структуру файла: запуск вручную, раннер Windows, лимит времени, вызовы скриптов и выгрузку артефакта. PowerShell он не исполняет.

### Офлайн-запуск

Нужен Python 3.11 или новее. Из корня проекта в PowerShell выполнить команды в активном виртуальном окружении.

```powershell
python -m pip install -r requirements.txt
$env:PYTHONPATH = 'src'
python -m sales_cube --output reports
Get-Content -Encoding UTF8 reports/summary.txt
```

Команда воспроизводит один набор с seed 64. В `reports/seed.sql` находятся вставки для загрузки в SQL Server, в `reports/expected.json` — ожидаемые ответы на запросы MDX. Генерация занимает около 2 секунд ([офлайн-протокол](docs/runs/2026-11-18-offline.md)). Тесты гоняются в CI (Linux) командой `python -m pytest -q`.

### Проверка загрузки в SQL Server

Задача CI `mssql` запускает SQL Server 2022 Developer в отдельном контейнере Linux и загружает сгенерированный `reports/seed.sql` той же командой `sqlcmd -i sql/load.sql`, что и на ручном стенде. Тесты читают все поля четырёх таблиц в порядке первичного ключа и сравнивают их с исходными строками. Ещё два сценария проверяют повторную загрузку и выбор другой базы. Команда для чистого стенда после генерации данных и запуска Compose — `python -m pytest -v -m slow tests/test_mssql.py`. [Конфигурация CI](.github/workflows/ci.yml) · [Тесты загрузки](tests/test_mssql.py)

### Исполнение MDX на Mondrian 3.2

Задача CI `mssql` после загрузки звезды скачивает Mondrian 3.2 (`mondrian-3.2.0-13661-JS-3` из репозитория Jaspersoft) и ещё 13 jar по закреплённым версиям, сверяет каждый файл командой `sha256sum -c` ([список](mondrian/artifacts.txt), [скрипт](scripts/fetch-mondrian.sh)), готовит тексты запросов (`python -m sales_cube.mondrian statements`), компилирует [RunMdx.java](mondrian/RunMdx.java) и исполняет все 10 запросов на JDK 17 с `-Dmondrian.olap.SsasCompatibleNaming=true` — тогда имена иерархий те же, что в SSAS (`[Date].[Calendar]`). Ответы пишутся в форме mddataset XMLA в `reports/mondrian/answers/`, затем сверяются: `python -m sales_cube.mondrian report docs/runs/expected-seed64.json reports/mondrian/answers` (таблица по запросам), `python -m sales_cube.cellset docs/runs/expected-seed64.json reports/mondrian/answers --queries mdx` и негативные проверки `python -m pytest -v -m slow tests/test_mondrian_answers.py`. Запуск — только в CI на Linux с Docker и Java; на Windows проекта Java не нужна. Подробно — [протокол](docs/runs/2026-11-21-mondrian.md).

### Результаты

Полный прогон CI 21.11.2026 (`ssas-mdx-sales-cube_20261121-063735`): задача `offline` — 50 тестов за 0,89 с, задача `mssql` — 8 тестов загрузки за 8,23 с, 10 из 10 ответов Mondrian совпали с ожидаемыми, 23 теста ответов Mondrian, из них 22 негативных, за 0,19 с ([протокол Mondrian](docs/runs/2026-11-21-mondrian.md)). Полный прогон 19.11.2026 (`ssas-mdx-sales-cube_20261119-113824`): 32 и 8 тестов ([протокол](docs/runs/2026-11-19-audit.md), [выдержка](docs/runs/2026-11-19-ci-local.txt)). Прогон 18.11.2026 — 20 и 6 тестов ([протокол](docs/runs/2026-11-18-mssql.md), [журналы](docs/runs/mssql-evidence.zip)). Ожидаемые ответы, с которыми сверяются ответы Mondrian и будут сверяться ответы SSAS:

| Показатель | Значение |
|---|---:|
| Строк продаж за два года | 1 838 |
| Выручка за два года | 870 055 ₽ |
| Выручка 2025 года по категориям Office / Tech | 192 840 / 218 900 ₽ |
| Выручка за январь — март 2025 года | 91 350 ₽ |
| Март 2025 / март 2024 | 28 625 / 42 395 ₽ |
| Изменение марта к тому же месяцу прошлого года | −13 770 ₽ |

Это ответы pandas, подтверждённые выборками SQLite. Mondrian 3.2 вернул те же числа на все 10 запросов (уровень — заменяющий движок Mondrian 3.2, не SSAS); ответов SSAS нет. [Все 27 строк](docs/runs/expected-seed64.json) · [Конспект](docs/STUDY.md)

### Ограничения

- Масштаб данных учебный: 6 товаров в 2 категориях, 4 покупателя в 2 регионах, 1 838 строк продаж. TopCount, разрезы по категориям и регионам и запрос по клиентам региона на таком справочнике мало что показывают: запросы иллюстрируют синтаксис MDX, а не аналитику. Текст MDX исполнен только движком Mondrian 3.2, у которого свой диалект: два расхождения с SSAS описаны выше. Что SSAS примет тексты без правок и вернёт те же ответы, не проверено.
- Ожидаемые ответы считают два независимых расчёта на Python и SQLite; с ними совпали ответы Mondrian, а ответы SSAS не проверены: куб в SSAS не разворачивался, Create и ProcessFull не выполнялись.
- Mondrian — ROLAP: каждый запрос он переводит в SQL к звезде и не хранит куб. Хранилище MOLAP, обработка и агрегации SSAS этим прогоном не проверены. XMLA-обработчик самого Mondrian 3.2 на этих запросах падает (ClassCastException при записи свойств членов), поэтому XML ответа собирает [RunMdx.java](mondrian/RunMdx.java) из результата Mondrian; числа, подписи и порядок строк — от Mondrian.
- Ничьих в топ-3 запроса 09 на этих данных нет, поэтому разрешение ничьих по ключу товара исполнением не проверено.
- Выручка — целые рубли, без скидок, возвратов и валют.
- Excel, SSAS и SSMS в проекте не запускались; сводная таблица Excel на кубе не собиралась.
