# Kołobrzeg Property Analytics

An English-language Power BI report for exploring recorded real-estate transactions in Kołobrzeg and nearby localities. It uses full CSV exports from Poland’s Register of Real Estate Prices (RCN) and imports data from PostgreSQL.

## What’s in the report

- **Transactions** shows transaction counts, median total prices and a transaction register.
- **Objects** shows the buildings, land parcels and units associated with transactions.
- **House Sales** focuses on open-market secondary sales of one residential building with land and full ownership. It shows sale counts, median total prices, land-size bands and building floor-area coverage.

## Run locally

Requirements are PostgreSQL, Python and Power BI Desktop on Windows.

1. Create a local PostgreSQL database named `kolobrzeg_property_analytics_v2` if you do not already have it. The import needs permission to create and update the `rcn` schema.
2. Install the Python dependency with `python -m pip install -r requirements.txt`.
3. Obtain a full 35-column RCN CSV for the desired area. From the repository root, run:

   ```powershell
   python power-bi/import_rcn.py "C:\path\to\rcn_export.csv"
   ```

   The loader defaults to the local database and the PostgreSQL role `postgres`. Use a PostgreSQL password file or another standard libpq authentication method. The loader accepts an alternative connection string through `--db`. The Power BI project targets `localhost:5432` and the database above.

4. Open `power-bi/RCN.pbip` in Power BI Desktop. Keep `RCN.Report` and `RCN.SemanticModel` next to it. Click **Refresh** and enter your local database credentials if prompted.

To update the report, import the next full export and click **Refresh** again. The loader logs each source file by SHA-256, imports in one transaction, and keys object rows by transaction ID, object type and object ID. The reporting views select the latest available transaction version. Weekly downloads and imports are currently manual.

## Baseline and interpretation

The 22 November 2026 export contains 54,345 object rows and 12,578 distinct transactions with document dates from 20 February 2020 through 22 October 2026. A sale can have several object rows. The strict House Sales selection contains 124 transactions, with a median total price of PLN 860,000. Seven have recorded house floor area, including two between 100 and 150 m². Missing areas remain blank. Prices represent transactions and can include land. Land area and house floor area are distinct measures.

## Repository contents

The repository contains the report definition, semantic model and PostgreSQL loader. Source extracts, database backups, local credentials, Power BI caches and data-bearing report exports are kept locally.
