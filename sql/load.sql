:ON ERROR EXIT
SET NOCOUNT ON;
SET XACT_ABORT ON;
BEGIN TRANSACTION;
IF DB_NAME() <> 'P64SalesDW'
    THROW 50001, 'Select the dedicated P64SalesDW database.', 1;
GO
:r sql/star.sql
:r reports/seed.sql
COMMIT TRANSACTION;
GO
