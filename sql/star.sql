CREATE TABLE dbo.DimDate (
    DateKey int NOT NULL PRIMARY KEY,
    DayDate date NOT NULL UNIQUE,
    MonthKey int NOT NULL,
    MonthLabel varchar(7) NOT NULL,
    YearNumber int NOT NULL
);

CREATE TABLE dbo.DimProduct (
    ProductKey int NOT NULL PRIMARY KEY,
    ProductName varchar(32) NOT NULL UNIQUE,
    Category varchar(32) NOT NULL
);

CREATE TABLE dbo.DimCustomer (
    CustomerKey int NOT NULL PRIMARY KEY,
    CustomerName varchar(32) NOT NULL UNIQUE,
    Region varchar(32) NOT NULL
);

CREATE TABLE dbo.FactSales (
    LineKey int NOT NULL PRIMARY KEY,
    DateKey int NOT NULL REFERENCES dbo.DimDate(DateKey),
    ProductKey int NOT NULL REFERENCES dbo.DimProduct(ProductKey),
    CustomerKey int NOT NULL REFERENCES dbo.DimCustomer(CustomerKey),
    Units int NOT NULL CHECK (Units > 0),
    Revenue int NOT NULL CHECK (Revenue > 0)
);
