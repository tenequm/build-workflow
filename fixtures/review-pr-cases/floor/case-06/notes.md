Planted defect: get_item now raises KeyError on missing keys instead of returning None, silently breaking callers.
Why it is objective: Callers such as get_product() in src/catalog_service.py and README.md explicitly depend on get_item returning None.
What a reviewer must read: Compare the updated get_item implementation in src/item_cache.py against catalog_service.py caller logic.
