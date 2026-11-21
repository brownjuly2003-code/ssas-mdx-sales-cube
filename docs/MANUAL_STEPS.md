# Проверка на SQL Server, SSAS и в Excel

Понадобятся экземпляр SQL Server Developer Edition, отдельный экземпляр Analysis Services в режиме Multidimensional, клиент sqlcmd, SQL Server Management Studio (SSMS), PowerShell с модулем SqlServer и Excel с провайдером MSOLAP. Имена реляционного и аналитического экземпляров могут отличаться. Обе учебные базы создаются с отдельными именами. Команды запускаются из корня проекта. Ключ `-C` нужен sqlcmd 18 (драйвер ODBC 18 по умолчанию шифрует соединение и проверяет сертификат); sqlcmd 17 его тоже принимает. Те же шаги без Excel выполняет ручной workflow `.github/workflows/ssas-windows.yml` на раннере GitHub `windows-2022`. Его запуск 21.11.2026 прошёл шаги 1–3 — [протокол](runs/2026-11-21-ssas-windows.md); шаг 4 (Excel) не выполнялся.

1. Выполнить команды офлайн-сборки из README. Появятся `reports/seed.sql` и `reports/expected.json`. В реляционном экземпляре создать пустую базу `P64SalesDW` с владельцем схемы dbo. Загрузить витрину под учётной записью с правом создания таблиц. Скрипт выполняет DDL и вставки в одной транзакции. При повторном запуске над готовыми таблицами он завершится с ошибкой и сохранит исходные строки.

   ```powershell
   sqlcmd -S localhost -E -C -d P64SalesDW -b -i sql/load.sql
   sqlcmd -S localhost -E -C -d P64SalesDW -b -Q "SELECT COUNT(*) AS lines, SUM(Units) AS units, SUM(Revenue) AS revenue FROM dbo.FactSales"
   ```

2. Дать служебной учётной записи SSAS право чтения четырёх таблиц в `P64SalesDW`: источник куба подключается от её имени (ImpersonateServiceAccount). Имя учётной записи — в свойствах службы, по умолчанию `NT Service\MSSQLServerOLAPService`.

   ```powershell
   $env:SsasAccount = (Get-CimInstance Win32_Service -Filter "Name='MSSQLServerOLAPService'").StartName
   sqlcmd -S localhost -E -C -d P64SalesDW -b -i sql/grant_ssas.sql
   ```

   В SSMS подключиться к **Analysis Services**. Открыть `cube/create.xmla`, для именованного экземпляра заменить `Data Source=localhost` в строке подключения источника на адрес **реляционного** экземпляра. Выполнить Create один раз: он создаёт только описание базы и куба. Затем выполнить `cube/process.xmla` (ProcessFull): без обработки куб пуст и запросы MDX завершатся ошибкой. Для повторной обработки уже существующей модели достаточно `cube/process.xmla`. Успешный ответ ProcessFull означает, что служба прочитала факты и измерения. Без SSMS те же два шага выполняет PowerShell: скрипт сохраняет ответ сервера и завершается ошибкой, если в нём есть Exception или Error. Затем `Test-CubeState.ps1` проверяет состояние Processed, хранение MOLAP и число членов уровней День, Товар и Клиент против строк измерений.

   ```powershell
   .\scripts\Invoke-Xmla.ps1 -Server localhost -InputFile cube/create.xmla -OutFile reports/create-response.xml
   .\scripts\Invoke-Xmla.ps1 -Server localhost -InputFile cube/process.xmla -OutFile reports/process-response.xml
   .\scripts\Test-CubeState.ps1 -Server localhost -ExpectedMembers @{ Date = 731; Product = 6; Customer = 4 } -OutDir reports/cube-state
   ```

3. В окне MDX выбрать аналитическую базу `P64SalesCube`, открыть `mdx/01_total.mdx` и выполнить запрос. Для сверки всего комплекта запустить из PowerShell с тем же виртуальным окружением Python. Передать имя **аналитического** экземпляра.

   ```powershell
   .\scripts\Compare-Cube.ps1 -Server localhost
   ```

   Команда сначала сверяет набор файлов `mdx/*.mdx` с ключами `reports/expected.json`, затем сохраняет ответы сервера в новую папку `reports/actual/<дата-время>/` (у каждого запуска своя) и сравнивает подписи строк, порядок и значения ячеек с `reports/expected.json`. В случае расхождения сохранить XML ответа и имя запроса. Для диагностики временных сравнений проверить атрибуты Years и Months, направление связей и месяц среза.

4. В Excel открыть **Данные → Получить данные → Из базы данных → Из базы данных Analysis Services**. Указать аналитический экземпляр, проверку подлинности Windows, базу `P64SalesCube` и куб `Sales`. Выбрать сводную таблицу. В строки поместить **Product → Catalog → Category**, в значения **Revenue**, в фильтр **Date → Calendar → Year** со значением **2025**. Сверить обе категории с `03_category` и общий итог с их суммой. Сохранить книгу и версию Excel вместе с протоколом, датой обработки и ответами сервера. Для повторной проверки обновить сводную через **Данные → Обновить всё**.
