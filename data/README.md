# Data

`raw/` holds 8 of the 9 files from the **Brazilian E-Commerce Public Dataset by Olist**: about 100,000 real, anonymized orders placed on the Olist marketplace between 2016 and 2018. The files are gzipped but otherwise unchanged.

- **Original source:** https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce
- **License:** [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/) (attribution, non-commercial, share-alike). Data in this folder and anything derived from it in this repository is shared under the same license.
- **Copy used:** the public mirror at https://github.com/dujiaying/olist

| File | Rows | Contents |
|---|---|---|
| `olist_orders_dataset.csv.gz` | 99,441 | Order status and timestamps (purchase, approval, carrier handoff, delivery, estimated delivery) |
| `olist_order_items_dataset.csv.gz` | 112,650 | One row per product line: product, seller, price, freight, seller shipping deadline |
| `olist_order_payments_dataset.csv.gz` | 103,886 | Payment method, installments and amount; an order can have several payments |
| `olist_order_reviews_dataset.csv.gz` | 100,000 | Review score (1–5) and comment; includes duplicates (see `docs/metrics.md`) |
| `olist_customers_dataset.csv.gz` | 99,441 | `customer_id` (per order), `customer_unique_id` (per person), city, state |
| `olist_products_dataset.csv.gz` | 32,951 | Category (Portuguese), weight and dimensions |
| `olist_sellers_dataset.csv.gz` | 3,095 | Seller city and state |
| `product_category_name_translation.csv.gz` | 71 | Portuguese to English category names |

The ninth file in the original dataset (geolocation, 1M rows of zip-code coordinates) is not used: the customer and seller tables already carry city and state.
