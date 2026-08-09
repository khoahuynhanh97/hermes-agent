# Shopee Vietnam public and Affiliate research for Hermes

Date: 2026-08-01

Scope: public/official sources only where available. No authenticated account inspection, private API calls, or code changes.

## Executive conclusion

Hermes should not crawl Shopee public pages at 100-200 products/day. Shopee Vietnam's Terms of Service explicitly prohibit robots, spiders, and automated or manual methods used to monitor, measure, collect, or copy Shopee Content without prior written consent. A permissive `robots.txt` would not override that contractual restriction; the current `robots.txt` could not be independently retrieved during this review.

The preferred ingestion order is:

1. Shopee Affiliate Product Feed, if the account has been enabled as a Product Feed partner.
2. An approved Affiliate API/feed contract, if Shopee grants credentials and written scope.
3. Shopee Open Platform only for products belonging to shops that explicitly authorize the Hermes app.
4. Manual URL/CSV intake for public listings when no approved machine interface exists.

Do not use undocumented website/mobile JSON endpoints, browser session replay, CAPTCHA bypass, cookie harvesting, or headless scraping as production fallbacks.

## Facts from primary sources

### Public product data

- Shopee officially describes search by keyword/image and filtering/sorting by category, seller location, shipping, price range, newest, best-selling, price, ratings, and promotion labels.  
  Source: [Shopee Help - finding products](https://help.shopee.vn/portal/4/article/79283-%5BTh%C3%A0nh-vi%C3%AAn-m%E1%BB%9Bi%5D-C%C3%A1ch-T%C3%ACm-Ki%E1%BA%BFm-S%E1%BA%A3n-Ph%E1%BA%A9m-C%E1%BA%A7n-Mua-Tr%C3%AAn-Shopee)
- Shopee's buying guide identifies product-page information including base/promotional price, seller location, ratings, sold count, structure/features, warranty, variants, and quantity.  
  Source: [Shopee Help - buying products](https://help.shopee.vn/portal/4/article/79180-%5BTh%C3%A0nh-vi%C3%AAn-m%E1%BB%9Bi%5D-L%C3%A0m-sao-%C4%91%E1%BB%83-mua-h%C3%A0ng-%2F-%C4%91%E1%BA%B7t-h%C3%A0ng-tr%C3%AAn-%E1%BB%A9ng-d%E1%BB%A5ng-Shopee%3F)
- Listing rules confirm title, images, price, description, origin, attributes, and warranty as listing data.  
  Source: [Shopee listing rules](https://help.shopee.vn/portal/4/article/77246)

These fields are publicly visible to users, but public visibility is not permission for automated collection.

### Affiliate system and Product Feed

- The Affiliate dashboard requires a Shopee Affiliate account and exposes performance, product-link collection, commission information, campaigns, offers, and related tools. Some offer/program areas are available only to selected users.  
  Sources: [Affiliate system guide](https://help.shopee.vn/portal/10/article/152867-H%C6%B0%E1%BB%9Bng-d%E1%BA%ABn-s%E1%BB%AD-d%E1%BB%A5ng-h%E1%BB%87-th%E1%BB%91ng-Shopee-Affiliate), [Affiliate page update](https://help.shopee.vn/portal/10/article/141547-C%E1%BA%ADp-nh%E1%BA%ADt-m%E1%BB%9Bi-v%E1%BB%81-Trang-th%C3%B4ng-tin-Shopee-Affiliate)
- Shopee officially documents a downloadable Product Feed at `Login > Creative > Product Feed`, specifically for “Product Feed partners”. It confirms at least a product short-link/landing-page field and affiliate/sub-ID tracking. The public article does not publish the full feed schema, update frequency, quota, or universal eligibility.  
  Source: [Shopee Help - affiliate short links and Product Feed](https://help.shopee.vn/portal/10/article/172955-H%C6%B0%E1%BB%9Bng-d%E1%BA%ABn-t%E1%BA%A1o-link-Ti%E1%BA%BFp-th%E1%BB%8B-li%C3%AAn-k%E1%BA%BFt-r%C3%BAt-g%E1%BB%8Dn)
- Commission is account/product/time dependent. Shopee describes Shopee commission and seller-funded Xtra commission; special programs can be restricted to selected KOL/KOC accounts.  
  Sources: [Shopee commission guide](https://help.shopee.vn/portal/10/article/190646-T%C3%ACm-hi%E1%BB%83u-v%E1%BB%81-Hoa-h%E1%BB%93ng-Ti%E1%BA%BFp-th%E1%BB%8B-li%C3%AAn-k%E1%BA%BFt-d%C3%A0nh-cho-Shopee-KOL/KOC-Affiliate), [Shopee Video Affiliate FAQ](https://help.shopee.vn/portal/10/article/164064)
- Affiliate participation is established through registration/acceptance by Shopee, and registered promotional media must be approved. Shopee can accept or reject participation.  
  Source: [Shopee Affiliate terms](https://help.shopee.vn/portal/10/article/171010)

### Open Platform

- Shopee Open Platform 2.0 uses developer registration, app creation, Partner ID/key, sandbox testing, Shopee approval for live access, and explicit shop authorization. API capabilities depend on developer/app type.  
  Source: [Official Shopee Open API Developer Guide PDF](https://cdngarenanow-a.akamaihd.net/shopee/seller/seller_cms/3a486040f6e64972f6dd53128a79f0dc/%5BTW%5D%5BOpen%20API%5DAPI%E4%B8%B2%E6%8E%A5%E8%AA%AA%E6%98%8E%E4%BA%8B%E9%A0%85%20%282020_09%29_newnew.pdf)
- Product-management access includes shop/item/public/image APIs for eligible app types; calls operate after shop authorization.  
  Source: [Official Shopee Open API capability/authorization guide PDF](https://cdngarenanow-a.akamaihd.net/shopee/seller/seller_cms/b17e7e1846b98c422e4404f223b9f65f/%5BTW%5D%5BOpen%20API%5DAPI%E4%B8%B2%E6%8E%A5%E8%AA%AA%E6%98%8E%E4%BA%8B%E9%A0%85%20%282020_10_21%29_newnew.pdf)

The accessible official guide is Taiwan-oriented and dated 2020. It proves the platform's authorization model, but Vietnam eligibility, current endpoint schemas, quotas, and approval criteria must be verified in the live Open Platform console or directly with Shopee.

### Automation, robots, login, and content restrictions

- Shopee Vietnam prohibits using robots, spiders, automated devices, or manual methods to monitor, measure, collect, or copy Shopee Content without prior written approval. It also prohibits copying/adapting Shopee content and bypassing security controls.  
  Source: [Shopee Vietnam Terms of Service, sections 3.1 and 6](https://help.shopee.vn/portal/4/article/77243-%C4%90I%E1%BB%80U-KHO%E1%BA%A2N-D%E1%BB%8ACH-V%E1%BB%A4)
- Affiliate terms reject bot/script-generated users and fraudulent or simulated activity.  
  Source: [Shopee Affiliate terms](https://help.shopee.vn/portal/10/article/171010)
- The Affiliate dashboard is a JavaScript application and protected features require login. Public documentation does not grant permission to automate the authenticated UI.  
  Source: [Shopee Affiliate dashboard](https://affiliate.shopee.vn/dashboard)

## Inferences for Hermes

The following are architectural inferences, not published Shopee guarantees:

- Product Feed is the only currently evidenced official mechanism that plausibly supports discovery at 100-200 products/day without page scraping.
- Open Platform is suitable for syncing an owned/authorized seller catalog, not broad marketplace or competitor discovery.
- The Product Feed schema should be learned from an actual export after confirming the account is entitled to use it. Likely normalized Hermes fields include source IDs/URL, title, shop, category, price, commission, images, availability, and timestamps, but only fields present in the authorized export may be ingested.
- Public page fields may be accepted as manually supplied evidence but should not be refreshed automatically until Shopee grants written permission.

## Safe adapter design

Use one adapter contract with explicit provenance and permission:

```text
ShopeeDiscoveryPort
  list_candidates(cursor, filters) -> CandidatePage
  get_capabilities() -> scopes, quotas, allowed_fields
  checkpoint(cursor)
```

Recommended implementations:

- `ShopeeAffiliateFeedAdapter`: imports a user-downloaded or officially delivered feed; validates schema, size, checksum, and timestamps.
- `ShopeeApprovedAffiliateApiAdapter`: disabled until Shopee supplies credentials, documentation, quotas, and written scope.
- `ShopeeAuthorizedShopAdapter`: Open Platform adapter restricted to explicitly authorized `shop_id` values.
- `ShopeeManualImportAdapter`: accepts user-selected URLs/CSV rows and records that enrichment is not automatic.

Controls:

- SQLite remains Hermes' operational source of truth; Google Sheets is a review/control projection.
- Store `source_type`, `source_url`, `shop_id`, `item_id`, `permission_basis`, `retrieved_at`, and `raw_record_hash`.
- Apply idempotent upserts, cursor checkpoints, rate/quota budgets, exponential backoff, and a kill switch.
- Deny adapters without an allowlisted host and declared permission basis.
- Never persist Shopee passwords/cookies in jobs or Sheets; secrets belong in the existing secret store/environment.
- Do not download/reuse seller images or videos for derivative publication unless licensing/permission is established. Store references and extracted factual attributes separately from creative assets.

## Decision

Proceed with a Product Feed capability check inside the user's Affiliate account. If `Creative > Product Feed` exists, inspect one export's headers and terms before implementation. If absent, request Product Feed/API access from Shopee; until approved, discovery remains manual and Hermes must not automate public-page crawling.
