-- Read access of the Analysis Services service account to the star.
-- cube/create.xmla connects with ImpersonateServiceAccount, so ProcessFull reads the tables
-- as the account of the service (StartName of MSSQLServerOLAPService, by default
-- NT Service\MSSQLServerOLAPService). The account comes in the sqlcmd variable SsasAccount
-- (-v or an environment variable of the same name):
--   sqlcmd -S localhost -E -C -d P64SalesDW -b -i sql/grant_ssas.sql
:ON ERROR EXIT
SET NOCOUNT ON;
IF DB_NAME() <> 'P64SalesDW'
    THROW 50001, 'Select the dedicated P64SalesDW database.', 1;
DECLARE @account sysname = N'$(SsasAccount)';
DECLARE @name nvarchar(300) = QUOTENAME(@account);
DECLARE @sql nvarchar(max);
IF SUSER_ID(@account) IS NULL
BEGIN
    SET @sql = N'CREATE LOGIN ' + @name + N' FROM WINDOWS;';
    EXEC (@sql);
END;
IF DATABASE_PRINCIPAL_ID(@account) IS NULL
BEGIN
    SET @sql = N'CREATE USER ' + @name + N' FOR LOGIN ' + @name + N';';
    EXEC (@sql);
END;
SET @sql = N'ALTER ROLE db_datareader ADD MEMBER ' + @name + N';';
EXEC (@sql);
SELECT member.name AS principal, role.name AS database_role
FROM sys.database_role_members AS link
JOIN sys.database_principals AS member ON member.principal_id = link.member_principal_id
JOIN sys.database_principals AS role ON role.principal_id = link.role_principal_id
WHERE member.name = @account;
