# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# Larva Labs CryptoPunks Access Skill

This skill extracts structured data from CryptoPunk detail pages on Larva Labs (larvalabs.com).

## Overview

CryptoPunks are one of the first NFT projects on Ethereum. This skill provides access to detailed information about individual CryptoPunks, including:

- **Punk Type & Rarity**: Alien, Ape, Zombie, Male, Female with population counts
- **Attributes**: Visual traits (e.g., Bandana, Pipe, Shades) with rarity counts
- **Market Status**: Current owner, sale status, active bids
- **Transaction History**: Complete history of transfers, sales, bids, and offers

## Functions

### get_punk_details

Fetches comprehensive details about a specific CryptoPunk.

**Parameters:**
- `punk_id` (string): The CryptoPunk ID number (0-9999)
- OR `url` (string): Full URL to the detail page

**Returns:**
```json
{
  "success": true,
  "punk_id": "5822",
  "url": "https://www.larvalabs.com/cryptopunks/details/5822",
  "title": "CryptoPunks: Details for Punk #5822",
  "type": "Alien",
  "type_count": 9,
  "attributes": [
    {
      "name": "Bandana",
      "count": 481
    }
  ],
  "attribute_count": 1,
  "market_status": {
    "owner": "0xba5514",
    "for_sale": false,
    "has_bids": true,
    "current_bid": {
      "amount": "<0.01Ξ",
      "from": "yungwknd…"
    }
  },
  "image_url": "https://www.larvalabs.com/public/images/cryptopunks/punk5822.png",
  "transaction_count": 96
}
```

### get_punk_transactions

Fetches transaction history for a specific CryptoPunk.

**Parameters:**
- `punk_id` (string): The CryptoPunk ID number (0-9999)
- OR `url` (string): Full URL to the detail page
- `transaction_limit` (integer, optional): Max transactions to return (default: 50, max: 500)

**Returns:**
```json
{
  "success": true,
  "punk_id": "7804",
  "url": "https://www.larvalabs.com/cryptopunks/details/7804",
  "total_transactions": 165,
  "returned_transactions": 50,
  "transactions": [
    {
      "type": "Sold",
      "from": "peruggia…",
      "to": "0x9bc2d5",
      "amount": "4.85KΞ ($16.41M)",
      "date": "Mar 20, 2024"
    },
    {
      "type": "Transfer",
      "from": "0x9bc2d5",
      "to": "artudito…",
      "amount": null,
      "date": "Apr 11, 2024"
    }
  ],
  "transaction_type_summary": {
    "Sold": 1,
    "Transfer": 15,
    "Bid": 80,
    "Bid Withdrawn": 45,
    "Offered": 24
  },
  "last_sale": {
    "type": "Sold",
    "from": "peruggia…",
    "to": "0x9bc2d5",
    "amount": "4.85KΞ ($16.41M)",
    "date": "Mar 20, 2024"
  }
}
```

## Transaction Types

The transaction history includes various types:

- **Transfer**: Punk moved between wallets (no sale)
- **Sold**: Punk sold for ETH
- **Bid**: Someone placed a bid on the punk
- **Bid Withdrawn**: A bid was withdrawn
- **Offered**: Owner listed the punk for sale
- **Offered Withdrawn**: Sale listing was removed

## Notable CryptoPunks

Some famous CryptoPunks to explore:

- **Punk 5822**: Alien with Bandana - one of 9 aliens
- **Punk 7804**: Alien with Cap Forward, Pipe, Small Shades - one of 9 aliens
- **Punk 7523**: Alien with COVID mask - sold for $11.8M
- **Punk 3100**: Alien with Headband - one of 9 aliens
- **Punk 9998**: Alien with Knitted Cap

## Notes

- The site uses JavaScript to load content, so this skill uses browser automation
- Page load may take a few seconds due to dynamic content
- Transaction history includes both historical and recent transactions
- ETH amounts include USD equivalent at transaction time
- Owner addresses may be truncated with "…" for display
- The site is an archived version; the official site is now cryptopunks.app

## Technical Details

This skill uses Playwright browser automation to:
1. Navigate to the CryptoPunk detail page
2. Wait for dynamic content to load
3. Extract structured data from the rendered DOM
4. Parse and normalize the data for consistent output

The skill handles timeouts, missing data, and various edge cases gracefully.
